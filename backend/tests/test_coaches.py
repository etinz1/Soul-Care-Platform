from app.models import User, UserRole
from app.security import create_access_token, hash_password


async def _make_user(db_session, email, role):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def test_only_admin_can_create_coach(client, db_session):
    non_admin = await _make_user(db_session, "someone@example.com", UserRole.coach)

    denied = await client.post(
        "/api/v1/coaches",
        headers=_auth(non_admin),
        json={"email": "new-coach@example.com", "password": "correcthorsebattery"},
    )
    assert denied.status_code == 403

    admin = await _make_user(db_session, "admin@example.com", UserRole.platform_admin)
    created = await client.post(
        "/api/v1/coaches",
        headers=_auth(admin),
        json={"email": "new-coach@example.com", "password": "correcthorsebattery", "bio": "10 years in ministry."},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "new-coach@example.com"
    assert body["active"] is True


async def test_coach_email_must_be_unique(client, db_session):
    admin = await _make_user(db_session, "admin2@example.com", UserRole.platform_admin)
    await _make_user(db_session, "dupe@example.com", UserRole.client)

    resp = await client.post(
        "/api/v1/coaches",
        headers=_auth(admin),
        json={"email": "dupe@example.com", "password": "correcthorsebattery"},
    )
    assert resp.status_code == 409


async def test_new_coach_can_log_in_and_admin_can_list_coaches(client, db_session):
    admin = await _make_user(db_session, "admin3@example.com", UserRole.platform_admin)
    await client.post(
        "/api/v1/coaches",
        headers=_auth(admin),
        json={"email": "logs-in@example.com", "password": "correcthorsebattery"},
    )

    login = await client.post(
        "/api/v1/auth/login", json={"email": "logs-in@example.com", "password": "correcthorsebattery"}
    )
    assert login.status_code == 200, login.text

    listing = await client.get("/api/v1/coaches", headers=_auth(admin))
    assert listing.status_code == 200
    emails = [c["email"] for c in listing.json()]
    assert "logs-in@example.com" in emails


async def test_list_coaches_is_admin_only(client, db_session):
    coach_user = await _make_user(db_session, "not-admin@example.com", UserRole.coach)
    resp = await client.get("/api/v1/coaches", headers=_auth(coach_user))
    assert resp.status_code == 403
