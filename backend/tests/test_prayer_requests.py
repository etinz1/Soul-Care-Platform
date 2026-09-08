from app.models import Client, Coach, User, UserRole
from app.security import create_access_token, hash_password


async def _make_user(db_session, email, role):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_client_with_coach(db_session, coach_email="coach@example.com", client_email="client@example.com"):
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


async def _make_client_without_coach(db_session, email="lonely-client@example.com"):
    client_user = await _make_user(db_session, email, UserRole.client)
    client_row = Client(user_id=client_user.id)
    db_session.add(client_row)
    await db_session.commit()
    await db_session.refresh(client_row)
    return client_user, client_row


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def test_prayer_request_auto_assigns_to_clients_coach(client, db_session):
    coach_user, coach, client_user, client_row = await _make_client_with_coach(db_session)

    resp = await client.post(
        "/api/v1/scheduling/prayer-requests",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "request_text": "Please pray for my family.", "urgency": "routine"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["assigned_to"] == str(coach_user.id)
    assert body["status"] == "open"


async def test_prayer_request_unassigned_when_no_coach(client, db_session):
    client_user, client_row = await _make_client_without_coach(db_session)

    resp = await client.post(
        "/api/v1/scheduling/prayer-requests",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "request_text": "Urgent need.", "urgency": "immediate"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["assigned_to"] is None


async def test_cannot_submit_prayer_request_for_another_client(client, db_session):
    client_user, _client_row = await _make_client_without_coach(db_session, email="me@example.com")
    _other_user, other_client_row = await _make_client_without_coach(db_session, email="someone-else@example.com")

    resp = await client.post(
        "/api/v1/scheduling/prayer-requests",
        headers=_auth(client_user),
        json={"client_id": str(other_client_row.id), "request_text": "x", "urgency": "routine"},
    )
    assert resp.status_code == 403


async def test_role_scoped_listing_and_assignee_can_close(client, db_session):
    coach_user, _coach, client_user, client_row = await _make_client_with_coach(db_session)

    created = await client.post(
        "/api/v1/scheduling/prayer-requests",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "request_text": "Pray for healing.", "urgency": "urgent"},
    )
    prayer_request_id = created.json()["prayer_request_id"]

    client_list = await client.get("/api/v1/scheduling/prayer-requests", headers=_auth(client_user))
    assert len(client_list.json()) == 1

    coach_list = await client.get("/api/v1/scheduling/prayer-requests", headers=_auth(coach_user))
    assert len(coach_list.json()) == 1

    other_coach = await _make_user(db_session, "other-coach@example.com", UserRole.coach)
    other_coach_list = await client.get("/api/v1/scheduling/prayer-requests", headers=_auth(other_coach))
    assert other_coach_list.json() == []

    # An unrelated coach can't touch it...
    forbidden = await client.patch(
        f"/api/v1/scheduling/prayer-requests/{prayer_request_id}",
        headers=_auth(other_coach),
        json={"status": "closed"},
    )
    assert forbidden.status_code == 403

    # ...but the assigned coach can update status.
    closed = await client.patch(
        f"/api/v1/scheduling/prayer-requests/{prayer_request_id}",
        headers=_auth(coach_user),
        json={"status": "in_progress"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "in_progress"


async def test_only_admin_can_reassign(client, db_session):
    coach_user, _coach, client_user, client_row = await _make_client_with_coach(db_session)
    admin_user = await _make_user(db_session, "admin@example.com", UserRole.platform_admin)
    other_coach_user = await _make_user(db_session, "other-coach2@example.com", UserRole.coach)

    created = await client.post(
        "/api/v1/scheduling/prayer-requests",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "request_text": "Pray for peace.", "urgency": "routine"},
    )
    prayer_request_id = created.json()["prayer_request_id"]

    denied = await client.patch(
        f"/api/v1/scheduling/prayer-requests/{prayer_request_id}",
        headers=_auth(coach_user),
        json={"assigned_to": str(other_coach_user.id)},
    )
    assert denied.status_code == 403

    reassigned = await client.patch(
        f"/api/v1/scheduling/prayer-requests/{prayer_request_id}",
        headers=_auth(admin_user),
        json={"assigned_to": str(other_coach_user.id)},
    )
    assert reassigned.status_code == 200
    assert reassigned.json()["assigned_to"] == str(other_coach_user.id)
