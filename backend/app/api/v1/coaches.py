"""
Coach provisioning — admin-only, closing a gap left open by
RegisterRequest's docstring (ARCHITECTURE.md §7): unlike clients
(self-register) and clinical providers (self-onboard through vetting),
coaches previously had no API-reachable creation path at all, which meant
an admin had no way to give a coach account to someone, and no way to see
which coaches exist when assigning a client to one (PATCH
/clients/{id}/assignment). This mirrors the read/create posture of
api/v1/church.py's church provisioning, at the same small scope: creation
and listing only, no bio/certification editing UI yet.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import require_role
from app.db import get_db_session
from app.models import Coach, User, UserRole
from app.schemas import CoachCreateRequest, CoachResponse
from app.security import hash_password

router = APIRouter(prefix="/coaches", tags=["coaches"])


@router.post("", response_model=CoachResponse, status_code=status.HTTP_201_CREATED)
async def create_coach(
    payload: CoachCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password), role=UserRole.coach)
    db.add(user)
    await db.flush()

    coach = Coach(user_id=user.id, bio=payload.bio, active=True)
    db.add(coach)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="coach.created",
        resource_type="coaches",
        resource_id=str(coach.id),
        phi_accessed=False,
    )
    await db.commit()
    return CoachResponse(coach_id=coach.id, email=user.email, bio=coach.bio, active=coach.active)


@router.get("", response_model=list[CoachResponse])
async def list_coaches(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    """Admin-only: every coach on the platform, so the client-assignment
    screen (PATCH /clients/{id}/assignment) has something to pick from."""
    coaches = (await db.execute(select(Coach))).scalars().all()
    if not coaches:
        return []

    user_ids = [c.user_id for c in coaches]
    users_by_id = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    }
    return [
        CoachResponse(
            coach_id=c.id,
            email=users_by_id[c.user_id].email if c.user_id in users_by_id else "",
            bio=c.bio,
            active=c.active,
        )
        for c in coaches
    ]
