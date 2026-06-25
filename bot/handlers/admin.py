from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import admin_panel_keyboard, main_menu_keyboard
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_ADMIN_BTN_KEYS = ["admin_btn_stats", "admin_btn_manage_texts", "admin_btn_back"]


class AdminPanelFilter(Filter):
    """Matches only when an admin sends the admin-panel button text."""
    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        if not message.text:
            return False
        tg = message.from_user
        user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
        if not user.is_admin:
            return False
        btn_fa = await get_text(session, "btn_admin_panel", "fa")
        btn_en = await get_text(session, "btn_admin_panel", "en")
        return message.text in (btn_fa, btn_en)


@router.message(AdminPanelFilter())
async def admin_panel_entry(message: Message, session: AsyncSession) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    btn = await get_texts(session, _ADMIN_BTN_KEYS, lang)
    text = await get_text(session, "message_admin_panel", lang)
    await message.answer(text, reply_markup=admin_panel_keyboard(btn))


@router.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def admin_callback(call: CallbackQuery, session: AsyncSession) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await call.answer("Access denied.", show_alert=True)
        return

    lang = user.language or "fa"
    action = call.data.split(":")[1]

    if action == "stats":
        await call.message.answer(
            "📊 آمار در فاز بعدی پیاده‌سازی می‌شود." if lang == "fa"
            else "📊 Stats will be implemented in the next phase."
        )
    elif action == "texts":
        await call.message.answer(
            "✏️ مدیریت متن‌ها در فاز بعدی پیاده‌سازی می‌شود." if lang == "fa"
            else "✏️ Text management will be implemented in the next phase."
        )
    elif action == "back":
        btn = await get_texts(session, _MENU_BTN_KEYS, lang)
        menu_text = await get_text(session, "message_main_menu", lang)
        await call.message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))

    await call.answer()
