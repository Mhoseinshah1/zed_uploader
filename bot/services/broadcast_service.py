from __future__ import annotations

import asyncio
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Broadcast, User

# Telegram allows ~30 msg/sec for bots; stay safely under it.
_THROTTLE_SECONDS = 0.05


async def _all_active_user_chat_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(
        select(User.telegram_id).where(User.is_blocked == False)  # noqa: E712
    )
    return [row[0] for row in result.all()]


async def run_broadcast(
    bot: Bot,
    session: AsyncSession,
    *,
    text: Optional[str] = None,
    forward_from_chat_id: Optional[int] = None,
    forward_message_id: Optional[int] = None,
) -> Broadcast:
    """Send (or forward) a message to all non-blocked users with throttling.

    Never crashes on a blocked user; counts sent/failed and records the result.
    """
    chat_ids = await _all_active_user_chat_ids(session)

    record = Broadcast(
        message_text=text,
        telegram_message_id=forward_message_id,
        total_users=len(chat_ids),
        status="running",
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    sent = 0
    failed = 0
    for chat_id in chat_ids:
        try:
            if forward_from_chat_id is not None and forward_message_id is not None:
                await bot.forward_message(chat_id, forward_from_chat_id, forward_message_id)
            elif text is not None:
                await bot.send_message(chat_id, text)
            else:
                break
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                if forward_from_chat_id is not None and forward_message_id is not None:
                    await bot.forward_message(chat_id, forward_from_chat_id, forward_message_id)
                elif text is not None:
                    await bot.send_message(chat_id, text)
                sent += 1
            except Exception:
                failed += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(_THROTTLE_SECONDS)

    record.sent_count = sent
    record.failed_count = failed
    record.status = "done"
    await session.commit()
    await session.refresh(record)
    return record
