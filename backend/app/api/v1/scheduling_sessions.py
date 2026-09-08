"""
Session scheduling — the first half of the "Scheduling/prayer routing"
module (ARCHITECTURE.md §7 step 6, API routing §4 `/scheduling`).

A session can be `coaching` (led by the client's assigned coach),
`clinical` (led by a provider who holds an *accepted* referral for that
client), or `prayer` (led by the client's assigned coach). Notes are kept
in a separate table (`session_notes`) reached only via reverse lookup — see
the comment on `SessionRecord` in models.py — and `note_type=clinical`
notes are readable only by the treating provider, the owning client, and
platform admins, never by a coach or church (ARCHITECTURE.md §3 ERD note).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user
from app.db import get_db_session
from app.models import (
    Client,
    Coach,
    ClinicalProvider,
    Referral,
    ReferralStatus,
    SessionNote,
    SessionRecord,
    User,
    UserRole,
)
from app.schemas import (
    SessionCreateRequest,
    SessionNoteCreateRequest,
    SessionNoteResponse,
    SessionResponse,
    SessionUpdateRequest,
)

router = APIRouter(prefix="/scheduling/sessions", tags=["scheduling"])


def _to_response(session: SessionRecord) -> SessionResponse:
    return SessionResponse(
        session_id=session.id,
        client_id=session.client_id,
        coach_id=session.coach_id,
        provider_id=session.provider_id,
        session_type=session.session_type,
        scheduled_at=session.scheduled_at,
        status=session.status,
    )


async def _get_own_coach(db: AsyncSession, user: User) -> Optional[Coach]:
    return (await db.execute(select(Coach).where(Coach.user_id == user.id))).scalar_one_or_none()


async def _get_own_provider(db: AsyncSession, user: User) -> Optional[ClinicalProvider]:
    return (
        await db.execute(select(ClinicalProvider).where(ClinicalProvider.user_id == user.id))
    ).scalar_one_or_none()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = await db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    coach_id = None
    provider_id = None

    if payload.session_type in ("coaching", "prayer"):
        if current_user.role == UserRole.platform_admin:
            coach_id = client.coach_id
        else:
            coach = await _get_own_coach(db, current_user)
            if coach is None or client.coach_id != coach.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the client's assigned coach (or an admin) can schedule this session",
                )
            coach_id = coach.id
    elif payload.session_type == "clinical":
        if current_user.role == UserRole.platform_admin:
            pass  # admin may schedule without an accepted referral on file (e.g. backfilling)
        else:
            provider = await _get_own_provider(db, current_user)
            if provider is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only a clinical provider (or an admin) can schedule a clinical session",
                )
            accepted = await db.execute(
                select(Referral).where(
                    Referral.client_id == payload.client_id,
                    Referral.provider_id == provider.id,
                    Referral.status == ReferralStatus.accepted,
                )
            )
            if accepted.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No accepted referral links this provider to this client",
                )
            provider_id = provider.id

    session = SessionRecord(
        client_id=payload.client_id,
        coach_id=coach_id,
        provider_id=provider_id,
        session_type=payload.session_type,
        scheduled_at=payload.scheduled_at,
        status="scheduled",
    )
    db.add(session)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="session.scheduled",
        resource_type="sessions",
        resource_id=str(session.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    client_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Role-scoped: a client sees their own sessions; a coach/provider sees sessions assigned to them."""
    stmt = select(SessionRecord)

    if current_user.role == UserRole.client:
        client = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalar_one_or_none()
        if client is None:
            return []
        stmt = stmt.where(SessionRecord.client_id == client.id)
    elif current_user.role == UserRole.coach:
        coach = await _get_own_coach(db, current_user)
        if coach is None:
            return []
        stmt = stmt.where(SessionRecord.coach_id == coach.id)
    elif current_user.role == UserRole.provider:
        provider = await _get_own_provider(db, current_user)
        if provider is None:
            return []
        stmt = stmt.where(SessionRecord.provider_id == provider.id)
    elif current_user.role == UserRole.platform_admin:
        if client_id is not None:
            stmt = stmt.where(SessionRecord.client_id == client_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to list sessions")

    sessions = (await db.execute(stmt)).scalars().all()
    return [_to_response(s) for s in sessions]


async def _authorize_session_leader(db: AsyncSession, current_user: User, session: SessionRecord) -> None:
    if current_user.role == UserRole.platform_admin:
        return
    if current_user.role == UserRole.coach:
        coach = await _get_own_coach(db, current_user)
        if coach is not None and session.coach_id == coach.id:
            return
    if current_user.role == UserRole.provider:
        provider = await _get_own_provider(db, current_user)
        if provider is not None and session.provider_id == provider.id:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the leader of this session")


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: UUID,
    payload: SessionUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(SessionRecord, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await _authorize_session_leader(db, current_user, session)

    if payload.status is not None:
        session.status = payload.status
    if payload.scheduled_at is not None:
        session.scheduled_at = payload.scheduled_at

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="session.updated",
        resource_type="sessions",
        resource_id=str(session.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(session)


@router.post("/{session_id}/notes", response_model=SessionNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_session_note(
    session_id: UUID,
    payload: SessionNoteCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(SessionRecord, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await _authorize_session_leader(db, current_user, session)

    if payload.note_type == "clinical" and current_user.role not in (UserRole.provider, UserRole.platform_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a clinical provider (or an admin) may write a clinical note",
        )

    note = SessionNote(
        session_id=session.id,
        note_type=payload.note_type,
        encrypted_content=payload.content,
        created_by=current_user.id,
    )
    db.add(note)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="session_note.created",
        resource_type="session_notes",
        resource_id=str(note.id),
        phi_accessed=True,
    )
    await db.commit()
    return SessionNoteResponse(
        note_id=note.id,
        session_id=note.session_id,
        note_type=note.note_type,
        content=note.encrypted_content,
        created_by=note.created_by,
        created_at=note.created_at,
    )


@router.get("/{session_id}/notes", response_model=list[SessionNoteResponse])
async def list_session_notes(
    session_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(SessionRecord, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    client = await db.get(Client, session.client_id)
    is_owning_client = current_user.role == UserRole.client and client is not None and client.user_id == current_user.id
    is_admin = current_user.role == UserRole.platform_admin

    is_session_coach = False
    if current_user.role == UserRole.coach:
        coach = await _get_own_coach(db, current_user)
        is_session_coach = coach is not None and session.coach_id == coach.id

    is_session_provider = False
    if current_user.role == UserRole.provider:
        provider = await _get_own_provider(db, current_user)
        is_session_provider = provider is not None and session.provider_id == provider.id

    if not (is_owning_client or is_admin or is_session_coach or is_session_provider):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this session")

    notes = (
        await db.execute(select(SessionNote).where(SessionNote.session_id == session_id))
    ).scalars().all()

    # note_type=clinical is never visible to a coach — readable only by the
    # treating provider, the owning client, and platform admins.
    visible = [
        n
        for n in notes
        if n.note_type != "clinical" or is_owning_client or is_admin or is_session_provider
    ]

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="session_notes.viewed",
        resource_type="session_notes",
        resource_id=str(session_id),
        phi_accessed=True,
    )
    await db.commit()

    return [
        SessionNoteResponse(
            note_id=n.id,
            session_id=n.session_id,
            note_type=n.note_type,
            content=n.encrypted_content,
            created_by=n.created_by,
            created_at=n.created_at,
        )
        for n in visible
    ]
