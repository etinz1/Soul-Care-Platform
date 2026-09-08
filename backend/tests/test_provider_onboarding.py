from app.models import User, UserRole
from app.security import create_access_token, hash_password


async def _make_admin(db_session) -> User:
    admin = User(email="admin@example.com", hashed_password=hash_password("x" * 12), role=UserRole.platform_admin)
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


def _auth_header(user: User) -> dict:
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


ONBOARD_PAYLOAD = {
    "email": "dr.psych@example.com",
    "password": "correcthorsebattery",
    "provider_type": "psychiatrist",
    "license_number": "OK-LIC-9001",
    "license_state": "ok",
    "npi_number": "1234567890",
}


async def test_onboard_creates_pending_non_accepting_provider(client):
    resp = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["vetting_status"] == "pending"
    assert body["accepting_referrals"] is False
    assert body["tokens"]["access_token"]
    # license_state is normalized to uppercase server-side
    provider_id = body["provider_id"]

    status_resp = await client.get(
        f"/api/v1/providers/{provider_id}/vetting-status",
        headers={"Authorization": f"Bearer {body['tokens']['access_token']}"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["license_state"] == "OK"


async def test_onboard_duplicate_email_conflicts(client):
    first = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    assert first.status_code == 201
    dup = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    assert dup.status_code == 409


async def test_onboard_invalid_provider_type_rejected(client):
    bad = dict(ONBOARD_PAYLOAD)
    bad["provider_type"] = "life_coach"
    resp = await client.post("/api/v1/providers/onboard", json=bad)
    assert resp.status_code == 422


async def test_vetting_status_not_visible_to_unrelated_user(client, db_session):
    onboard = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    provider_id = onboard.json()["provider_id"]

    other = await client.post(
        "/api/v1/auth/register", json={"email": "someone-else@example.com", "password": "correcthorsebattery"}
    )
    other_token = other.json()["access_token"]

    resp = await client.get(
        f"/api/v1/providers/{provider_id}/vetting-status",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


async def test_list_providers_is_admin_only(client, db_session):
    onboard = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    provider_token = onboard.json()["tokens"]["access_token"]

    forbidden = await client.get(
        "/api/v1/providers", headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert forbidden.status_code == 403

    admin = await _make_admin(db_session)
    allowed = await client.get("/api/v1/providers", headers=_auth_header(admin))
    assert allowed.status_code == 200
    assert len(allowed.json()) == 1
    assert allowed.json()[0]["vetting_status"] == "pending"


async def test_admin_can_approve_provider(client, db_session):
    onboard = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    provider_id = onboard.json()["provider_id"]

    admin = await _make_admin(db_session)
    approve = await client.patch(
        f"/api/v1/providers/{provider_id}/vetting",
        json={"vetting_status": "approved", "accepting_referrals": True},
        headers=_auth_header(admin),
    )
    assert approve.status_code == 200
    body = approve.json()
    assert body["vetting_status"] == "approved"
    assert body["accepting_referrals"] is True


async def test_accepting_referrals_forced_false_unless_approved(client, db_session):
    onboard = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    provider_id = onboard.json()["provider_id"]

    admin = await _make_admin(db_session)
    # Caller asks for accepting_referrals=True while rejecting — server must not honor that.
    resp = await client.patch(
        f"/api/v1/providers/{provider_id}/vetting",
        json={"vetting_status": "rejected", "accepting_referrals": True},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["accepting_referrals"] is False


async def test_provider_can_fetch_own_profile_via_me(client):
    """GET /providers/me lets a provider discover their own provider_id and
    vetting status right after login, without already knowing provider_id —
    the self-service equivalent of GET /clients/me."""
    onboard = await client.post("/api/v1/providers/onboard", json=ONBOARD_PAYLOAD)
    provider_id = onboard.json()["provider_id"]
    access_token = onboard.json()["tokens"]["access_token"]

    me = await client.get("/api/v1/providers/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["provider_id"] == provider_id
    assert body["email"] == ONBOARD_PAYLOAD["email"]
    assert body["vetting_status"] == "pending"
    assert body["accepting_referrals"] is False


async def test_providers_me_rejected_for_non_provider_role(client, db_session):
    admin = await _make_admin(db_session)
    resp = await client.get("/api/v1/providers/me", headers=_auth_header(admin))
    assert resp.status_code == 403
