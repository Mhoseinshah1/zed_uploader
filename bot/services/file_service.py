from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import FileReport, StoredFile, User
from bot.services.password_service import hash_password, verify_password

_CODE_ALPHABET = string.ascii_letters + string.digits
_CODE_PREFIX = "F_"
_CODE_RANDOM_LEN = 8


def generate_unique_code() -> str:
    random_part = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_RANDOM_LEN))
    return f"{_CODE_PREFIX}{random_part}"


def build_deep_link(code: str, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start={code}"


def is_file_expired(stored: StoredFile) -> bool:
    """Check expiry by flag OR by computing from expires_at."""
    if stored.is_expired:
        return True
    if stored.expires_at:
        exp = stored.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(tz=timezone.utc) > exp
    return False


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
    expires_at: Optional[datetime] = None,
    auto_delete_seconds: Optional[int] = None,
) -> StoredFile:
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
        expires_at=expires_at,
        auto_delete_seconds=auto_delete_seconds,
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


async def get_file_by_id(session: AsyncSession, file_id: int) -> Optional[StoredFile]:
    result = await session.execute(
        select(StoredFile).where(StoredFile.id == file_id)
    )
    return result.scalar_one_or_none()


async def get_user_files(
    session: AsyncSession,
    owner_id: int,
    include_deleted: bool = False,
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[StoredFile], int]:
    q = select(StoredFile).where(StoredFile.owner_id == owner_id)
    if not include_deleted:
        q = q.where(StoredFile.is_deleted == False)  # noqa: E712
    total_q = select(func.count()).select_from(q.subquery())
    total = (await session.execute(total_q)).scalar_one()
    files_result = await session.execute(
        q.order_by(StoredFile.created_at.desc()).limit(limit).offset(offset)
    )
    return list(files_result.scalars().all()), total


async def get_all_files(
    session: AsyncSession,
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[StoredFile], int]:
    q = select(StoredFile)
    total_q = select(func.count()).select_from(q.subquery())
    total = (await session.execute(total_q)).scalar_one()
    files_result = await session.execute(
        q.order_by(StoredFile.created_at.desc()).limit(limit).offset(offset)
    )
    return list(files_result.scalars().all()), total


async def increment_view_count(session: AsyncSession, stored: StoredFile) -> None:
    await session.execute(
        update(StoredFile)
        .where(StoredFile.id == stored.id)
        .values(views_count=StoredFile.views_count + 1)
    )
    await session.commit()


async def soft_delete_file(session: AsyncSession, stored: StoredFile) -> None:
    stored.is_deleted = True
    await session.commit()


async def toggle_file_active(session: AsyncSession, stored: StoredFile) -> bool:
    """Toggle is_deleted. Returns new is_deleted state."""
    stored.is_deleted = not stored.is_deleted
    await session.commit()
    return stored.is_deleted


def get_bot_username(bot_username_override: str = "") -> str:
    username = bot_username_override or settings.BOT_USERNAME
    return username.lstrip("@")


async def regenerate_code(session: AsyncSession, stored: StoredFile) -> str:
    """Assign a fresh unique code. The OLD code stops working immediately."""
    for _ in range(5):
        code = generate_unique_code()
        existing = await session.execute(select(StoredFile).where(StoredFile.code == code))
        if existing.scalar_one_or_none() is None:
            break
    else:
        raise RuntimeError("Failed to generate a unique file code after 5 attempts")
    stored.code = code
    await session.commit()
    await session.refresh(stored)
    return code


async def set_file_password(session: AsyncSession, stored: StoredFile, password: str) -> None:
    stored.password_hash = hash_password(password)
    await session.commit()


async def remove_file_password(session: AsyncSession, stored: StoredFile) -> None:
    stored.password_hash = None
    await session.commit()


def check_file_password(stored: StoredFile, password: str) -> bool:
    if not stored.password_hash:
        return True
    return verify_password(password, stored.password_hash)


async def set_file_expiration(session: AsyncSession, stored: StoredFile, seconds: Optional[int]) -> None:
    """Set expiration N seconds from now, or clear it when seconds is falsy."""
    if seconds and seconds > 0:
        stored.expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
        stored.is_expired = False
    else:
        stored.expires_at = None
        stored.is_expired = False
    await session.commit()


async def remove_file_expiration(session: AsyncSession, stored: StoredFile) -> None:
    stored.expires_at = None
    stored.is_expired = False
    await session.commit()


async def mark_expired(session: AsyncSession, stored: StoredFile) -> None:
    if not stored.is_expired:
        stored.is_expired = True
        await session.commit()


async def add_report(session: AsyncSession, stored: StoredFile, user: User, reason: str = "") -> int:
    """Record a report (one per user per file) and return the new reports_count."""
    existing = await session.execute(
        select(FileReport).where(FileReport.file_id == stored.id, FileReport.user_id == user.id)
    )
    if existing.scalar_one_or_none() is None:
        session.add(FileReport(file_id=stored.id, user_id=user.id, reason=reason[:500] or None))
        await session.execute(
            update(StoredFile).where(StoredFile.id == stored.id)
            .values(reports_count=StoredFile.reports_count + 1)
        )
        await session.commit()
        await session.refresh(stored)
    return stored.reports_count


async def toggle_public(session: AsyncSession, stored: StoredFile) -> bool:
    """Flip public/private. Returns the new is_public value."""
    stored.is_public = not stored.is_public
    await session.commit()
    return stored.is_public


async def set_fake_views(session: AsyncSession, stored: StoredFile, amount: int) -> None:
    stored.fake_views = max(0, amount)
    await session.commit()


def display_views(stored: StoredFile) -> int:
    """Views shown publicly = real views + admin-configured fake views."""
    return stored.views_count + (stored.fake_views or 0)


async def add_like(session: AsyncSession, stored: StoredFile) -> int:
    await session.execute(
        update(StoredFile).where(StoredFile.id == stored.id)
        .values(likes_count=StoredFile.likes_count + 1)
    )
    await session.commit()
    await session.refresh(stored)
    return stored.likes_count


async def get_files_by_owner_telegram_id(
    session: AsyncSession,
    telegram_id: int,
    category: str = "all",
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[StoredFile], int]:
    """Admin file lookup by the owner's numeric Telegram ID, filtered by category."""
    q = (
        select(StoredFile)
        .join(User, StoredFile.owner_id == User.id)
        .where(User.telegram_id == telegram_id)
    )
    if category == "active":
        q = q.where(StoredFile.is_deleted == False, StoredFile.is_expired == False)  # noqa: E712
    elif category == "deleted":
        q = q.where(StoredFile.is_deleted == True)  # noqa: E712
    elif category == "expired":
        q = q.where(StoredFile.is_expired == True)  # noqa: E712
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = await session.execute(
        q.order_by(StoredFile.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), total
