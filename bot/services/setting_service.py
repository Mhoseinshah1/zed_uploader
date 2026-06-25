from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import BotSetting


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str) -> BotSetting:
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        setting = BotSetting(key=key, value=value)
        session.add(setting)
    await session.commit()
    return setting
