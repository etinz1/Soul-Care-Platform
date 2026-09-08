from datetime import datetime, timedelta

from app.models import (
    Client,
    Coach,
    ClinicalProvider,
    ProviderType,
    Referral,
    ReferralStatus,
    RoiConsent,
    User,
    UserRole,
    VettingStatus,
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


async def _make_accepted_referral(db_session, client_row, provider_email="psych@example.com"):
    provider_user = await _make_user(db_session, provider_email, UserRole.provider)
    provider = ClinicalProvider(
        user_id=provider_user.id,
        provider_type=ProviderType.psychiatrist,
        license_number="LIC-SCHED-1",
        license_state="OK",
        vetting_status=VettingStatus.approved,
        accepting_referrals=True,
    )
    db_session.add(provider)
    await db_session.flush()

    consent = RoiConsent(
        client_id=client_row.id,
        discloses_to_provider_id=provider.id,
        scope={},
        signature_hash="test-hash",
    )
    db_session.add(consent)
    await db_session.flush()

    referral = Referral(
        client_id=client_row.id,
        provider_id=provider.id,
        consent_id=consent.id,
        status=ReferralStatus.accepted,
    )
    db_session.add(referral)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider_user, provider


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def test_coach_can_schedule_coaching_session_for_own_client(client, db_session):
    coach_user, coach, client_user, client_row = await _make_coach_and_client(db_session)

    resp = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(coach_user),
        json={
            "client_id": str(client_row.id),
            "session_type": "coaching",
            "scheduled_at": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["coach_id"] == str(coach.id)
    assert body["status"] == "scheduled"


async def test_coach_cannot_schedule_session_for_unassigned_client(db_session, client):
    coach_user, _coach, _client_user, _client_row = await _make_coach_and_client(
        db_session, coach_email="coach-a@example.com", client_email="client-a@example.com"
    )
    _other_coach, _other_coach_row, _other_client_user, other_client_row = await _make_coach_and_client(
        db_session, coach_email="coach-b@example.com", client_email="client-b@example.com"
    )

    resp = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(coach_user),
        json={
            "client_id": str(other_client_row.id),
            "session_type": "coaching",
            "scheduled_at": datetime.utcnow().isoformat(),
        },
    )
    assert resp.status_code == 403


async def test_clinical_session_requires_accepted_referral(client, db_session):
    _coach_user, _coach, _client_user, client_row = await _make_coach_and_client(db_session)
    provider_user, _provider = await _make_accepted_referral(db_session, client_row)

    resp = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(provider_user),
        json={
            "client_id": str(client_row.id),
            "session_type": "clinical",
            "scheduled_at": datetime.utcnow().isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["session_type"] == "clinical"


async def test_clinical_session_blocked_without_referral(client, db_session):
    _coach_user, _coach, _client_user, client_row = await _make_coach_and_client(db_session)
    other_provider_user = await _make_user(db_session, "no-referral-psych@example.com", UserRole.provider)
    provider = ClinicalProvider(
        user_id=other_provider_user.id,
        provider_type=ProviderType.psychiatrist,
        license_number="LIC-NOREF",
        license_state="OK",
        vetting_status=VettingStatus.approved,
        accepting_referrals=True,
    )
    db_session.add(provider)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(other_provider_user),
        json={
            "client_id": str(client_row.id),
            "session_type": "clinical",
            "scheduled_at": datetime.utcnow().isoformat(),
        },
    )
    assert resp.status_code == 400


async def test_role_scoped_listing_and_status_update(client, db_session):
    coach_user, coach, client_user, client_row = await _make_coach_and_client(db_session)

    created = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(coach_user),
        json={
            "client_id": str(client_row.id),
            "session_type": "coaching",
            "scheduled_at": datetime.utcnow().isoformat(),
        },
    )
    session_id = created.json()["session_id"]

    client_list = await client.get("/api/v1/scheduling/sessions", headers=_auth(client_user))
    assert len(client_list.json()) == 1

    coach_list = await client.get("/api/v1/scheduling/sessions", headers=_auth(coach_user))
    assert len(coach_list.json()) == 1

    other_coach_user = await _make_user(db_session, "other-coach@example.com", UserRole.coach)
    other_list = await client.get("/api/v1/scheduling/sessions", headers=_auth(other_coach_user))
    assert other_list.json() == []

    update = await client.patch(
        f"/api/v1/scheduling/sessions/{session_id}",
        headers=_auth(coach_user),
        json={"status": "completed"},
    )
    assert update.status_code == 200
    assert update.json()["status"] == "completed"

    forbidden_update = await client.patch(
        f"/api/v1/scheduling/sessions/{session_id}",
        headers=_auth(other_coach_user),
        json={"status": "cancelled"},
    )
    assert forbidden_update.status_code == 403


async def test_clinical_note_hidden_from_coach_but_visible_to_client_and_provider(client, db_session):
    coach_user, _coach, client_user, client_row = await _make_coach_and_client(db_session)
    provider_user, _provider = await _make_accepted_referral(db_session, client_row)

    session_resp = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(provider_user),
        json={
            "client_id": str(client_row.id),
            "session_type": "clinical",
            "scheduled_at": datetime.utcnow().isoformat(),
        },
    )
    session_id = session_resp.json()["session_id"]

    # A coach may not write a clinical note.
    coach_attempt = await client.post(
        f"/api/v1/scheduling/sessions/{session_id}/notes",
        headers=_auth(coach_user),
        json={"note_type": "clinical", "content": "should not be allowed"},
    )
    assert coach_attempt.status_code == 403

    clinical_note = await client.post(
        f"/api/v1/scheduling/sessions/{session_id}/notes",
        headers=_auth(provider_user),
        json={"note_type": "clinical", "content": "Clinical impression: stable."},
    )
    assert clinical_note.status_code == 201, clinical_note.text

    # The client can view it...
    client_view = await client.get(f"/api/v1/scheduling/sessions/{session_id}/notes", headers=_auth(client_user))
    assert len(client_view.json()) == 1

    # ...the provider can view it...
    provider_view = await client.get(f"/api/v1/scheduling/sessions/{session_id}/notes", headers=_auth(provider_user))
    assert len(provider_view.json()) == 1

    # ...but this coach has no relationship to this clinical session at all
    # (it wasn't scheduled through them), so they can't view it — a coach's
    # visibility never extends to a session's clinical notes.
    coach_view = await client.get(f"/api/v1/scheduling/sessions/{session_id}/notes", headers=_auth(coach_user))
    assert coach_view.status_code == 403


async def test_clinical_note_filtered_out_for_session_coach(client, db_session):
    """Even when a coach IS the leader of a session, a clinical note on it (e.g. added by
    an admin) is filtered out of what they see — the session_notes access rule in
    ARCHITECTURE.md §3 says clinical notes go to the provider + client + admin only,
    never the coach, regardless of who else is attached to the session."""
    coach_user, coach, client_user, client_row = await _make_coach_and_client(db_session)
    admin_user = await _make_user(db_session, "admin@example.com", UserRole.platform_admin)

    session_resp = await client.post(
        "/api/v1/scheduling/sessions",
        headers=_auth(coach_user),
        json={
            "client_id": str(client_row.id),
            "session_type": "coaching",
            "scheduled_at": datetime.utcnow().isoformat(),
        },
    )
    session_id = session_resp.json()["session_id"]

    await client.post(
        f"/api/v1/scheduling/sessions/{session_id}/notes",
        headers=_auth(coach_user),
        json={"note_type": "progress", "content": "Made progress this week."},
    )
    await client.post(
        f"/api/v1/scheduling/sessions/{session_id}/notes",
        headers=_auth(admin_user),
        json={"note_type": "clinical", "content": "Admin-entered clinical note."},
    )

    coach_view = await client.get(f"/api/v1/scheduling/sessions/{session_id}/notes", headers=_auth(coach_user))
    assert coach_view.status_code == 200
    note_types = [n["note_type"] for n in coach_view.json()]
    assert "progress" in note_types
    assert "clinical" not in note_types

    admin_view = await client.get(f"/api/v1/scheduling/sessions/{session_id}/notes", headers=_auth(admin_user))
    assert len(admin_view.json()) == 2
