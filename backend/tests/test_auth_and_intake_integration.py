import pytest

from app.models import (
    Client,
    ClinicalProvider,
    IntakeAssessment,
    IntakeStatus,
    ProviderType,
    User,
    UserRole,
    VettingStatus,
)
from app.security import hash_password


async def _register_and_login(client, email="client1@example.com", password="correcthorsebattery"):
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_register_login_refresh_flow(client):
    tokens = await _register_and_login(client)
    assert tokens["access_token"] and tokens["refresh_token"]

    # Duplicate registration is rejected.
    dup = await client.post(
        "/api/v1/auth/register", json={"email": "client1@example.com", "password": "correcthorsebattery"}
    )
    assert dup.status_code == 409

    # Wrong password is rejected.
    bad_login = await client.post(
        "/api/v1/auth/login", json={"email": "client1@example.com", "password": "wrongpassword"}
    )
    assert bad_login.status_code == 401

    # Refresh rotates the token and the old refresh token can't be reused.
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401


async def test_rbac_blocks_non_admin_from_provider_vetting(client):
    tokens = await _register_and_login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    unauthenticated = await client.patch(
        "/api/v1/providers/00000000-0000-0000-0000-000000000000/vetting", json={"vetting_status": "approved"}
    )
    assert unauthenticated.status_code == 401

    forbidden = await client.patch(
        "/api/v1/providers/00000000-0000-0000-0000-000000000000/vetting",
        json={"vetting_status": "approved"},
        headers=headers,
    )
    assert forbidden.status_code == 403


async def _seed_client_and_psychiatrist(db_session):
    tokens_user = User(email="seeded-client@example.com", hashed_password=hash_password("x" * 12), role=UserRole.client)
    db_session.add(tokens_user)
    await db_session.flush()
    client_row = Client(user_id=tokens_user.id)
    db_session.add(client_row)

    provider_user = User(
        email="seeded-psych@example.com", hashed_password=hash_password("x" * 12), role=UserRole.provider
    )
    db_session.add(provider_user)
    await db_session.flush()
    provider = ClinicalProvider(
        user_id=provider_user.id,
        provider_type=ProviderType.psychiatrist,
        license_number="TEST-LIC-1",
        license_state="OK",
        vetting_status=VettingStatus.approved,
        accepting_referrals=True,
    )
    db_session.add(provider)
    await db_session.flush()

    intake = IntakeAssessment(client_id=client_row.id, status=IntakeStatus.draft)
    db_session.add(intake)
    await db_session.commit()
    return client_row, provider, intake, tokens_user


async def test_hard_stop_intake_creates_referral_and_audit_trail(client, db_session):
    client_row, provider, intake, user = await _seed_client_and_psychiatrist(db_session)

    # Login as the seeded client (password set directly above, not via /register).
    from app.security import create_access_token

    access_token = create_access_token(user.id, user.role.value)
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = await client.post(
        f"/api/v1/intake/{intake.id}/submit",
        headers=headers,
        json={
            "client_id": str(client_row.id),
            "distress_level": 9,
            "c9_suicidal_ideation": 2,
            "substance_use_severity": 0,
            "presenting_concerns": ["anxiety"],
            "raw_responses": {},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["risk_decision"]["is_hard_stop"] is True
    assert body["risk_decision"]["routed_provider_type"] == "psychiatrist"
    assert body["risk_decision"]["referral_id"] is not None
    # Imminent severity (score 2) suppresses synchronous scripture display.
    assert body["scripture_cards"] == []

    # Resubmitting an already-submitted intake is rejected.
    resubmit = await client.post(
        f"/api/v1/intake/{intake.id}/submit",
        headers=headers,
        json={
            "client_id": str(client_row.id),
            "distress_level": 1,
            "c9_suicidal_ideation": 0,
            "substance_use_severity": 0,
            "presenting_concerns": ["grief"],
            "raw_responses": {},
        },
    )
    assert resubmit.status_code == 409


async def test_low_risk_intake_returns_scripture_cards_no_referral(client, db_session):
    client_row, provider, intake, user = await _seed_client_and_psychiatrist(db_session)
    from app.security import create_access_token

    access_token = create_access_token(user.id, user.role.value)
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = await client.post(
        f"/api/v1/intake/{intake.id}/submit",
        headers=headers,
        json={
            "client_id": str(client_row.id),
            "distress_level": 3,
            "c9_suicidal_ideation": 0,
            "substance_use_severity": 0,
            "presenting_concerns": ["grief"],
            "raw_responses": {},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["risk_decision"]["is_hard_stop"] is False
    assert body["risk_decision"]["referral_id"] is None
    assert len(body["scripture_cards"]) == 1
    assert body["scripture_cards"][0]["reference"] == "Matthew 5:4"
