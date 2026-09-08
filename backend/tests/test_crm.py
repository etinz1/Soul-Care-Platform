from datetime import datetime, timedelta

from app.models import (
    Client,
    Coach,
    IntakeAssessment,
    IntakeStatus,
    PrayerRequest,
    SessionNote,
    SessionRecord,
    User,
    UserRole,
)
from app.security import create_access_token, hash_password


async def _make_user(db_session, email, role):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_coach_and_client(db_session, coach_email="coach@example.com", client_email="client@example.com"):
    coach_user = await _make_user(db_session, coach_email, UserRole.coach)
    coach = Coach(user_id=coach_user.id)
    db_session.add(coach)
    await db_session.flush()

    client_user = await _make_user(db_session, client_email, UserRole.client)
    client_row = Client(user_id=client_user.id, coach_id=coach.id)
    db_session.add(client_row)
    await db_session.commit()
    await db_session.refresh(coach)
    await db_session.refresh(client_row)
    return coach_user, coach, client_user, client_row


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def test_coach_sees_only_own_roster(client, db_session):
    coach_user, coach, _client_user, client_row = await _make_coach_and_client(db_session)
    other_coach_user = await _make_user(db_session, "other-coach@example.com", UserRole.coach)

    roster = await client.get("/api/v1/crm/clients", headers=_auth(coach_user))
    assert roster.status_code == 200
    assert len(roster.json()) == 1
    assert roster.json()[0]["client_id"] == str(client_row.id)
    # The roster carries the client's email so a coach caseload screen has
    # something human-readable to show — ClientRosterEntry/ClientSummaryResponse
    # otherwise expose no identifying detail at all.
    assert roster.json()[0]["email"] == "client@example.com"

    empty_roster = await client.get("/api/v1/crm/clients", headers=_auth(other_coach_user))
    assert empty_roster.json() == []


async def test_summary_denied_to_unaffiliated_coach_and_client_role(client, db_session):
    coach_user, _coach, client_user, client_row = await _make_coach_and_client(db_session)
    other_coach_user = await _make_user(db_session, "other-coach2@example.com", UserRole.coach)

    denied = await client.get(f"/api/v1/crm/clients/{client_row.id}/summary", headers=_auth(other_coach_user))
    assert denied.status_code == 403

    # The CRM view is coach/admin-only — not even the client themselves can pull it.
    client_denied = await client.get(f"/api/v1/crm/clients/{client_row.id}/summary", headers=_auth(client_user))
    assert client_denied.status_code == 403

    allowed = await client.get(f"/api/v1/crm/clients/{client_row.id}/summary", headers=_auth(coach_user))
    assert allowed.status_code == 200
    assert allowed.json()["email"] == client_user.email


async def test_summary_excludes_clinical_notes_and_scores(client, db_session):
    coach_user, coach, _client_user, client_row = await _make_coach_and_client(db_session)
    admin_user = await _make_user(db_session, "admin@example.com", UserRole.platform_admin)

    intake = IntakeAssessment(
        client_id=client_row.id,
        status=IntakeStatus.submitted,
        submitted_at=datetime.utcnow(),
        distress_level=6,
        phq9_score=15,
        gad7_score=10,
        presenting_concerns=["anxiety", "grief"],
        protective_factors=["strong faith community"],
    )
    db_session.add(intake)
    await db_session.flush()

    session = SessionRecord(
        client_id=client_row.id, coach_id=coach.id, session_type="coaching", scheduled_at=datetime.utcnow(), status="completed"
    )
    db_session.add(session)
    await db_session.flush()

    progress_note = SessionNote(
        session_id=session.id, note_type="progress", encrypted_content="Doing well.", created_by=coach_user.id
    )
    # A clinical note shouldn't exist on a coaching session in practice, but
    # add one directly (as an admin might via the API) to prove the
    # exclusion filter actually works rather than relying on it never
    # occurring.
    clinical_note = SessionNote(
        session_id=session.id, note_type="clinical", encrypted_content="Should never surface here.", created_by=admin_user.id
    )
    db_session.add_all([progress_note, clinical_note])
    await db_session.commit()

    summary = await client.get(f"/api/v1/crm/clients/{client_row.id}/summary", headers=_auth(coach_user))
    assert summary.status_code == 200
    body = summary.json()

    assert body["presenting_concerns"] == ["anxiety", "grief"]
    assert body["protective_factors"] == ["strong faith community"]
    assert body["distress_level"] == 6
    # No PHQ-9/GAD-7 field is even present in the response schema.
    assert "phq9_score" not in body
    assert "gad7_score" not in body

    note_types = [n["note_type"] for n in body["recent_session_notes"]]
    assert "progress" in note_types
    assert "clinical" not in note_types
    assert body["completed_sessions_count"] == 1


async def test_open_prayer_requests_counted_in_summary(client, db_session):
    coach_user, _coach, _client_user, client_row = await _make_coach_and_client(db_session)

    db_session.add(PrayerRequest(client_id=client_row.id, request_text="Pray for me.", urgency="routine", status="open"))
    db_session.add(PrayerRequest(client_id=client_row.id, request_text="Closed one.", urgency="routine", status="closed"))
    await db_session.commit()

    summary = await client.get(f"/api/v1/crm/clients/{client_row.id}/summary", headers=_auth(coach_user))
    assert summary.json()["open_prayer_requests_count"] == 1


async def test_crm_notes_create_and_list_restricted_to_coach_and_admin(client, db_session):
    coach_user, _coach, client_user, client_row = await _make_coach_and_client(db_session)
    other_coach_user = await _make_user(db_session, "other-coach3@example.com", UserRole.coach)
    admin_user = await _make_user(db_session, "admin2@example.com", UserRole.platform_admin)

    denied = await client.post(
        f"/api/v1/crm/clients/{client_row.id}/notes",
        headers=_auth(other_coach_user),
        json={"content": "Should not be allowed."},
    )
    assert denied.status_code == 403

    created = await client.post(
        f"/api/v1/crm/clients/{client_row.id}/notes",
        headers=_auth(coach_user),
        json={"content": "Left a voicemail, will follow up Thursday."},
    )
    assert created.status_code == 201, created.text
    assert created.json()["coach_id"] is not None

    admin_created = await client.post(
        f"/api/v1/crm/clients/{client_row.id}/notes",
        headers=_auth(admin_user),
        json={"content": "Admin follow-up note."},
    )
    assert admin_created.status_code == 201

    notes = await client.get(f"/api/v1/crm/clients/{client_row.id}/notes", headers=_auth(coach_user))
    assert len(notes.json()) == 2

    # A client cannot read their own coach's CRM notes about them.
    client_denied = await client.get(f"/api/v1/crm/clients/{client_row.id}/notes", headers=_auth(client_user))
    assert client_denied.status_code == 403
