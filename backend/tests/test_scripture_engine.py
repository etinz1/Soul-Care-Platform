import uuid

from app.schemas import PresentingConcern
from app.services import scripture_engine


def test_dispatch_returns_cards_for_matching_tags():
    result = scripture_engine.dispatch(
        client_id=uuid.uuid4(),
        presenting_concerns=[PresentingConcern.grief, PresentingConcern.anxiety],
        intake_id=uuid.uuid4(),
    )
    refs = {card.reference for card in result.cards_for_response}
    assert "Matthew 5:4" in refs
    assert "Philippians 4:6-7" in refs
    assert result.queued_for_async_delivery is True


def test_dispatch_deduplicates_repeated_tags():
    result = scripture_engine.dispatch(
        client_id=uuid.uuid4(),
        presenting_concerns=[PresentingConcern.grief, PresentingConcern.grief],
        intake_id=uuid.uuid4(),
    )
    assert len(result.cards_for_response) == 1


def test_suppress_synchronous_display_hides_cards_but_still_queues():
    result = scripture_engine.dispatch(
        client_id=uuid.uuid4(),
        presenting_concerns=[PresentingConcern.grief],
        intake_id=uuid.uuid4(),
        suppress_synchronous_display=True,
    )
    assert result.cards_for_response == []
    assert result.queued_for_async_delivery is True


def test_no_concerns_returns_no_cards():
    result = scripture_engine.dispatch(client_id=uuid.uuid4(), presenting_concerns=[], intake_id=uuid.uuid4())
    assert result.cards_for_response == []
    assert result.queued_for_async_delivery is False
