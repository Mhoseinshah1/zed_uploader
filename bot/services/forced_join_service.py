from __future__ import annotations

from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import RequiredChannel
from bot.services.setting_service import get_setting, set_setting

_FORCED_JOIN_KEY = "forced_join_enabled"
_NOT_MEMBER_STATUSES = {"left", "kicked"}


async def is_forced_join_enabled(session: AsyncSession) -> bool:
    val = await get_setting(session, _FORCED_JOIN_KEY, "0")
    return val in ("1", "true", "True", "on")


async def set_forced_join_enabled(session: AsyncSession, enabled: bool) -> None:
    await set_setting(session, _FORCED_JOIN_KEY, "1" if enabled else "0")


async def list_channels(session: AsyncSession, active_only: bool = False) -> list[RequiredChannel]:
    q = select(RequiredChannel).order_by(RequiredChannel.sort_order, RequiredChannel.id)
    if active_only:
        q = q.where(RequiredChannel.is_active == True)  # noqa: E712
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_channel(session: AsyncSession, channel_id: int) -> Optional[RequiredChannel]:
    result = await session.execute(select(RequiredChannel).where(RequiredChannel.id == channel_id))
    return result.scalar_one_or_none()


async def get_channel_by_chat_id(session: AsyncSession, chat_id: int) -> Optional[RequiredChannel]:
    result = await session.execute(select(RequiredChannel).where(RequiredChannel.chat_id == chat_id))
    return result.scalar_one_or_none()


async def add_channel(
    session: AsyncSession,
    chat_id: int,
    title: str,
    invite_link: Optional[str],
) -> RequiredChannel:
    existing = await get_channel_by_chat_id(session, chat_id)
    if existing:
        existing.title = title
        if invite_link:
            existing.invite_link = invite_link
        existing.is_active = True
        await session.commit()
        return existing
    channel = RequiredChannel(chat_id=chat_id, title=title, invite_link=invite_link, is_active=True)
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def delete_channel(session: AsyncSession, channel: RequiredChannel) -> None:
    await session.delete(channel)
    await session.commit()


async def toggle_channel(session: AsyncSession, channel: RequiredChannel) -> bool:
    channel.is_active = not channel.is_active
    await session.commit()
    return channel.is_active


async def get_missing_channels(bot: Bot, session: AsyncSession, user_id: int) -> list[RequiredChannel]:
    """Return active channels the user has NOT joined. Empty list = all good (or join disabled)."""
    if not await is_forced_join_enabled(session):
        return []
    channels = await list_channels(session, active_only=True)
    missing: list[RequiredChannel] = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch.chat_id, user_id)
            if member.status in _NOT_MEMBER_STATUSES:
                missing.append(ch)
        except TelegramAPIError:
            # Bot likely not admin / cannot verify — treat as not-joined so the
            # user sees the channel, rather than silently letting everyone through.
            missing.append(ch)
    return missing
