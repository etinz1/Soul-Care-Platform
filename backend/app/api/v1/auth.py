"""
Auth endpoints: register (client self-signup only), login, refresh, logout.

Every successful login/refresh is audit-logged (AU-2/CC7.2 — see
docs/SECURITY_GRC_BLUEPRINT.md) since authentication events are exactly the
kind of activity a HIPAA-adjacent audit trail needs to reconstruct.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user
from app.db import get_db_session
from app.models import User, UserRole
from app.redis_client import allow_refresh_token, is_refresh_token_allowed, revoke_refresh_token
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db_session)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.client,
    )
    db.add(user)
    await db.flush()
    tokens = await _issue_tokens(db, user)
    await db.commit()
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Constant-shape failure path: verify against a dummy hash when the user
    # doesn't exist, so login timing doesn't leak whether an email is
    # registered.
    if user is None:
        hash_password("dummy-password-for-timing-parity")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    tokens = await _issue_tokens(db, user)

    await write_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.login",
        resource_type="users",
        resource_id=str(user.id),
        phi_accessed=False,
        request=request,
    )
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if claims.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    jti = claims.get("jti")
    if jti is None or not await is_refresh_token_allowed(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")

    try:
        user = await db.get(User, UUID(claims["sub"]))
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token subject")
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Rotate: revoke the used refresh token and issue a new pair.
    await revoke_refresh_token(jti)
    tokens = await _issue_tokens(db, user)
    await db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, current_user: User = Depends(get_current_user)):
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("jti"):
            await revoke_refresh_token(claims["jti"])
    except JWTError:
        pass  # already invalid/expired — logout is idempotent either way
    return None


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    access_token = create_access_token(user.id, user.role.value)
    refresh_token, jti, ttl_seconds = create_refresh_token(user.id)
    await allow_refresh_token(jti, ttl_seconds)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
