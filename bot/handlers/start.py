from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import language_selection_keyboard, main_menu_keyboard
from bot.services.file_service import get_file_by_code, get_bot_username, increment_view_count
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

    # ── Deep-link payload: /start <code> ──────────────────────────────────────
    payload = (command.args or "").strip()
    if payload:
        await _handle_file_deeplink(message, session, bot, user, payload)
        return

    # ── Normal /start ─────────────────────────────────────────────────────────
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

    if stored.is_expired:
        text = await get_text(session, "message_file_expired", lang)
        await message.answer(text)
        return

    await increment_view_count(session, stored)
    await resend_stored_file(bot, message, stored)
    sent_text = await get_text(session, "message_file_sent", lang)
    await message.answer(sent_text)
