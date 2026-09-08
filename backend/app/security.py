"""
Password hashing and JWT issuance/validation.

Kept separate from auth.py (FastAPI dependencies) so this module has no
FastAPI/DB imports and is trivially unit-testable.
"""
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: UUID, role: str) -> str:
    token, _ = _create_token(
        user_id, role, token_type="access", expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return token


def create_refresh_token(user_id: UUID) -> tuple[str, str, int]:
    """Returns (token, jti, ttl_seconds) — the jti/ttl let the caller register it in Redis."""
    ttl_seconds = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    token, jti = _create_token(
        user_id, role=None, token_type="refresh", expires_delta=timedelta(seconds=ttl_seconds)
    )
    return token, jti, ttl_seconds


def _create_token(user_id: UUID, role: str | None, token_type: str, expires_delta: timedelta) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + expires_delta,
    }
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM), jti


def decode_token(token: str) -> dict:
    """Raises jose.JWTError on invalid signature/expiry — callers translate to HTTP 401."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def hash_typed_signature(client_id: UUID, typed_name: str, scope: dict, signed_at: datetime) -> str:
    """
    Placeholder e-signature: hashes the attestation (typed legal name) together
    with what was consented to and when, so the hash is tamper-evident even
    though it isn't a real digital-signature certificate. See
    ConsentCreateRequest's docstring — replace with a real e-signature vendor
    before collecting real ROI consent.
    """
    canonical = f"{client_id}|{typed_name.strip().lower()}|{sorted(scope.items())}|{signed_at.isoformat()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_stripe_webhook_signature(
    payload: bytes, sig_header: str | None, secret: str, tolerance_seconds: int = 300
) -> bool:
    """
    Verifies a Stripe webhook signature per Stripe's documented scheme
    (https://stripe.com/docs/webhooks/signatures), implemented directly
    against HMAC-SHA256 rather than pulling in the `stripe` SDK just for
    this one check.

    Header format: `t=<unix timestamp>,v1=<hex hmac>[,v1=<hex hmac>...]`
    (multiple v1 entries occur during Stripe's signing-secret rotation).
    The signed payload is `f"{timestamp}.{raw body}"`. Returns False (never
    raises) on any malformed header, stale timestamp, or mismatch, so the
    caller can respond with a clean 400 either way.
    """
    if not sig_header:
        return False

    timestamp = None
    signatures = []
    for item in sig_header.split(","):
        key, _, value = item.partition("=")
        key, value = key.strip(), value.strip()
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if timestamp is None or not signatures:
        return False
    try:
        ts_int = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_typed_signature",
    "verify_stripe_webhook_signature",
    "JWTError",
]
