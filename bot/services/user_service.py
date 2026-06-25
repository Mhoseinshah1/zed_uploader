from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    first_name: str,
) -> tuple[User, bool]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    is_admin = telegram_id in settings.ADMIN_IDS
    created = False

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            is_admin=is_admin,
            language="",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        created = True
    else:
        changed = False
        if user.username != username:
            user.username = username
            changed = True
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.is_admin != is_admin:
            user.is_admin = is_admin
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)

    return user, created


async def set_user_language(session: AsyncSession, user: User, lang: str) -> None:
    user.language = lang
    await session.commit()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()
