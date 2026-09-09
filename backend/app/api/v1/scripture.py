"""
Client-facing retrieval of scripture content queued by the automation
engine (services/scripture_engine.py) during intake submission.

This is the "still queues for later delivery via the dashboard" half of
that module's design — see its docstring. Without an endpoint to read
`scripture_deliveries` back, content queued during an imminent-severity
hard-stop (where the synchronous intake response deliberately hides the
cards) would never actually reach the client. This endpoint, plus the
"Scripture" section on the client dashboard that calls it, is what closes
that loop.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_role
from app.db import get_db_session
from app.models import Client, ScriptureContent, ScriptureDelivery, User, UserRole
from app.schemas import ScriptureDeliveryResponse

router = APIRouter(prefix="/scripture", tags=["scripture"])


@router.get("/deliveries", response_model=list[ScriptureDeliveryResponse])
async def list_my_scripture_deliveries(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.client)),
):
    """A client's own scripture deliveries, most recent first. Client-only
    for now — this is dashboard content, not a clinical record a coach or
    admin has a stated need to review."""
    client = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalar_one_or_none()
    if client is None:
        return []

    stmt = (
        select(ScriptureDelivery, ScriptureContent)
        .join(ScriptureContent, ScriptureDelivery.scripture_content_id == ScriptureContent.id)
        .where(ScriptureDelivery.client_id == client.id)
        .order_by(ScriptureDelivery.delivered_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ScriptureDeliveryResponse(
            delivery_id=delivery.id,
            reference=content.reference,
            verse_text=content.verse_text,
            reflection_text=content.reflection_text,
            translation=content.translation,
            channel=delivery.channel,
            delivered_at=delivery.delivered_at,
        )
        for delivery, content in rows
    ]
