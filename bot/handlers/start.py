from __future__ import annotations

import asyncio

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import language_selection_keyboard, main_menu_keyboard
from bot.services.file_service import get_file_by_code, increment_view_count, is_file_expired
from bot.services.resend_service import resend_stored_file
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_LANG_BTN_KEYS = ["btn_lang_fa", "btn_lang_en"]


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    command: CommandObject,
) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(
        session,
        telegram_id=tg.id,
        username=tg.username,
        first_name=tg.first_name or "",
    )

    payload = (command.args or "").strip()
    if payload:
        await _handle_file_deeplink(message, session, bot, user, payload)
        return

    if not user.language:
        btn = await get_texts(session, _LANG_BTN_KEYS, "fa")
        text = await get_text(session, "message_choose_language", "fa")
        await message.answer(text, reply_markup=language_selection_keyboard(btn))
        return

    lang = user.language
    btn = await get_texts(session, _MENU_BTN_KEYS, lang)
    welcome = await get_text(session, "message_welcome", lang, name=user.first_name)
    menu_text = await get_text(session, "message_main_menu", lang)
    await message.answer(welcome)
    await message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))


@router.callback_query(lambda c: c.data and c.data.startswith("get_again:"))
async def get_file_again(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    code = call.data.split(":", 1)[1]
    stored = await get_file_by_code(session, code)

    if stored is None or stored.is_deleted:
        text = await get_text(session, "message_file_not_found", lang)
        await call.answer(text, show_alert=True)
        return

    if is_file_expired(stored):
        text = await get_text(session, "message_file_expired", lang)
        await call.answer(text, show_alert=True)
        return

    await increment_view_count(session, stored)
    sent = await resend_stored_file(bot, call.message, stored)
    await call.answer()

    if sent and stored.auto_delete_seconds:
        _schedule_delete(bot, sent.chat.id, sent.message_id, stored.auto_delete_seconds, session, code)


async def _handle_file_deeplink(message, session, bot, user, code: str) -> None:
    lang = user.language or "fa"
    stored = await get_file_by_code(session, code)

    if stored is None:
        text = await get_text(session, "message_file_not_found", lang)
        await message.answer(text)
        return

    if stored.is_deleted:
        text = await get_text(session, "message_file_deleted", lang)
        await message.answer(text)
        return

    if is_file_expired(stored):
        text = await get_text(session, "message_file_expired", lang)
        await message.answer(text)
        return

    await increment_view_count(session, stored)
    sent = await resend_stored_file(bot, message, stored)
    sent_text = await get_text(session, "message_file_sent", lang)

    if sent and stored.auto_delete_seconds:
        adl = stored.auto_delete_seconds
        warn_text = await get_text(session, "message_auto_delete_warning", lang, seconds=adl)
        kb = InlineKeyboardBuilder()
        btn_label = await get_text(session, "btn_get_file_again", lang)
        kb.button(text=btn_label, callback_data=f"get_again:{code}")
        await message.answer(warn_text, reply_markup=kb.as_markup())
        _schedule_delete(bot, sent.chat.id, sent.message_id, adl, session, code)
    else:
        await message.answer(sent_text)


def _schedule_delete(bot: Bot, chat_id: int, message_id: int, delay: int, session, code: str) -> None:
    async def _do_delete():
        await asyncio.sleep(delay)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    asyncio.create_task(_do_delete())
