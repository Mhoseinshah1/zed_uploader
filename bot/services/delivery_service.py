from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import StoredFile, User
from bot.services.file_service import (
    get_file_by_code,
    increment_view_count,
    is_file_expired,
    mark_expired,
)
from bot.services.forced_join_service import get_missing_channels
from bot.services.resend_service import resend_stored_file
from bot.services.text_service import get_text
from bot.states import PasswordStates


def schedule_auto_delete(bot: Bot, chat_id: int, message_id: int, delay: int) -> None:
    """Delete a sent file message after `delay` seconds. Never crashes the bot."""
    async def _runner() -> None:
        await asyncio.sleep(delay)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    asyncio.create_task(_runner())


async def deliver_file(
    bot: Bot,
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    user: User,
    code: str,
    *,
    password_verified: bool = False,
) -> str:
    """Central delivery pipeline. Returns a status string:
    'sent' | 'not_found' | 'deleted' | 'expired' | 'needs_join' | 'needs_password'.

    Order (per spec): exists → deleted → expired → forced join → password → send.
    Never downloads files — only resends Telegram file_id.
    """
    lang = user.language or "fa"
    stored = await get_file_by_code(session, code)

    if stored is None:
        await message.answer(await get_text(session, "message_file_not_found", lang))
        return "not_found"

    if stored.is_deleted:
        await message.answer(await get_text(session, "message_file_deleted", lang))
        return "deleted"

    # ── private files: only the owner or an admin may receive ──────────────────
    if not stored.is_public and stored.owner_id != user.id and not user.is_admin:
        await message.answer(await get_text(session, "message_file_private", lang))
        return "private"

    if is_file_expired(stored):
        await mark_expired(session, stored)
        await message.answer(await get_text(session, "message_file_expired", lang))
        return "expired"

    # ── forced join ────────────────────────────────────────────────────────────
    missing = await get_missing_channels(bot, session, user.telegram_id)
    if missing:
        await _send_join_prompt(message, session, lang, missing, code)
        return "needs_join"

    # ── password ───────────────────────────────────────────────────────────────
    if stored.password_hash and not password_verified:
        await state.set_state(PasswordStates.waiting_for_password)
        await state.update_data(file_code=code)
        await message.answer(await get_text(session, "message_password_required", lang))
        return "needs_password"

    # ── send ──────────────────────────────────────────────────────────────────
    await increment_view_count(session, stored)
    sent = await resend_stored_file(bot, message, stored)
    await _post_delivery(bot, message, session, stored, sent, lang)
    return "sent"


async def _send_join_prompt(message, session, lang, channels, code: str) -> None:
    text = await get_text(session, "message_forced_join", lang)
    kb = InlineKeyboardBuilder()
    for ch in channels:
        if ch.invite_link:
            kb.button(text=f"📢 {ch.title}", url=ch.invite_link)
    check_label = await get_text(session, "btn_check_join", lang)
    kb.button(text=check_label, callback_data=f"check_join:{code}")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup())


async def _post_delivery(bot, message, session, stored: StoredFile, sent, lang) -> None:
    """Schedule auto-delete (if set) and attach get-again / like / report controls."""
    adl = stored.auto_delete_seconds
    kb = InlineKeyboardBuilder()

    if sent and adl and adl > 0:
        again_label = await get_text(session, "btn_get_file_again", lang)
        kb.button(text=again_label, callback_data=f"get_file_again:{stored.code}")

    like_label = await get_text(session, "btn_file_like", lang)
    report_label = await get_text(session, "btn_file_report", lang)
    kb.button(text=like_label, callback_data=f"flike:{stored.code}")
    kb.button(text=report_label, callback_data=f"freport:{stored.code}")
    kb.adjust(1, 2)

    if sent and adl and adl > 0:
        warn = await get_text(session, "message_auto_delete_warning", lang, seconds=adl)
        await message.answer(warn, reply_markup=kb.as_markup())
        schedule_auto_delete(bot, sent.chat.id, sent.message_id, adl)
    else:
        sent_text = await get_text(session, "message_file_sent", lang)
        await message.answer(sent_text, reply_markup=kb.as_markup())
