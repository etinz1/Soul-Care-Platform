"""
Minimal Redis wiring, used for refresh-token allowlisting (a refresh token
is only honored if its jti is present in Redis, so logout/revocation is
immediate rather than waiting out the token's natural expiry).
"""
import os

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


async def allow_refresh_token(jti: str, ttl_seconds: int) -> None:
    await redis_client.set(f"refresh:{jti}", "1", ex=ttl_seconds)


async def is_refresh_token_allowed(jti: str) -> bool:
    return await redis_client.exists(f"refresh:{jti}") == 1


async def revoke_refresh_token(jti: str) -> None:
    await redis_client.delete(f"refresh:{jti}")
