"""
Dev/demo seed script.

Run with: `python -m app.seed` (inside the backend container/venv, with
DATABASE_URL pointed at a migrated database — run `alembic upgrade head`
first).

Seeds:
  1. scripture_tags / scripture_content from the same library the
     scripture_engine service uses for its in-memory dispatch, so the
     content is consistent between the API's synchronous response and
     whatever a future admin-editable content table would show.
  2. A small set of demo users so the intake flow is runnable end-to-end
     locally: one client, one approved+accepting psychiatrist, and one
     approved+accepting addiction specialist.

Idempotent: safe to re-run — it skips rows that already exist by natural
key (scripture tag name, provider license number, user email).
"""
import asyncio

from sqlalchemy import select

from app.db import async_session_maker
from app.models import (
    ClinicalProvider,
    ProviderType,
    ScriptureContent,
    ScriptureTag,
    User,
    UserRole,
    VettingStatus,
)
from app.security import hash_password
from app.services.scripture_engine import _SCRIPTURE_LIBRARY

DEMO_PASSWORD = "demo-password-change-me-123"


async def seed_scripture(db) -> None:
    for tag_enum, cards in _SCRIPTURE_LIBRARY.items():
        tag_name = tag_enum.value
        existing_tag = (
            await db.execute(select(ScriptureTag).where(ScriptureTag.name == tag_name))
        ).scalar_one_or_none()
        if existing_tag is None:
            existing_tag = ScriptureTag(name=tag_name)
            db.add(existing_tag)
            await db.flush()

        for card in cards:
            existing_content = (
                await db.execute(
                    select(ScriptureContent).where(ScriptureContent.reference == card.reference)
                )
            ).scalar_one_or_none()
            if existing_content is None:
                db.add(
                    ScriptureContent(
                        tag_id=existing_tag.id,
                        reference=card.reference,
                        verse_text=card.verse_text,
                        reflection_text=card.reflection_text,
                        translation=card.translation,
                    )
                )
    print(f"Seeded scripture content for {len(_SCRIPTURE_LIBRARY)} tags.")


async def _get_or_create_user(db, email: str, role: UserRole) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(email=email, hashed_password=hash_password(DEMO_PASSWORD), role=role)
    db.add(user)
    await db.flush()
    return user


async def seed_demo_accounts(db) -> None:
    from app.models import Client

    client_user = await _get_or_create_user(db, "demo-client@example.com", UserRole.client)
    existing_client = (
        await db.execute(select(Client).where(Client.user_id == client_user.id))
    ).scalar_one_or_none()
    if existing_client is None:
        db.add(Client(user_id=client_user.id))

    for email, provider_type, license_number in [
        ("demo-psychiatrist@example.com", ProviderType.psychiatrist, "DEMO-PSYCH-001"),
        ("demo-addiction-specialist@example.com", ProviderType.addiction_specialist, "DEMO-ADDX-001"),
    ]:
        provider_user = await _get_or_create_user(db, email, UserRole.provider)
        existing_provider = (
            await db.execute(
                select(ClinicalProvider).where(ClinicalProvider.license_number == license_number)
            )
        ).scalar_one_or_none()
        if existing_provider is None:
            db.add(
                ClinicalProvider(
                    user_id=provider_user.id,
                    provider_type=provider_type,
                    license_number=license_number,
                    license_state="OK",
                    vetting_status=VettingStatus.approved,
                    accepting_referrals=True,
                )
            )

    admin_email = "demo-admin@example.com"
    await _get_or_create_user(db, admin_email, UserRole.platform_admin)

    print(
        "Seeded demo accounts (client, psychiatrist, addiction specialist, platform admin). "
        f"Password for all: {DEMO_PASSWORD!r} — dev/demo only, never use in a real deployment."
    )


async def main() -> None:
    async with async_session_maker() as db:
        await seed_scripture(db)
        await seed_demo_accounts(db)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
