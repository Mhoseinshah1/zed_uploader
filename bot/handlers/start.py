from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import language_selection_keyboard, main_menu_keyboard
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_LANG_BTN_KEYS = ["btn_lang_fa", "btn_lang_en"]


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(
        session,
        telegram_id=tg.id,
        username=tg.username,
        first_name=tg.first_name or "",
    )

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
