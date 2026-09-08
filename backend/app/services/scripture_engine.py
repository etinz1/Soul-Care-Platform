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
delivery via the dashboard.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

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


@dataclass
class ScriptureDispatchResult:
    cards_for_response: list[ScriptureCard]
    queued_for_async_delivery: bool


def dispatch(
    client_id: UUID,
    presenting_concerns: list[PresentingConcern],
    intake_id: UUID,
    suppress_synchronous_display: bool = False,
) -> ScriptureDispatchResult:
    """
    Resolve scripture cards for the given tags and enqueue async delivery.

    `suppress_synchronous_display` is set by the API layer when the risk
    engine returned an imminent-severity hard stop, per the module docstring.
    """
    cards: list[ScriptureCard] = []
    seen_refs: set[str] = set()
    for concern in presenting_concerns:
        for card in _SCRIPTURE_LIBRARY.get(concern, []):
            if card.reference not in seen_refs:
                cards.append(card)
                seen_refs.add(card.reference)

    _enqueue_delivery_job(client_id=client_id, intake_id=intake_id, cards=cards)

    return ScriptureDispatchResult(
        cards_for_response=[] if suppress_synchronous_display else cards,
        queued_for_async_delivery=bool(cards),
    )


def _enqueue_delivery_job(client_id: UUID, intake_id: UUID, cards: list[ScriptureCard]) -> None:
    """
    Placeholder for the Celery/RQ job that writes `scripture_deliveries` rows
    and dispatches via dashboard/email/SMS. Wired to the real task queue at
    the infrastructure layer — kept out of this module so risk/scripture
    logic stays testable without a broker running.
    """
    # e.g. celery_app.send_task("deliver_scripture", args=[str(client_id), str(intake_id), ...])
    pass
