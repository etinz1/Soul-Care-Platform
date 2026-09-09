"""
Scripture Automation Engine — maps intake presenting-concern tags to curated
scripture content and enqueues delivery.

Kept deliberately simple for the MVP: a static lookup table seeds
`scripture_tags` / `scripture_content` (see models.py); this module reads
from that table and hands back ScriptureCard payloads for the API response,
while also enqueueing an async delivery job (email/SMS/dashboard) so the
request/response cycle for /intake/{id}/submit stays fast.

Even a hard-stop risk routing does not suppress scripture delivery per the
requirement — a client in crisis still receives pastoral care content
alongside (not instead of) the clinical referral. The one exception encoded
below: an "imminent" severity suicidal-ideation result suppresses scripture
delivery in the synchronous response (the UI's full attention should go to
the crisis resources / referral confirmation) but still queues it for later
delivery via the dashboard — see GET /scripture/deliveries
(api/v1/scripture.py), which is how that queued content actually reaches
the client afterward.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScriptureContent, ScriptureDelivery, ScriptureTag
from app.schemas import PresentingConcern, ScriptureCard


# Placeholder seed content — replace with a reviewed, church-approved content
# library (ideally versioned and editable by ministry staff via an admin UI,
# not hardcoded) before launch.
_SCRIPTURE_LIBRARY: dict[str, list[ScriptureCard]] = {
    PresentingConcern.anxiety: [
        ScriptureCard(
            reference="Philippians 4:6-7",
            verse_text=(
                "Do not be anxious about anything, but in every situation, by prayer and "
                "petition, with thanksgiving, present your requests to God."
            ),
            reflection_text="God invites your anxiety into His presence rather than asking you to hide it.",
        )
    ],
    PresentingConcern.depression: [
        ScriptureCard(
            reference="Psalm 34:18",
            verse_text="The Lord is close to the brokenhearted and saves those who are crushed in spirit.",
            reflection_text="Nearness, not distance, is God's posture toward you in the heaviest seasons.",
        )
    ],
    PresentingConcern.grief: [
        ScriptureCard(
            reference="Matthew 5:4",
            verse_text="Blessed are those who mourn, for they will be comforted.",
            reflection_text="Grief is not a failure of faith — it is honored here.",
        )
    ],
    PresentingConcern.marital_conflict: [
        ScriptureCard(
            reference="Ephesians 4:32",
            verse_text="Be kind and compassionate to one another, forgiving each other, just as in Christ God forgave you.",
        )
    ],
    PresentingConcern.addiction_recovery: [
        ScriptureCard(
            reference="2 Corinthians 5:17",
            verse_text="Therefore, if anyone is in Christ, the new creation has come: The old has gone, the new is here!",
            reflection_text="Recovery and identity renewal are the same story here, not two separate ones.",
        )
    ],
    PresentingConcern.spiritual_dryness: [
        ScriptureCard(
            reference="Psalm 42:1",
            verse_text="As the deer pants for streams of water, so my soul pants for you, my God.",
        )
    ],
    PresentingConcern.trauma_history: [
        ScriptureCard(
            reference="Isaiah 41:10",
            verse_text="So do not fear, for I am with you; do not be dismayed, for I am your God.",
        )
    ],
    PresentingConcern.parenting: [
        ScriptureCard(
            reference="Proverbs 22:6",
            verse_text="Start children off on the way they should go, and even when they are old they will not turn from it.",
        )
    ],
    PresentingConcern.financial_stress: [
        ScriptureCard(
            reference="Philippians 4:19",
            verse_text="And my God will meet all your needs according to the riches of his glory in Christ Jesus.",
        )
    ],
    PresentingConcern.identity_purpose: [
        ScriptureCard(
            reference="Jeremiah 29:11",
            verse_text="For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you.",
        )
    ],
}


# Reverse lookup built once at import time: every card in the library above
# is defined under exactly one concern, so this is unambiguous. Used to
# get-or-create the right ScriptureTag when persisting a delivery.
_REFERENCE_TO_CONCERN: dict[str, PresentingConcern] = {
    card.reference: concern for concern, cards in _SCRIPTURE_LIBRARY.items() for card in cards
}


@dataclass
class ScriptureDispatchResult:
    cards_for_response: list[ScriptureCard]
    queued_for_async_delivery: bool


async def dispatch(
    db: AsyncSession,
    client_id: UUID,
    presenting_concerns: list[PresentingConcern],
    intake_id: UUID,
    suppress_synchronous_display: bool = False,
) -> ScriptureDispatchResult:
    """
    Resolve scripture cards for the given tags and persist a delivery record
    for each one so it can be retrieved later via GET /scripture/deliveries
    — this is what makes "queued for later delivery via the dashboard" (see
    module docstring) actually true, rather than just a boolean the caller
    trusts without evidence.

    `suppress_synchronous_display` is set by the API layer when the risk
    engine returned an imminent-severity hard stop, per the module docstring.
    It only affects what's returned in this response, never what's persisted
    — a suppressed card is still queued and still reaches the dashboard.

    Caller is responsible for committing `db` (this only flushes, matching
    the rest of the codebase's one-commit-per-request convention — see
    api/v1/intake.py's submit_intake, which calls this mid-transaction).
    """
    cards: list[ScriptureCard] = []
    seen_refs: set[str] = set()
    for concern in presenting_concerns:
        for card in _SCRIPTURE_LIBRARY.get(concern, []):
            if card.reference not in seen_refs:
                cards.append(card)
                seen_refs.add(card.reference)

    await _persist_deliveries(db, client_id=client_id, intake_id=intake_id, cards=cards)

    return ScriptureDispatchResult(
        cards_for_response=[] if suppress_synchronous_display else cards,
        queued_for_async_delivery=bool(cards),
    )


async def _get_or_create_content(db: AsyncSession, card: ScriptureCard) -> ScriptureContent:
    """Mirrors app/seed.py's seed_scripture() get-or-create logic, so a
    delivery can be persisted even against a database that hasn't been
    seeded yet (e.g. a fresh test DB) — the content becomes durable the
    first time it's actually dispatched, not only via the seed script."""
    existing = (
        await db.execute(select(ScriptureContent).where(ScriptureContent.reference == card.reference))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    concern = _REFERENCE_TO_CONCERN[card.reference]
    tag = (await db.execute(select(ScriptureTag).where(ScriptureTag.name == concern.value))).scalar_one_or_none()
    if tag is None:
        tag = ScriptureTag(name=concern.value)
        db.add(tag)
        await db.flush()

    content = ScriptureContent(
        tag_id=tag.id,
        reference=card.reference,
        verse_text=card.verse_text,
        reflection_text=card.reflection_text,
        translation=card.translation,
    )
    db.add(content)
    await db.flush()
    return content


async def _persist_deliveries(db: AsyncSession, client_id: UUID, intake_id: UUID, cards: list[ScriptureCard]) -> None:
    for card in cards:
        content = await _get_or_create_content(db, card)
        db.add(
            ScriptureDelivery(
                client_id=client_id,
                scripture_content_id=content.id,
                channel="dashboard",
                triggered_by_intake_id=intake_id,
                delivered_at=datetime.utcnow(),
            )
        )
    await db.flush()
