"""
Coaching CRM — ARCHITECTURE.md §7 step 8, the last module in the suggested
MVP build sequence. Gives a coach an operational view of their own caseload
without ever surfacing clinical detail: no PHQ-9/GAD-7 scores, no raw
intake responses, no risk events, and no `note_type=clinical` session
notes (see ClientSummaryResponse's docstring in schemas.py — this is the
`/crm` route's own version of the "billing without clinical visibility"
principle applied to coaching).

`crm_notes` (api/v1/crm.py + the `CrmNote` model) is a new, independent
table from `session_notes`: a coach can log a caseload note ("left a
voicemail", "checking in Thursday") that isn't tied to any specific
scheduled session.
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
    CrmNote,
    IntakeAssessment,
    IntakeStatus,
    PrayerRequest,
    SessionNote,
    SessionRecord,
    User,
    UserRole,
)
from app.schemas import (
    ClientRosterEntry,
    ClientSummaryResponse,
    CrmNoteCreateRequest,
    CrmNoteResponse,
    SessionNoteResponse,
)

router = APIRouter(prefix="/crm", tags=["crm"])


async def _get_own_coach(db: AsyncSession, user: User) -> Optional[Coach]:
    return (await db.execute(select(Coach).where(Coach.user_id == user.id))).scalar_one_or_none()


async def _authorize_coach_or_admin_for_client(db: AsyncSession, current_user: User, client: Client) -> None:
    if current_user.role == UserRole.platform_admin:
        return
    if current_user.role == UserRole.coach:
        coach = await _get_own_coach(db, current_user)
        if coach is not None and client.coach_id == coach.id:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to access this client's CRM record")


@router.get("/clients", response_model=list[ClientRosterEntry])
async def list_my_clients(
    coach_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """A coach's own caseload roster; admin sees all (optionally filtered by coach_id)."""
    stmt = select(Client)

    if current_user.role == UserRole.coach:
        coach = await _get_own_coach(db, current_user)
        if coach is None:
            return []
        stmt = stmt.where(Client.coach_id == coach.id)
    elif current_user.role == UserRole.platform_admin:
        if coach_id is not None:
            stmt = stmt.where(Client.coach_id == coach_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to list CRM clients")

    clients = (await db.execute(stmt)).scalars().all()
    if not clients:
        return []

    user_ids = [c.user_id for c in clients]
    users_by_id = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    }
    return [
        ClientRosterEntry(
            client_id=c.id,
            email=users_by_id[c.user_id].email if c.user_id in users_by_id else "",
            coach_id=c.coach_id,
            church_sponsor_id=c.church_sponsor_id,
            created_at=c.created_at,
        )
        for c in clients
    ]


@router.get("/clients/{client_id}/summary", response_model=ClientSummaryResponse)
async def get_client_summary(
    client_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    await _authorize_coach_or_admin_for_client(db, current_user, client)

    client_user = await db.get(User, client.user_id)

    latest_intake = (
        await db.execute(
            select(IntakeAssessment)
            .where(IntakeAssessment.client_id == client_id, IntakeAssessment.status == IntakeStatus.submitted)
            .order_by(IntakeAssessment.submitted_at.desc())
        )
    ).scalars().first()

    sessions = (
        await db.execute(select(SessionRecord).where(SessionRecord.client_id == client_id))
    ).scalars().all()
    # Only sessions this coach actually leads are counted for a coach viewer
    # (an admin sees the client's full session count); a coach never learns
    # from this summary that a clinical session exists at all.
    if current_user.role == UserRole.coach:
        sessions = [s for s in sessions if s.coach_id is not None]
    upcoming = sum(1 for s in sessions if s.status == "scheduled")
    completed = sum(1 for s in sessions if s.status == "completed")

    session_ids = [s.id for s in sessions]
    recent_session_notes: list[SessionNoteResponse] = []
    if session_ids:
        notes = (
            await db.execute(
                select(SessionNote)
                .where(SessionNote.session_id.in_(session_ids), SessionNote.note_type != "clinical")
                .order_by(SessionNote.created_at.desc())
                .limit(20)
            )
        ).scalars().all()
        recent_session_notes = [
            SessionNoteResponse(
                note_id=n.id,
                session_id=n.session_id,
                note_type=n.note_type,
                content=n.encrypted_content,
                created_by=n.created_by,
                created_at=n.created_at,
            )
            for n in notes
        ]

    crm_notes = (
        await db.execute(
            select(CrmNote).where(CrmNote.client_id == client_id).order_by(CrmNote.created_at.desc()).limit(20)
        )
    ).scalars().all()

    open_prayer_count = len(
        (
            await db.execute(
                select(PrayerRequest).where(PrayerRequest.client_id == client_id, PrayerRequest.status == "open")
            )
        )
        .scalars()
        .all()
    )

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="crm.client_summary_viewed",
        resource_type="clients",
        resource_id=str(client_id),
        phi_accessed=True,
    )
    await db.commit()

    return ClientSummaryResponse(
        client_id=client.id,
        email=client_user.email if client_user is not None else "",
        coach_id=client.coach_id,
        church_sponsor_id=client.church_sponsor_id,
        created_at=client.created_at,
        latest_intake_submitted_at=latest_intake.submitted_at if latest_intake else None,
        presenting_concerns=latest_intake.presenting_concerns if latest_intake else [],
        protective_factors=latest_intake.protective_factors if latest_intake else [],
        distress_level=latest_intake.distress_level if latest_intake else None,
        upcoming_sessions_count=upcoming,
        completed_sessions_count=completed,
        open_prayer_requests_count=open_prayer_count,
        recent_session_notes=recent_session_notes,
        recent_crm_notes=[
            CrmNoteResponse(
                note_id=n.id,
                client_id=n.client_id,
                coach_id=n.coach_id,
                content=n.encrypted_content,
                created_by=n.created_by,
                created_at=n.created_at,
            )
            for n in crm_notes
        ],
    )


@router.post("/clients/{client_id}/notes", response_model=CrmNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_crm_note(
    client_id: UUID,
    payload: CrmNoteCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    await _authorize_coach_or_admin_for_client(db, current_user, client)

    note = CrmNote(
        client_id=client_id,
        coach_id=client.coach_id,
        encrypted_content=payload.content,
        created_by=current_user.id,
    )
    db.add(note)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="crm_note.created",
        resource_type="crm_notes",
        resource_id=str(note.id),
        phi_accessed=True,
    )
    await db.commit()
    return CrmNoteResponse(
        note_id=note.id,
        client_id=note.client_id,
        coach_id=note.coach_id,
        content=note.encrypted_content,
        created_by=note.created_by,
        created_at=note.created_at,
    )


@router.get("/clients/{client_id}/notes", response_model=list[CrmNoteResponse])
async def list_crm_notes(
    client_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    await _authorize_coach_or_admin_for_client(db, current_user, client)

    notes = (
        await db.execute(select(CrmNote).where(CrmNote.client_id == client_id).order_by(CrmNote.created_at.desc()))
    ).scalars().all()
    return [
        CrmNoteResponse(
            note_id=n.id,
            client_id=n.client_id,
            coach_id=n.coach_id,
            content=n.encrypted_content,
            created_by=n.created_by,
            created_at=n.created_at,
        )
        for n in notes
    ]
