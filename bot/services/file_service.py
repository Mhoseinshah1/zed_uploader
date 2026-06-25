from __future__ import annotations

import secrets
import string
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import StoredFile, User

_CODE_ALPHABET = string.ascii_letters + string.digits
_CODE_PREFIX = "F_"
_CODE_RANDOM_LEN = 8


def generate_unique_code() -> str:
    random_part = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_RANDOM_LEN))
    return f"{_CODE_PREFIX}{random_part}"


def build_deep_link(code: str, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start={code}"


async def create_stored_file(
    session: AsyncSession,
    owner: User,
    file_type: str,
    telegram_file_id: str = "",
    telegram_file_unique_id: str = "",
    caption: Optional[str] = None,
    text_content: Optional[str] = None,
    metadata_json: Optional[dict] = None,
    original_file_name: Optional[str] = None,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
) -> StoredFile:
    # Guarantee uniqueness: retry on the rare collision
    for _ in range(5):
        code = generate_unique_code()
        existing = await session.execute(
            select(StoredFile).where(StoredFile.code == code)
        )
        if existing.scalar_one_or_none() is None:
            break
    else:
        raise RuntimeError("Failed to generate a unique file code after 5 attempts")

    stored = StoredFile(
        code=code,
        owner_id=owner.id,
        file_type=file_type,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        caption=caption,
        text_content=text_content,
        metadata_json=metadata_json,
        original_file_name=original_file_name,
        file_size=file_size,
        mime_type=mime_type,
    )
    session.add(stored)
    await session.commit()
    await session.refresh(stored)
    return stored


async def get_file_by_code(session: AsyncSession, code: str) -> Optional[StoredFile]:
    result = await session.execute(
        select(StoredFile).where(StoredFile.code == code)
    )
    return result.scalar_one_or_none()


async def increment_view_count(session: AsyncSession, stored: StoredFile) -> None:
    await session.execute(
        update(StoredFile)
        .where(StoredFile.id == stored.id)
        .values(views_count=StoredFile.views_count + 1)
    )
    await session.commit()


def get_bot_username(bot_username_override: str = "") -> str:
    username = bot_username_override or settings.BOT_USERNAME
    return username.lstrip("@")
