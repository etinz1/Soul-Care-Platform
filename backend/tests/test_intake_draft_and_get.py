from app.models import Client, Coach, User, UserRole
from app.security import create_access_token, hash_password


async def _make_user(db_session, email, role):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def _register(client, email="draft-client@example.com"):
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorsebattery"})
    tokens = resp.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = await client.get("/api/v1/clients/me", headers=headers)
    return headers, me.json()["client_id"]


async def test_client_can_create_and_fetch_own_draft(client):
    headers, client_id = await _register(client)

    created = await client.post("/api/v1/intake", headers=headers, json={"client_id": client_id})
    assert created.status_code == 201, created.text
    intake_id = created.json()["intake_id"]
    assert created.json()["status"] == "draft"

    fetched = await client.get(f"/api/v1/intake/{intake_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "draft"
    assert fetched.json()["submitted_at"] is None


async def test_cannot_create_draft_for_another_client(client):
    headers_a, _client_id_a = await _register(client, "draft-a@example.com")
    _headers_b, client_id_b = await _register(client, "draft-b@example.com")

    resp = await client.post("/api/v1/intake", headers=headers_a, json={"client_id": client_id_b})
    assert resp.status_code == 403


async def test_full_draft_then_submit_flow(client):
    headers, client_id = await _register(client, "full-flow-client@example.com")

    created = await client.post("/api/v1/intake", headers=headers, json={"client_id": client_id})
    intake_id = created.json()["intake_id"]

    submitted = await client.post(
        f"/api/v1/intake/{intake_id}/submit",
        headers=headers,
        json={
            "client_id": client_id,
            "distress_level": 3,
            "c9_suicidal_ideation": 0,
            "substance_use_severity": 0,
            "presenting_concerns": ["anxiety"],
            "protective_factors": ["supportive family"],
            "raw_responses": {},
        },
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["risk_decision"]["is_hard_stop"] is False

    fetched = await client.get(f"/api/v1/intake/{intake_id}", headers=headers)
    assert fetched.json()["status"] == "submitted"
    assert fetched.json()["presenting_concerns"] == ["anxiety"]


async def test_get_intake_visible_to_own_coach_not_unrelated_coach(client, db_session):
    headers, client_id = await _register(client, "coach-visible-client@example.com")
    created = await client.post("/api/v1/intake", headers=headers, json={"client_id": client_id})
    intake_id = created.json()["intake_id"]

    coach_user = await _make_user(db_session, "assigned-coach@example.com", UserRole.coach)
    coach = Coach(user_id=coach_user.id)
    db_session.add(coach)
    await db_session.flush()

    client_row = await db_session.get(Client, client_id)
    client_row.coach_id = coach.id
    await db_session.commit()

    allowed = await client.get(f"/api/v1/intake/{intake_id}", headers=_auth(coach_user))
    assert allowed.status_code == 200

    other_coach = await _make_user(db_session, "unrelated-coach@example.com", UserRole.coach)
    denied = await client.get(f"/api/v1/intake/{intake_id}", headers=_auth(other_coach))
    assert denied.status_code == 403
