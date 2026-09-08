"""Unit tests for the hand-rolled Stripe webhook signature verification
(app.security.verify_stripe_webhook_signature) — no network, no `stripe`
SDK dependency, just the documented HMAC-SHA256 scheme."""
import hashlib
import hmac
import time

from app.security import verify_stripe_webhook_signature

SECRET = "whsec_test_secret"


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    payload = b'{"type": "payment_intent.succeeded"}'
    ts = int(time.time())
    sig = _sign(payload, SECRET, ts)
    header = f"t={ts},v1={sig}"
    assert verify_stripe_webhook_signature(payload, header, SECRET) is True


def test_tampered_payload_rejected():
    payload = b'{"type": "payment_intent.succeeded"}'
    ts = int(time.time())
    sig = _sign(payload, SECRET, ts)
    header = f"t={ts},v1={sig}"
    tampered = b'{"type": "payment_intent.succeeded", "amount": 999999}'
    assert verify_stripe_webhook_signature(tampered, header, SECRET) is False


def test_wrong_secret_rejected():
    payload = b'{"type": "payment_intent.succeeded"}'
    ts = int(time.time())
    sig = _sign(payload, "some-other-secret", ts)
    header = f"t={ts},v1={sig}"
    assert verify_stripe_webhook_signature(payload, header, SECRET) is False


def test_stale_timestamp_rejected():
    payload = b'{"type": "payment_intent.succeeded"}'
    ts = int(time.time()) - 10_000  # well outside the default 300s tolerance
    sig = _sign(payload, SECRET, ts)
    header = f"t={ts},v1={sig}"
    assert verify_stripe_webhook_signature(payload, header, SECRET) is False


def test_missing_header_rejected():
    assert verify_stripe_webhook_signature(b"{}", None, SECRET) is False
    assert verify_stripe_webhook_signature(b"{}", "", SECRET) is False


def test_malformed_header_rejected():
    assert verify_stripe_webhook_signature(b"{}", "not-a-valid-header", SECRET) is False


def test_multiple_v1_entries_any_match_accepted():
    """Stripe sends multiple v1 signatures during signing-secret rotation; matching any is valid."""
    payload = b'{"type": "payment_intent.succeeded"}'
    ts = int(time.time())
    correct_sig = _sign(payload, SECRET, ts)
    header = f"t={ts},v1=deadbeef,v1={correct_sig}"
    assert verify_stripe_webhook_signature(payload, header, SECRET) is True
