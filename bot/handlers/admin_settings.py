from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.setting_service import get_setting, set_setting
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user
from bot.states import AdminSettingsStates

router = Router()

# (callback_suffix, title_key, setting_key)
_SETTINGS = [
    ("support_text",   "btn_admin_setting_support_text",  "support_text"),
    ("support_url",    "btn_admin_setting_support_url",   "support_url"),
    ("support_btn",    "btn_admin_setting_support_btn",   "support_btn_text"),
    ("default_exp",    "btn_admin_setting_default_exp",   "global_expiration_seconds"),
    ("auto_del",       "btn_admin_setting_auto_del",      "global_auto_delete_seconds"),
]


@router.callback_query(lambda c: c.data and c.data.startswith("adm_s:"))
async def admin_settings_callback(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await call.answer("Access denied.", show_alert=True)
        return

    lang = user.language or "fa"
    parts = call.data.split(":")
    action = parts[1]

    entry = next((s for s in _SETTINGS if s[0] == action), None)
    if not entry:
        await call.answer()
        return

    _, title_key, setting_key = entry
    current_val = await get_setting(session, setting_key, "—")
    title = await get_text(session, title_key, lang)
    text = await get_text(
        session, "message_admin_setting_current", lang,
        title=title,
        value=current_val,
    )

    await state.set_state(AdminSettingsStates.entering_value)
    await state.update_data(setting_key=setting_key)
    await call.message.answer(text)
    await call.answer()


@router.message(AdminSettingsStates.entering_value)
async def receive_setting_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await state.clear()
        return

    lang = user.language or "fa"

    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌")
        return

    data = await state.get_data()
    setting_key = data.get("setting_key", "")
    await state.clear()

    if setting_key and message.text:
        await set_setting(session, setting_key, message.text.strip())

    text = await get_text(session, "message_admin_setting_updated", lang)
    await message.answer(text)


async def build_admin_settings_keyboard(session: AsyncSession, lang: str):
    kb = InlineKeyboardBuilder()
    for suffix, title_key, _ in _SETTINGS:
        label = await get_text(session, title_key, lang)
        kb.button(text=label, callback_data=f"adm_s:{suffix}")
    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="admin:back")
    kb.adjust(1)
    return kb.as_markup()
