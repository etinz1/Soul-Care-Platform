"""
Prayer request routing — the second half of the "Scheduling/prayer
routing" module (ARCHITECTURE.md §7 step 6, API routing §4 `/scheduling`).

Routing rule (deterministic, mirrors the risk-engine philosophy of
services/risk_engine.py: no inference, just an explicit rule): a new
request is auto-assigned to the client's own coach when one is on file;
otherwise it lands unassigned in the admin triage queue. `urgency` does not
change who it's assigned to (a client with no coach still has no one to
route to) but is exposed so the queue can be sorted/filtered by it.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user
from app.db import get_db_session
from app.models import Client, Coach, PrayerRequest, User, UserRole
from app.schemas import PrayerRequestCreateRequest, PrayerRequestResponse, PrayerRequestUpdateRequest

router = APIRouter(prefix="/scheduling/prayer-requests", tags=["scheduling"])


def _to_response(pr: PrayerRequest) -> PrayerRequestResponse:
    return PrayerRequestResponse(
        prayer_request_id=pr.id,
        client_id=pr.client_id,
        request_text=pr.request_text,
        urgency=pr.urgency,
        assigned_to=pr.assigned_to,
        status=pr.status,
        created_at=pr.created_at,
    )


@router.post("", response_model=PrayerRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_prayer_request(
    payload: PrayerRequestCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = await db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if current_user.role == UserRole.client and client.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot submit a request for another client")
    if current_user.role not in (UserRole.client, UserRole.platform_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to submit a prayer request")

    assigned_to = None
    if client.coach_id is not None:
        coach = await db.get(Coach, client.coach_id)
        if coach is not None:
            assigned_to = coach.user_id

    prayer_request = PrayerRequest(
        client_id=payload.client_id,
        request_text=payload.request_text,
        urgency=payload.urgency,
        assigned_to=assigned_to,
        status="open",
    )
    db.add(prayer_request)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="prayer_request.created",
        resource_type="prayer_requests",
        resource_id=str(prayer_request.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(prayer_request)


@router.get("", response_model=list[PrayerRequestResponse])
async def list_prayer_requests(
    client_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Role-scoped: a client sees their own requests; staff see requests assigned to them; admin sees all."""
    stmt = select(PrayerRequest)

    if current_user.role == UserRole.client:
        client = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalar_one_or_none()
        if client is None:
            return []
        stmt = stmt.where(PrayerRequest.client_id == client.id)
    elif current_user.role in (UserRole.coach, UserRole.provider, UserRole.church_admin):
        stmt = stmt.where(PrayerRequest.assigned_to == current_user.id)
    elif current_user.role == UserRole.platform_admin:
        if client_id is not None:
            stmt = stmt.where(PrayerRequest.client_id == client_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to list prayer requests")

    if status_filter is not None:
        stmt = stmt.where(PrayerRequest.status == status_filter)

    requests = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in requests]


@router.patch("/{prayer_request_id}", response_model=PrayerRequestResponse)
async def update_prayer_request(
    prayer_request_id: UUID,
    payload: PrayerRequestUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    prayer_request = await db.get(PrayerRequest, prayer_request_id)
    if prayer_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prayer request not found")

    is_admin = current_user.role == UserRole.platform_admin
    is_assignee = prayer_request.assigned_to == current_user.id

    if payload.assigned_to is not None and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin can reassign a prayer request")
    if not (is_admin or is_assignee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to update this prayer request")

    if payload.status is not None:
        prayer_request.status = payload.status
    if payload.assigned_to is not None:
        prayer_request.assigned_to = payload.assigned_to

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="prayer_request.updated",
        resource_type="prayer_requests",
        resource_id=str(prayer_request.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(prayer_request)
