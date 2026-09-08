"""
Minimal async SQLAlchemy session wiring. Replace the connection string with
Secrets-Manager-sourced credentials in real deployments — never hardcode.
"""
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/soul_care"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
