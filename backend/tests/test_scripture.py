"""
API-level tests for GET /scripture/deliveries — the endpoint that closes the
gap found in a codebase audit: scripture content queued during intake
submission (services/scripture_engine.py) had no way to be read back, so it
never actually reached a client after the one-time intake confirmation
screen. See test_scripture_engine.py for the unit-level persistence tests.
"""


async def _register(client, email="scripture-client@example.com"):
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorsebattery"})
    tokens = resp.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = await client.get("/api/v1/clients/me", headers=headers)
    return headers, me.json()["client_id"]


async def _submit_intake(client, headers, client_id, presenting_concerns, c9=0):
    created = await client.post("/api/v1/intake", headers=headers, json={"client_id": client_id})
    intake_id = created.json()["intake_id"]
    return await client.post(
        f"/api/v1/intake/{intake_id}/submit",
        headers=headers,
        json={
            "client_id": client_id,
            "distress_level": 3,
            "c9_suicidal_ideation": c9,
            "substance_use_severity": 0,
            "presenting_concerns": presenting_concerns,
            "protective_factors": [],
            "raw_responses": {},
        },
    )


async def test_deliveries_empty_before_any_intake(client):
    headers, _client_id = await _register(client)
    resp = await client.get("/api/v1/scripture/deliveries", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_deliveries_appear_after_low_risk_submit(client):
    headers, client_id = await _register(client, "scripture-low-risk@example.com")
    submitted = await _submit_intake(client, headers, client_id, ["grief"])
    assert submitted.status_code == 200

    resp = await client.get("/api/v1/scripture/deliveries", headers=headers)
    assert resp.status_code == 200
    deliveries = resp.json()
    assert len(deliveries) == 1
    assert deliveries[0]["reference"] == "Matthew 5:4"
    assert deliveries[0]["channel"] == "dashboard"


async def test_suppressed_cards_are_still_retrievable_after_hard_stop(client):
    """The exact gap the audit flagged: an imminent-severity hard-stop hides
    scripture from the synchronous response, but the client should still be
    able to see it afterward on their dashboard."""
    headers, client_id = await _register(client, "scripture-hard-stop@example.com")
    submitted = await _submit_intake(client, headers, client_id, ["anxiety"], c9=2)
    assert submitted.status_code == 200
    assert submitted.json()["scripture_cards"] == []  # suppressed synchronously

    resp = await client.get("/api/v1/scripture/deliveries", headers=headers)
    assert resp.status_code == 200
    deliveries = resp.json()
    assert len(deliveries) == 1
    assert deliveries[0]["reference"] == "Philippians 4:6-7"


async def test_a_client_only_sees_their_own_deliveries(client):
    headers_a, client_id_a = await _register(client, "scripture-a@example.com")
    headers_b, _client_id_b = await _register(client, "scripture-b@example.com")

    await _submit_intake(client, headers_a, client_id_a, ["grief"])

    resp_b = await client.get("/api/v1/scripture/deliveries", headers=headers_b)
    assert resp_b.json() == []

    resp_a = await client.get("/api/v1/scripture/deliveries", headers=headers_a)
    assert len(resp_a.json()) == 1


async def test_non_client_role_cannot_list_deliveries(client, db_session):
    from app.models import User, UserRole
    from app.security import create_access_token, hash_password

    coach_user = User(email="scripture-coach@example.com", hashed_password=hash_password("x" * 12), role=UserRole.coach)
    db_session.add(coach_user)
    await db_session.commit()
    await db_session.refresh(coach_user)

    headers = {"Authorization": f"Bearer {create_access_token(coach_user.id, coach_user.role.value)}"}
    resp = await client.get("/api/v1/scripture/deliveries", headers=headers)
    assert resp.status_code == 403
