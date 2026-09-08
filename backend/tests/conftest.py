import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://soul_care:soul_care_dev_password@localhost:5432/soul_care_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")  # separate DB index from dev
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-do-not-use-in-prod")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_db_session
from app.main import app
from app.models import Base
from app.redis_client import redis_client

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
# NullPool: pytest-asyncio spins up a fresh event loop per test function by
# default, but asyncpg connections are bound to the loop that created them.
# A pooled connection reused across tests/loops raises
# "cannot perform operation: another operation is in progress" — NullPool
# opens a fresh connection per checkout instead of reusing one across loops.
_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def _override_get_db_session():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db_session] = _override_get_db_session


@pytest_asyncio.fixture(autouse=True)
async def _reset_state():
    """Fresh schema and flushed Redis before every test for isolation."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    await redis_client.flushdb()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session
