from app.models import Church, Client, Coach, User, UserRole
from app.security import create_access_token, hash_password


async def _make_user(db_session, email, role):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def test_register_creates_client_row_atomically(client):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "new-client@example.com", "password": "correcthorsebattery"}
    )
    assert resp.status_code == 201, resp.text
    tokens = resp.json()

    me = await client.get("/api/v1/clients/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["coach_id"] is None
    assert body["church_sponsor_id"] is None
    assert body["date_of_birth"] is None


async def test_client_can_update_own_profile(client):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "profile-client@example.com", "password": "correcthorsebattery"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    updated = await client.patch(
        "/api/v1/clients/me",
        headers=headers,
        json={"date_of_birth": "1990-01-01", "emergency_contact": "Jane Doe, 555-0100"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["date_of_birth"] == "1990-01-01"
    assert updated.json()["emergency_contact"] == "Jane Doe, 555-0100"

    empty_patch = await client.patch("/api/v1/clients/me", headers=headers, json={})
    assert empty_patch.status_code == 422


async def test_client_cannot_self_assign_coach_or_church(client, db_session):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "cant-self-assign@example.com", "password": "correcthorsebattery"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = await client.get("/api/v1/clients/me", headers=headers)
    client_id = me.json()["client_id"]

    coach_user = await _make_user(db_session, "some-coach@example.com", UserRole.coach)
    coach = Coach(user_id=coach_user.id)
    db_session.add(coach)
    await db_session.commit()
    await db_session.refresh(coach)

    # No such route/permission exists for a client — assignment is admin-only.
    denied = await client.patch(
        f"/api/v1/clients/{client_id}/assignment",
        headers=headers,
        json={"coach_id": str(coach.id)},
    )
    assert denied.status_code == 403


async def test_admin_can_assign_coach_and_church(client, db_session):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "assignable-client@example.com", "password": "correcthorsebattery"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = await client.get("/api/v1/clients/me", headers=headers)
    client_id = me.json()["client_id"]

    admin_user = await _make_user(db_session, "assign-admin@example.com", UserRole.platform_admin)
    coach_user = await _make_user(db_session, "assign-coach@example.com", UserRole.coach)
    coach = Coach(user_id=coach_user.id)
    church = Church(name="Assignment Test Church")
    db_session.add_all([coach, church])
    await db_session.commit()
    await db_session.refresh(coach)
    await db_session.refresh(church)

    assigned = await client.patch(
        f"/api/v1/clients/{client_id}/assignment",
        headers=_auth(admin_user),
        json={"coach_id": str(coach.id), "church_sponsor_id": str(church.id)},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["coach_id"] == str(coach.id)
    assert assigned.json()["church_sponsor_id"] == str(church.id)

    # Now visible via the CRM roster for that coach — proves the assignment
    # is real, not just reflected back in this response.
    roster = await client.get("/api/v1/crm/clients", headers=_auth(coach_user))
    assert any(c["client_id"] == client_id for c in roster.json())


async def test_get_client_by_id_restricted_to_self_or_admin(client, db_session):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "lookup-client@example.com", "password": "correcthorsebattery"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = await client.get("/api/v1/clients/me", headers=headers)
    client_id = me.json()["client_id"]

    other_client_user = await _make_user(db_session, "other-lookup@example.com", UserRole.client)
    denied = await client.get(f"/api/v1/clients/{client_id}", headers=_auth(other_client_user))
    assert denied.status_code == 403

    admin_user = await _make_user(db_session, "lookup-admin@example.com", UserRole.platform_admin)
    allowed = await client.get(f"/api/v1/clients/{client_id}", headers=_auth(admin_user))
    assert allowed.status_code == 200
