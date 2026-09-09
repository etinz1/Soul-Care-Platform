from sqlalchemy import select

from app.models import Client, ScriptureDelivery, User, UserRole
from app.schemas import PresentingConcern
from app.security import hash_password
from app.services import scripture_engine


async def _make_client(db_session, email="scripture-engine-client@example.com"):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=UserRole.client)
    db_session.add(user)
    await db_session.flush()
    client_row = Client(user_id=user.id)
    db_session.add(client_row)
    await db_session.commit()
    await db_session.refresh(client_row)
    return client_row


async def test_dispatch_returns_cards_for_matching_tags(db_session):
    client_row = await _make_client(db_session)
    result = await scripture_engine.dispatch(
        db_session,
        client_id=client_row.id,
        presenting_concerns=[PresentingConcern.grief, PresentingConcern.anxiety],
        intake_id=None,
    )
    refs = {card.reference for card in result.cards_for_response}
    assert "Matthew 5:4" in refs
    assert "Philippians 4:6-7" in refs
    assert result.queued_for_async_delivery is True


async def test_dispatch_deduplicates_repeated_tags(db_session):
    client_row = await _make_client(db_session, "scripture-engine-dedupe@example.com")
    result = await scripture_engine.dispatch(
        db_session,
        client_id=client_row.id,
        presenting_concerns=[PresentingConcern.grief, PresentingConcern.grief],
        intake_id=None,
    )
    assert len(result.cards_for_response) == 1


async def test_suppress_synchronous_display_hides_cards_but_still_queues(db_session):
    client_row = await _make_client(db_session, "scripture-engine-suppress@example.com")
    result = await scripture_engine.dispatch(
        db_session,
        client_id=client_row.id,
        presenting_concerns=[PresentingConcern.grief],
        intake_id=None,
        suppress_synchronous_display=True,
    )
    assert result.cards_for_response == []
    assert result.queued_for_async_delivery is True


async def test_no_concerns_returns_no_cards(db_session):
    client_row = await _make_client(db_session, "scripture-engine-none@example.com")
    result = await scripture_engine.dispatch(
        db_session, client_id=client_row.id, presenting_concerns=[], intake_id=None
    )
    assert result.cards_for_response == []
    assert result.queued_for_async_delivery is False


async def test_dispatch_persists_a_delivery_row_per_card(db_session):
    """This is the gap a codebase audit found: `queued_for_async_delivery=True`
    used to be a promise with nothing behind it — _enqueue_delivery_job was a
    no-op. Now it should actually be retrievable — see test_scripture.py for
    the API-level version of this."""
    client_row = await _make_client(db_session, "scripture-engine-persist@example.com")
    await scripture_engine.dispatch(
        db_session,
        client_id=client_row.id,
        presenting_concerns=[PresentingConcern.grief, PresentingConcern.anxiety],
        intake_id=None,
    )
    await db_session.commit()

    deliveries = (
        (await db_session.execute(select(ScriptureDelivery).where(ScriptureDelivery.client_id == client_row.id)))
        .scalars()
        .all()
    )
    assert len(deliveries) == 2
    assert all(d.channel == "dashboard" for d in deliveries)
    assert all(d.delivered_at is not None for d in deliveries)


async def test_suppressed_card_is_still_persisted(db_session):
    """The module's stated design: an imminent hard-stop hides cards from the
    synchronous response but still queues them. Verify the queue is real."""
    client_row = await _make_client(db_session, "scripture-engine-suppressed-persist@example.com")
    await scripture_engine.dispatch(
        db_session,
        client_id=client_row.id,
        presenting_concerns=[PresentingConcern.grief],
        intake_id=None,
        suppress_synchronous_display=True,
    )
    await db_session.commit()

    deliveries = (
        (await db_session.execute(select(ScriptureDelivery).where(ScriptureDelivery.client_id == client_row.id)))
        .scalars()
        .all()
    )
    assert len(deliveries) == 1


async def test_repeated_dispatch_reuses_existing_scripture_content_row(db_session):
    """_get_or_create_content should not create duplicate ScriptureContent
    rows across multiple dispatches for the same reference."""
    from app.models import ScriptureContent

    client_row = await _make_client(db_session, "scripture-engine-reuse@example.com")
    await scripture_engine.dispatch(
        db_session, client_id=client_row.id, presenting_concerns=[PresentingConcern.grief], intake_id=None
    )
    await scripture_engine.dispatch(
        db_session, client_id=client_row.id, presenting_concerns=[PresentingConcern.grief], intake_id=None
    )
    await db_session.commit()

    content_rows = (
        (await db_session.execute(select(ScriptureContent).where(ScriptureContent.reference == "Matthew 5:4")))
        .scalars()
        .all()
    )
    assert len(content_rows) == 1

    deliveries = (
        (await db_session.execute(select(ScriptureDelivery).where(ScriptureDelivery.client_id == client_row.id)))
        .scalars()
        .all()
    )
    assert len(deliveries) == 2  # one delivery per dispatch, sharing the one content row
