from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]

_ACTION_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_support",
]


class MenuButtonFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        if not message.text:
            return False
        for key in _ACTION_KEYS:
            fa = await get_text(session, key, "fa")
            en = await get_text(session, key, "en")
            if message.text in (fa, en):
                return True
        return False


@router.message(MenuButtonFilter())
async def handle_menu_button(message: Message, session: AsyncSession) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"

    matched_key: str | None = None
    for key in _ACTION_KEYS:
        fa = await get_text(session, key, "fa")
        en = await get_text(session, key, "en")
        if message.text in (fa, en):
            matched_key = key
            break

    if matched_key is None:
        return

    if matched_key == "btn_save_file":
        text = await get_text(session, "message_save_file_coming_soon", lang)
        await message.answer(text)

    elif matched_key == "btn_my_files":
        text = await get_text(session, "message_my_files_empty", lang)
        await message.answer(text)

    elif matched_key == "btn_profile":
        created_str = user.created_at.strftime("%Y-%m-%d") if user.created_at else "—"
        lang_label = "فارسی" if lang == "fa" else "English"
        text = await get_text(
            session, "message_profile", lang,
            telegram_id=str(user.telegram_id),
            first_name=user.first_name or "—",
            language=lang_label,
            created_at=created_str,
        )
        await message.answer(text)

    elif matched_key == "btn_settings":
        text = await get_text(session, "message_settings", lang)
        await message.answer(text)

    elif matched_key == "btn_support":
        text = await get_text(session, "message_support", lang)
        await message.answer(text)
