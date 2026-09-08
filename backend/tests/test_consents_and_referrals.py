from app.models import Client, ClinicalProvider, ProviderType, User, UserRole, VettingStatus
from app.security import create_access_token, hash_password


async def _make_client_user(db_session, email="client1@example.com"):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=UserRole.client)
    db_session.add(user)
    await db_session.flush()
    client_row = Client(user_id=user.id)
    db_session.add(client_row)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(client_row)
    return user, client_row


async def _make_provider(db_session, email, approved=True, license_number="LIC-1"):
    user = User(email=email, hashed_password=hash_password("x" * 12), role=UserRole.provider)
    db_session.add(user)
    await db_session.flush()
    provider = ClinicalProvider(
        user_id=user.id,
        provider_type=ProviderType.psychiatrist,
        license_number=license_number,
        license_state="OK",
        vetting_status=VettingStatus.approved if approved else VettingStatus.pending,
        accepting_referrals=approved,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(provider)
    return user, provider


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


async def test_client_can_create_consent_scoped_to_provider(client, db_session):
    client_user, client_row = await _make_client_user(db_session)
    _, provider = await _make_provider(db_session, "psych1@example.com")

    resp = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={
            "client_id": str(client_row.id),
            "discloses_to_provider_id": str(provider.id),
            "scope": {"clinical_summary": True},
            "typed_signature_name": "Jane Client",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["discloses_to_provider_id"] == str(provider.id)
    assert body["revoked_at"] is None


async def test_cannot_create_consent_for_another_client(client, db_session):
    client_user, _client_row = await _make_client_user(db_session, email="me@example.com")
    _, other_client_row = await _make_client_user(db_session, email="someone-else@example.com")
    _, provider = await _make_provider(db_session, "psych2@example.com")

    resp = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={
            "client_id": str(other_client_row.id),
            "discloses_to_provider_id": str(provider.id),
            "scope": {},
            "typed_signature_name": "Jane Client",
        },
    )
    assert resp.status_code == 403


async def test_consent_requires_exactly_one_disclosure_target(client, db_session):
    client_user, client_row = await _make_client_user(db_session)

    neither = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "scope": {}, "typed_signature_name": "Jane Client"},
    )
    assert neither.status_code == 422


async def test_revoke_consent_then_referral_creation_fails(client, db_session):
    client_user, client_row = await _make_client_user(db_session)
    _, provider = await _make_provider(db_session, "psych3@example.com")

    create = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={
            "client_id": str(client_row.id),
            "discloses_to_provider_id": str(provider.id),
            "scope": {},
            "typed_signature_name": "Jane Client",
        },
    )
    consent_id = create.json()["consent_id"]

    revoke = await client.post(f"/api/v1/consents/roi/{consent_id}/revoke", headers=_auth(client_user))
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None

    # Revoking twice is rejected.
    revoke_again = await client.post(f"/api/v1/consents/roi/{consent_id}/revoke", headers=_auth(client_user))
    assert revoke_again.status_code == 409

    referral = await client.post(
        "/api/v1/referrals",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "provider_id": str(provider.id), "consent_id": consent_id},
    )
    assert referral.status_code == 400


async def test_referral_blocked_when_provider_not_accepting(client, db_session):
    client_user, client_row = await _make_client_user(db_session)
    _, pending_provider = await _make_provider(db_session, "pending-psych@example.com", approved=False)

    consent = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={
            "client_id": str(client_row.id),
            "discloses_to_provider_id": str(pending_provider.id),
            "scope": {},
            "typed_signature_name": "Jane Client",
        },
    )
    consent_id = consent.json()["consent_id"]

    referral = await client.post(
        "/api/v1/referrals",
        headers=_auth(client_user),
        json={
            "client_id": str(client_row.id),
            "provider_id": str(pending_provider.id),
            "consent_id": consent_id,
        },
    )
    assert referral.status_code == 409


async def test_referral_blocked_when_consent_scoped_to_different_provider(client, db_session):
    client_user, client_row = await _make_client_user(db_session)
    _, provider_a = await _make_provider(db_session, "provider-a@example.com", license_number="LIC-A")
    _, provider_b = await _make_provider(db_session, "provider-b@example.com", license_number="LIC-B")

    consent = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={
            "client_id": str(client_row.id),
            "discloses_to_provider_id": str(provider_a.id),
            "scope": {},
            "typed_signature_name": "Jane Client",
        },
    )
    consent_id = consent.json()["consent_id"]

    referral = await client.post(
        "/api/v1/referrals",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "provider_id": str(provider_b.id), "consent_id": consent_id},
    )
    assert referral.status_code == 400


async def test_full_referral_flow_and_role_scoped_listing(client, db_session):
    client_user, client_row = await _make_client_user(db_session)
    other_client_user, other_client_row = await _make_client_user(db_session, email="other-client@example.com")
    provider_user, provider = await _make_provider(db_session, "accepting-psych@example.com")

    consent = await client.post(
        "/api/v1/consents/roi",
        headers=_auth(client_user),
        json={
            "client_id": str(client_row.id),
            "discloses_to_provider_id": str(provider.id),
            "scope": {"clinical_summary": True},
            "typed_signature_name": "Jane Client",
        },
    )
    consent_id = consent.json()["consent_id"]

    created = await client.post(
        "/api/v1/referrals",
        headers=_auth(client_user),
        json={"client_id": str(client_row.id), "provider_id": str(provider.id), "consent_id": consent_id},
    )
    assert created.status_code == 201, created.text
    referral_id = created.json()["referral_id"]
    assert created.json()["status"] == "pending"

    # Client sees their own referral.
    client_list = await client.get("/api/v1/referrals", headers=_auth(client_user))
    assert len(client_list.json()) == 1

    # A different client sees nothing.
    other_list = await client.get("/api/v1/referrals", headers=_auth(other_client_user))
    assert other_list.json() == []

    # The provider sees the inbound referral.
    provider_list = await client.get("/api/v1/referrals", headers=_auth(provider_user))
    assert len(provider_list.json()) == 1

    # A provider cannot respond to someone else's referral.
    _, other_provider = await _make_provider(db_session, "other-psych@example.com", license_number="LIC-OTHER")
    other_provider_user = (await db_session.get(User, other_provider.user_id))
    wrong_respond = await client.patch(
        f"/api/v1/referrals/{referral_id}/respond",
        headers=_auth(other_provider_user),
        json={"status": "accepted"},
    )
    assert wrong_respond.status_code == 403

    accept = await client.patch(
        f"/api/v1/referrals/{referral_id}/respond",
        headers=_auth(provider_user),
        json={"status": "accepted"},
    )
    assert accept.status_code == 200
    assert accept.json()["status"] == "accepted"

    # Responding twice is rejected.
    respond_again = await client.patch(
        f"/api/v1/referrals/{referral_id}/respond",
        headers=_auth(provider_user),
        json={"status": "declined"},
    )
    assert respond_again.status_code == 409
