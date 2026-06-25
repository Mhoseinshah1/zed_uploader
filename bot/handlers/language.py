from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import language_selection_keyboard, main_menu_keyboard
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user, set_user_language

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_LANG_BTN_KEYS = ["btn_lang_fa", "btn_lang_en"]


class ChangeLangTextFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        tg = message.from_user
        user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
        lang = user.language or "fa"
        btn_fa = await get_text(session, "btn_change_language", "fa")
        btn_en = await get_text(session, "btn_change_language", "en")
        return message.text in (btn_fa, btn_en)


@router.message(ChangeLangTextFilter())
async def handle_change_language(message: Message, session: AsyncSession) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    btn = await get_texts(session, _LANG_BTN_KEYS, lang)
    text = await get_text(session, "message_choose_language", lang)
    await message.answer(text, reply_markup=language_selection_keyboard(btn))


@router.callback_query(lambda c: c.data and c.data.startswith("lang:"))
async def callback_language_selected(call: CallbackQuery, session: AsyncSession) -> None:
    lang = call.data.split(":")[1]
    if lang not in ("fa", "en"):
        await call.answer()
        return

    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    await set_user_language(session, user, lang)

    changed_text = await get_text(session, "message_language_changed", lang)
    await call.message.answer(changed_text)

    btn = await get_texts(session, _MENU_BTN_KEYS, lang)
    welcome = await get_text(session, "message_welcome", lang, name=user.first_name)
    menu_text = await get_text(session, "message_main_menu", lang)
    await call.message.answer(welcome)
    await call.message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))
    await call.answer()
