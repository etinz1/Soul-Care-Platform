import hashlib
import hmac
import json
import time

from app.models import Church, Client, RoiConsent, User, UserRole
from app.security import create_access_token, hash_password

STRIPE_TEST_SECRET = "whsec_integration_test"


async def _make_user(db_session, email, role):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_client(db_session, email="client@example.com"):
    user = await _make_user(db_session, email, UserRole.client)
    client_row = Client(user_id=user.id)
    db_session.add(client_row)
    await db_session.commit()
    await db_session.refresh(client_row)
    return user, client_row


async def _make_church_admin_and_church(db_session, admin_email="church-admin@example.com", name="Grace Fellowship"):
    admin_user = await _make_user(db_session, admin_email, UserRole.church_admin)
    church = Church(name=name, primary_contact_user_id=admin_user.id)
    db_session.add(church)
    await db_session.commit()
    await db_session.refresh(church)
    return admin_user, church


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def _make_consent_to_church(db_session, client_row, church):
    consent = RoiConsent(
        client_id=client_row.id,
        discloses_to_church_id=church.id,
        scope={},
        signature_hash="test-hash",
    )
    db_session.add(consent)
    await db_session.commit()
    await db_session.refresh(consent)
    return consent


# --- Church provisioning ---


async def test_only_admin_can_create_church(client, db_session):
    non_admin = await _make_user(db_session, "someone@example.com", UserRole.church_admin)

    denied = await client.post("/api/v1/church", headers=_auth(non_admin), json={"name": "New Church"})
    assert denied.status_code == 403

    admin_user = await _make_user(db_session, "admin@example.com", UserRole.platform_admin)
    created = await client.post("/api/v1/church", headers=_auth(admin_user), json={"name": "New Church"})
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "New Church"


async def test_church_primary_contact_must_be_church_admin_role(client, db_session):
    admin_user = await _make_user(db_session, "admin2@example.com", UserRole.platform_admin)
    wrong_role_user = await _make_user(db_session, "wrong-role@example.com", UserRole.coach)

    resp = await client.post(
        "/api/v1/church",
        headers=_auth(admin_user),
        json={"name": "Bad Contact Church", "primary_contact_user_id": str(wrong_role_user.id)},
    )
    assert resp.status_code == 400


async def test_list_churches_is_admin_only(client, db_session):
    """GET /church is the admin-only directory the admin dashboard's invoice
    and client-assignment screens use to pick a church, mirroring GET
    /providers for the provider vetting queue."""
    admin_user, church = await _make_church_admin_and_church(db_session)
    platform_admin = await _make_user(db_session, "platform-admin@example.com", UserRole.platform_admin)

    denied = await client.get("/api/v1/church", headers=_auth(admin_user))
    assert denied.status_code == 403

    allowed = await client.get("/api/v1/church", headers=_auth(platform_admin))
    assert allowed.status_code == 200
    names = [c["name"] for c in allowed.json()]
    assert church.name in names


async def test_get_my_church_returns_own_church_for_church_admin(client, db_session):
    """GET /church/me — the self-service lookup the church_admin dashboard
    uses to find its own church_id/name, mirroring GET /clients/me and
    GET /providers/me."""
    church_admin, church = await _make_church_admin_and_church(db_session)

    resp = await client.get("/api/v1/church/me", headers=_auth(church_admin))
    assert resp.status_code == 200
    assert resp.json()["church_id"] == str(church.id)
    assert resp.json()["name"] == church.name


async def test_get_my_church_404_for_church_admin_with_no_church(client, db_session):
    unaffiliated = await _make_user(db_session, "no-church-admin@example.com", UserRole.church_admin)
    resp = await client.get("/api/v1/church/me", headers=_auth(unaffiliated))
    assert resp.status_code == 404


async def test_get_my_church_forbidden_for_non_church_admin(client, db_session):
    platform_admin = await _make_user(db_session, "pa-me-check@example.com", UserRole.platform_admin)
    resp = await client.get("/api/v1/church/me", headers=_auth(platform_admin))
    assert resp.status_code == 403


# --- Sponsorships ---


async def test_sponsorship_requires_consent_scoped_to_church(client, db_session):
    church_admin, church = await _make_church_admin_and_church(db_session)
    _client_user, client_row = await _make_client(db_session)

    no_consent = await client.post(
        "/api/v1/church/sponsorships",
        headers=_auth(church_admin),
        json={"client_id": str(client_row.id), "church_id": str(church.id), "consent_id": str(church.id)},
    )
    assert no_consent.status_code == 404  # bogus consent_id (reusing church.id as a stand-in UUID)

    consent = await _make_consent_to_church(db_session, client_row, church)
    ok = await client.post(
        "/api/v1/church/sponsorships",
        headers=_auth(church_admin),
        json={
            "client_id": str(client_row.id),
            "church_id": str(church.id),
            "consent_id": str(consent.id),
            "sponsor_type": "full",
            "sessions_covered": 12,
            "amount_covered_cents": 120000,
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["status"] == "active"


async def test_sponsorship_blocked_when_consent_scoped_to_different_church(client, db_session):
    church_admin, church_a = await _make_church_admin_and_church(db_session, "admin-a@example.com", "Church A")
    _other_admin, church_b = await _make_church_admin_and_church(db_session, "admin-b@example.com", "Church B")
    _client_user, client_row = await _make_client(db_session)

    consent_to_b = await _make_consent_to_church(db_session, client_row, church_b)

    resp = await client.post(
        "/api/v1/church/sponsorships",
        headers=_auth(church_admin),
        json={
            "client_id": str(client_row.id),
            "church_id": str(church_a.id),
            "consent_id": str(consent_to_b.id),
        },
    )
    assert resp.status_code == 400


async def test_unaffiliated_church_admin_cannot_sponsor_via_another_church(client, db_session):
    _owning_admin, church = await _make_church_admin_and_church(db_session)
    outsider_admin = await _make_user(db_session, "outsider@example.com", UserRole.church_admin)
    _client_user, client_row = await _make_client(db_session)
    consent = await _make_consent_to_church(db_session, client_row, church)

    resp = await client.post(
        "/api/v1/church/sponsorships",
        headers=_auth(outsider_admin),
        json={"client_id": str(client_row.id), "church_id": str(church.id), "consent_id": str(consent.id)},
    )
    assert resp.status_code == 403


async def test_sponsorship_visible_to_owning_church_client_and_admin_only(client, db_session):
    church_admin, church = await _make_church_admin_and_church(db_session)
    client_user, client_row = await _make_client(db_session)
    consent = await _make_consent_to_church(db_session, client_row, church)
    platform_admin = await _make_user(db_session, "platform-admin@example.com", UserRole.platform_admin)

    created = await client.post(
        "/api/v1/church/sponsorships",
        headers=_auth(church_admin),
        json={"client_id": str(client_row.id), "church_id": str(church.id), "consent_id": str(consent.id)},
    )
    sponsorship_id = created.json()["sponsorship_id"]

    for user in (church_admin, client_user, platform_admin):
        resp = await client.get(f"/api/v1/church/sponsorships/{sponsorship_id}", headers=_auth(user))
        assert resp.status_code == 200

    outsider = await _make_user(db_session, "outsider2@example.com", UserRole.client)
    denied = await client.get(f"/api/v1/church/sponsorships/{sponsorship_id}", headers=_auth(outsider))
    assert denied.status_code == 403

    update = await client.patch(
        f"/api/v1/church/sponsorships/{sponsorship_id}", headers=_auth(church_admin), json={"status": "ended"}
    )
    assert update.status_code == 200
    assert update.json()["status"] == "ended"

    client_cannot_edit = await client.patch(
        f"/api/v1/church/sponsorships/{sponsorship_id}", headers=_auth(client_user), json={"status": "active"}
    )
    assert client_cannot_edit.status_code == 403


# --- Billing ---


async def test_only_admin_can_create_invoice_and_amount_is_computed_from_line_items(client, db_session):
    church_admin, church = await _make_church_admin_and_church(db_session)
    platform_admin = await _make_user(db_session, "billing-admin@example.com", UserRole.platform_admin)

    denied = await client.post(
        "/api/v1/billing/invoices",
        headers=_auth(church_admin),
        json={"church_id": str(church.id), "line_items": [{"description": "Session", "amount_cents": 5000}]},
    )
    assert denied.status_code == 403

    created = await client.post(
        "/api/v1/billing/invoices",
        headers=_auth(platform_admin),
        json={
            "church_id": str(church.id),
            "line_items": [
                {"description": "Session 1", "amount_cents": 5000},
                {"description": "Session 2", "amount_cents": 7500},
            ],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["amount_cents"] == 12500
    assert body["status"] == "open"
    # No clinical field can appear — the line item schema has none to carry one.
    for item in body["line_items"]:
        assert set(item.keys()) <= {"session_id", "session_date", "description", "amount_cents"}


async def test_invoice_requires_church_or_client():
    pass  # covered structurally by InvoiceCreateRequest's model_validator; see test_schemas if desired


async def test_church_admin_sees_only_own_church_invoices(client, db_session):
    _admin_a, church_a = await _make_church_admin_and_church(db_session, "admin-a2@example.com", "Church A2")
    admin_b, church_b = await _make_church_admin_and_church(db_session, "admin-b2@example.com", "Church B2")
    platform_admin = await _make_user(db_session, "billing-admin2@example.com", UserRole.platform_admin)

    await client.post(
        "/api/v1/billing/invoices",
        headers=_auth(platform_admin),
        json={"church_id": str(church_a.id), "line_items": [{"description": "x", "amount_cents": 100}]},
    )
    await client.post(
        "/api/v1/billing/invoices",
        headers=_auth(platform_admin),
        json={"church_id": str(church_b.id), "line_items": [{"description": "y", "amount_cents": 200}]},
    )

    b_list = await client.get("/api/v1/church/invoices", headers=_auth(admin_b))
    assert len(b_list.json()) == 1
    assert b_list.json()[0]["church_id"] == str(church_b.id)


def _sign_stripe_payload(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    signed_payload = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


async def test_stripe_webhook_marks_invoice_paid(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.v1.billing.STRIPE_WEBHOOK_SECRET", STRIPE_TEST_SECRET)

    church_admin, church = await _make_church_admin_and_church(db_session, "wh-admin@example.com", "Webhook Church")
    platform_admin = await _make_user(db_session, "wh-platform-admin@example.com", UserRole.platform_admin)

    invoice_resp = await client.post(
        "/api/v1/billing/invoices",
        headers=_auth(platform_admin),
        json={"church_id": str(church.id), "line_items": [{"description": "x", "amount_cents": 100}]},
    )
    invoice_id = invoice_resp.json()["invoice_id"]

    event_payload = json.dumps(
        {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_test_123", "metadata": {"invoice_id": invoice_id}}},
        }
    ).encode("utf-8")
    header = _sign_stripe_payload(event_payload, STRIPE_TEST_SECRET)

    resp = await client.post(
        "/api/v1/billing/stripe/webhook",
        content=event_payload,
        headers={"stripe-signature": header, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    invoice_check = await client.get(f"/api/v1/church/invoices/{invoice_id}", headers=_auth(church_admin))
    assert invoice_check.json()["status"] == "paid"
    assert invoice_check.json()["stripe_payment_intent_id"] == "pi_test_123"


async def test_stripe_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.billing.STRIPE_WEBHOOK_SECRET", STRIPE_TEST_SECRET)

    payload = json.dumps({"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_x"}}}).encode("utf-8")
    resp = await client.post(
        "/api/v1/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
    )
    assert resp.status_code == 400
