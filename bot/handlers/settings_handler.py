from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import language_selection_keyboard, main_menu_keyboard
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user
from bot.states import SettingsStates

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_LANG_BTN_KEYS = ["btn_lang_fa", "btn_lang_en"]

# (label_key, seconds_value) for expiration choices; 0 = never
_EXP_CHOICES = [
    ("exp_never", 0),
    ("exp_20s", 20),
    ("exp_1h", 3600),
    ("exp_6h", 21600),
    ("exp_1d", 86400),
    ("exp_7d", 604800),
    ("exp_30d", 2592000),
    ("exp_custom", -1),
]

# (label_key, seconds_value) for auto-delete; 0 = off
_ADL_CHOICES = [
    ("adl_off", 0),
    ("adl_20s", 20),
    ("adl_1m", 60),
    ("adl_5m", 300),
    ("adl_custom", -1),
]


class SettingsButtonFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool | dict:
        if not message.text:
            return False
        tg = message.from_user
        user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
        fa = await get_text(session, "btn_settings", "fa")
        en = await get_text(session, "btn_settings", "en")
        if message.text not in (fa, en):
            return False
        return {"db_user": user}


@router.message(SettingsButtonFilter())
async def show_settings(message: Message, session: AsyncSession, db_user) -> None:
    lang = db_user.language or "fa"
    text = await get_text(session, "message_settings_menu", lang)
    markup = await _settings_keyboard(session, lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(lambda c: c.data and c.data.startswith("uset:"))
async def settings_callback(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    parts = call.data.split(":")
    action = parts[1]

    if action == "lang":
        btn = await get_texts(session, _LANG_BTN_KEYS, lang)
        text = await get_text(session, "message_choose_language", lang)
        await call.message.answer(text, reply_markup=language_selection_keyboard(btn))
        await call.answer()

    elif action == "sig":
        sig_text: str
        if user.signature:
            sig_text = await get_text(session, "message_current_signature", lang, sig=user.signature)
        else:
            sig_text = await get_text(session, "message_no_signature", lang)
        prompt = await get_text(session, "message_settings_signature_prompt", lang)
        await state.set_state(SettingsStates.waiting_for_signature)
        await call.message.answer(sig_text)
        await call.message.answer(prompt)
        await call.answer()

    elif action == "exp":
        current = _seconds_to_label(user.default_expiration_seconds, lang)
        text = await get_text(session, "message_settings_expiration", lang, current=current)
        kb = await _expiration_keyboard(session, lang)
        await call.message.answer(text, reply_markup=kb)
        await call.answer()

    elif action == "adl":
        current = _adl_seconds_to_label(user.auto_delete_seconds, lang)
        text = await get_text(session, "message_settings_auto_delete", lang, current=current)
        kb = await _auto_delete_keyboard(session, lang)
        await call.message.answer(text, reply_markup=kb)
        await call.answer()

    elif action == "set_exp":
        val = int(parts[2])
        if val == -1:
            await state.set_state(SettingsStates.waiting_for_expiration_custom)
            prompt = await get_text(session, "message_settings_custom_exp_prompt", lang)
            await call.message.answer(prompt)
        else:
            user.default_expiration_seconds = val if val > 0 else None
            await session.commit()
            text = await get_text(session, "message_settings_expiration_set", lang)
            await call.message.answer(text)
        await call.answer()

    elif action == "set_adl":
        val = int(parts[2])
        if val == -1:
            await state.set_state(SettingsStates.waiting_for_auto_delete_custom)
            prompt = await get_text(session, "message_settings_custom_adl_prompt", lang)
            await call.message.answer(prompt)
        else:
            user.auto_delete_seconds = val if val > 0 else None
            await session.commit()
            text = await get_text(session, "message_settings_auto_delete_set", lang)
            await call.message.answer(text)
        await call.answer()

    elif action == "back":
        btn = await get_texts(session, _MENU_BTN_KEYS, lang)
        menu_text = await get_text(session, "message_main_menu", lang)
        await call.message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))
        await call.answer()


@router.message(SettingsStates.waiting_for_signature)
async def receive_signature(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    await state.clear()

    if message.text and message.text.strip() == "/remove":
        user.signature = None
        await session.commit()
        text = await get_text(session, "message_settings_signature_removed", lang)
    else:
        user.signature = (message.text or "").strip()[:500]
        await session.commit()
        text = await get_text(session, "message_settings_signature_set", lang)
    await message.answer(text)


@router.message(SettingsStates.waiting_for_expiration_custom)
async def receive_expiration_custom(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    await state.clear()

    try:
        val = int((message.text or "").strip())
        if val <= 0:
            raise ValueError
        user.default_expiration_seconds = val
        await session.commit()
        text = await get_text(session, "message_settings_expiration_set", lang)
    except ValueError:
        text = await get_text(session, "message_settings_invalid_number", lang)
    await message.answer(text)


@router.message(SettingsStates.waiting_for_auto_delete_custom)
async def receive_auto_delete_custom(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    await state.clear()

    try:
        val = int((message.text or "").strip())
        if val <= 0:
            raise ValueError
        user.auto_delete_seconds = val
        await session.commit()
        text = await get_text(session, "message_settings_auto_delete_set", lang)
    except ValueError:
        text = await get_text(session, "message_settings_invalid_number", lang)
    await message.answer(text)


# ── Keyboard builders ──────────────────────────────────────────────────────────

async def _settings_keyboard(session: AsyncSession, lang: str):
    kb = InlineKeyboardBuilder()
    keys = [
        ("btn_settings_language", "uset:lang"),
        ("btn_settings_signature", "uset:sig"),
        ("btn_settings_expiration", "uset:exp"),
        ("btn_settings_auto_delete", "uset:adl"),
    ]
    for text_key, cb in keys:
        label = await get_text(session, text_key, lang)
        kb.button(text=label, callback_data=cb)
    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="uset:back")
    kb.adjust(1)
    return kb.as_markup()


async def _expiration_keyboard(session: AsyncSession, lang: str):
    kb = InlineKeyboardBuilder()
    for text_key, val in _EXP_CHOICES:
        label = await get_text(session, text_key, lang)
        kb.button(text=label, callback_data=f"uset:set_exp:{val}")
    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="uset:back")
    kb.adjust(2)
    return kb.as_markup()


async def _auto_delete_keyboard(session: AsyncSession, lang: str):
    kb = InlineKeyboardBuilder()
    for text_key, val in _ADL_CHOICES:
        label = await get_text(session, text_key, lang)
        kb.button(text=label, callback_data=f"uset:set_adl:{val}")
    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="uset:back")
    kb.adjust(2)
    return kb.as_markup()


def _seconds_to_label(secs: int | None, lang: str) -> str:
    if not secs:
        return "♾ بدون انقضا" if lang == "fa" else "♾ Never"
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _adl_seconds_to_label(secs: int | None, lang: str) -> str:
    if not secs:
        return "🔕 خاموش" if lang == "fa" else "🔕 Off"
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"
