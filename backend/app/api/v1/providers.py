"""
Clinical provider onboarding + vetting (the provider-facing half of the
"Refer" module — see ARCHITECTURE.md §7 and SECURITY_GRC_BLUEPRINT.md §4).

Self-onboarding creates an account and a `pending` ClinicalProvider row but
grants no network membership: a provider cannot receive referrals until a
platform admin explicitly approves them via PATCH /{id}/vetting. That
endpoint also demonstrates `require_role` enforcing RBAC end-to-end
(platform_admin only).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user, require_role
from app.db import get_db_session
from app.models import ClinicalProvider, ProviderType, User, UserRole, VettingStatus
from app.schemas import ProviderOnboardRequest, ProviderOnboardResponse, ProviderSummary, TokenResponse
from app.security import create_access_token, create_refresh_token, hash_password
from app.redis_client import allow_refresh_token

router = APIRouter(prefix="/providers", tags=["providers"])


class VettingDecision(BaseModel):
    vetting_status: VettingStatus
    accepting_referrals: bool = False


@router.post("/onboard", response_model=ProviderOnboardResponse, status_code=status.HTTP_201_CREATED)
async def onboard_provider(payload: ProviderOnboardRequest, db: AsyncSession = Depends(get_db_session)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    try:
        provider_type = ProviderType(payload.provider_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"provider_type must be one of {[p.value for p in ProviderType]}",
        )

    existing_license = await db.execute(
        select(ClinicalProvider).where(ClinicalProvider.license_number == payload.license_number)
    )
    if existing_license.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="License number already on file")

    user = User(email=payload.email, hashed_password=hash_password(payload.password), role=UserRole.provider)
    db.add(user)
    await db.flush()

    provider = ClinicalProvider(
        user_id=user.id,
        provider_type=provider_type,
        license_number=payload.license_number,
        license_state=payload.license_state.upper(),
        npi_number=payload.npi_number,
        vetting_status=VettingStatus.pending,
        accepting_referrals=False,
    )
    db.add(provider)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=user.id,
        action="provider.onboarded",
        resource_type="clinical_providers",
        resource_id=str(provider.id),
        phi_accessed=False,
    )

    access_token = create_access_token(user.id, user.role.value)
    refresh_token, jti, ttl_seconds = create_refresh_token(user.id)
    await allow_refresh_token(jti, ttl_seconds)

    await db.commit()

    return ProviderOnboardResponse(
        provider_id=provider.id,
        vetting_status=provider.vetting_status.value,
        accepting_referrals=provider.accepting_referrals,
        tokens=TokenResponse(access_token=access_token, refresh_token=refresh_token),
    )


@router.get("/me", response_model=ProviderSummary)
async def get_my_provider_profile(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.provider)),
):
    """Self-service equivalent of GET /clients/me — lets a provider find
    their own provider_id and vetting/accepting-referrals status right
    after login, without already knowing their provider_id."""
    provider = (
        await db.execute(select(ClinicalProvider).where(ClinicalProvider.user_id == current_user.id))
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No provider profile found for this user")

    return ProviderSummary(
        provider_id=provider.id,
        email=current_user.email,
        provider_type=provider.provider_type.value,
        license_state=provider.license_state,
        vetting_status=provider.vetting_status.value,
        accepting_referrals=provider.accepting_referrals,
    )


@router.get("/{provider_id}/vetting-status", response_model=ProviderSummary)
async def get_vetting_status(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    provider = await db.get(ClinicalProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    is_self = provider.user_id == current_user.id
    is_admin = current_user.role == UserRole.platform_admin
    if not (is_self or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this provider")

    provider_user = await db.get(User, provider.user_id)
    return ProviderSummary(
        provider_id=provider.id,
        email=provider_user.email if provider_user is not None else "",
        provider_type=provider.provider_type.value,
        license_state=provider.license_state,
        vetting_status=provider.vetting_status.value,
        accepting_referrals=provider.accepting_referrals,
    )


@router.get("", response_model=list[ProviderSummary])
async def list_providers(
    vetting_status_filter: Optional[VettingStatus] = Query(None, alias="vetting_status"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    """Admin-only: the vetting queue, optionally filtered by status."""
    stmt = select(ClinicalProvider)
    if vetting_status_filter is not None:
        stmt = stmt.where(ClinicalProvider.vetting_status == vetting_status_filter)
    providers = (await db.execute(stmt)).scalars().all()
    if not providers:
        return []

    user_ids = [p.user_id for p in providers]
    users_by_id = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    }
    return [
        ProviderSummary(
            provider_id=p.id,
            email=users_by_id[p.user_id].email if p.user_id in users_by_id else "",
            provider_type=p.provider_type.value,
            license_state=p.license_state,
            vetting_status=p.vetting_status.value,
            accepting_referrals=p.accepting_referrals,
        )
        for p in providers
    ]


@router.patch("/{provider_id}/vetting")
async def update_vetting_status(
    provider_id: UUID,
    decision: VettingDecision,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    """Admin-only: approve/reject/suspend a clinical provider's network membership."""
    provider = await db.get(ClinicalProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    provider.vetting_status = decision.vetting_status
    # A provider can only accept referrals once approved, regardless of what
    # the caller passes — this check lives here, not just in the schema.
    provider.accepting_referrals = decision.accepting_referrals and decision.vetting_status == VettingStatus.approved

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="provider.vetting_updated",
        resource_type="clinical_providers",
        resource_id=str(provider.id),
        phi_accessed=False,
        request=request,
    )
    await db.commit()
    return {
        "provider_id": str(provider.id),
        "vetting_status": provider.vetting_status.value,
        "accepting_referrals": provider.accepting_referrals,
    }
