"""
Client self-service profile + admin coach/church assignment.

The `Client` row itself is created atomically at registration (see
api/v1/auth.py's `register`), but a client still needs a way to (a)
discover their own `client_id` — every other module's endpoints are keyed
off it, not `User.id` — and (b) fill in the optional profile fields.
Assigning a coach or a sponsoring church is deliberately kept admin-only:
letting a client self-assign either would let them grant themselves a
coach's access to their case or claim a church's sponsorship unearned.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user, require_role
from app.db import get_db_session
from app.models import Church, Client, Coach, User, UserRole
from app.schemas import ClientAdminAssignRequest, ClientProfileResponse, ClientProfileUpdateRequest

router = APIRouter(prefix="/clients", tags=["clients"])


def _to_response(c: Client) -> ClientProfileResponse:
    return ClientProfileResponse(
        client_id=c.id,
        user_id=c.user_id,
        coach_id=c.coach_id,
        church_sponsor_id=c.church_sponsor_id,
        date_of_birth=c.date_of_birth,
        emergency_contact=c.emergency_contact,
        created_at=c.created_at,
    )


async def _get_own_client_row(db: AsyncSession, user: User) -> Client:
    client_row = (await db.execute(select(Client).where(Client.user_id == user.id))).scalar_one_or_none()
    if client_row is None:
        # Shouldn't happen for anyone who registered through /auth/register,
        # but a pre-existing client_admin-created User (e.g. via seed.py
        # against an older DB) could lack one.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No client profile found for this account")
    return client_row


@router.get("/me", response_model=ClientProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.client)),
):
    client_row = await _get_own_client_row(db, current_user)
    return _to_response(client_row)


@router.patch("/me", response_model=ClientProfileResponse)
async def update_my_profile(
    payload: ClientProfileUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.client)),
):
    client_row = await _get_own_client_row(db, current_user)

    if payload.date_of_birth is not None:
        client_row.date_of_birth = payload.date_of_birth
    if payload.emergency_contact is not None:
        client_row.emergency_contact = payload.emergency_contact

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="client.profile_updated",
        resource_type="clients",
        resource_id=str(client_row.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(client_row)


@router.get("/{client_id}", response_model=ClientProfileResponse)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client_row = await db.get(Client, client_id)
    if client_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    is_self = current_user.role == UserRole.client and client_row.user_id == current_user.id
    is_admin = current_user.role == UserRole.platform_admin
    if not (is_self or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this client")

    return _to_response(client_row)


@router.patch("/{client_id}/assignment", response_model=ClientProfileResponse)
async def assign_coach_or_church(
    client_id: UUID,
    payload: ClientAdminAssignRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    client_row = await db.get(Client, client_id)
    if client_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if payload.coach_id is not None:
        if await db.get(Coach, payload.coach_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coach not found")
        client_row.coach_id = payload.coach_id

    if payload.church_sponsor_id is not None:
        if await db.get(Church, payload.church_sponsor_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Church not found")
        client_row.church_sponsor_id = payload.church_sponsor_id

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="client.assignment_updated",
        resource_type="clients",
        resource_id=str(client_row.id),
        phi_accessed=False,
    )
    await db.commit()
    return _to_response(client_row)
