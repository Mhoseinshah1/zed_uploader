from __future__ import annotations

import json
import math
from pathlib import Path

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import BotText
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user
from bot.states import AdminTextStates

router = Router()

_PAGE_SIZE = 8
_LOCALES_DIR = Path(__file__).parent.parent / "locales"

# Category id → (label_text_key, list of key-prefixes). "all" = the full list.
_CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("menu_btn",   "cat_menu_buttons",   ["btn_save_file", "btn_my_files", "btn_profile", "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel", "btn_back", "btn_cancel", "btn_lang_"]),
    ("menu_msg",   "cat_menu_messages",  ["message_welcome", "message_main_menu", "message_profile", "message_choose_language", "message_language_changed"]),
    ("admin_btn",  "cat_admin_buttons",  ["admin_btn_", "btn_admin_"]),
    ("admin_msg",  "cat_admin_messages", ["message_admin_"]),
    ("saving",     "cat_file_saving",    ["message_send_file", "message_unsupported", "message_file_saved", "message_file_link", "message_save_cancelled"]),
    ("myfiles",    "cat_my_files",       ["btn_file_", "btn_folder", "btn_folders", "message_my_files", "message_file_item", "message_file_stats", "message_file_delete", "message_file_enabled", "message_file_disabled", "message_file_regenerated", "message_file_made_", "message_file_moved", "file_status_", "btn_prev_page", "btn_next_page", "message_move_", "message_folder"]),
    ("settings",   "cat_settings",       ["btn_settings_", "message_settings_", "exp_", "adl_", "message_current_signature", "message_no_signature"]),
    ("support",    "cat_support",        ["message_support", "default_support_text", "btn_support_contact"]),
    ("forced",     "cat_forced_join",    ["message_forced_join", "message_join_", "message_fj", "fj_status_", "btn_fj_", "btn_check_join"]),
    ("password",   "cat_password",       ["message_password", "message_myfiles_ask_password"]),
    ("expiration", "cat_expiration",     ["message_expiration_", "message_auto_delete", "message_file_expires", "message_file_no_expiry", "message_myfiles_ask_expiration", "btn_get_file_again"]),
    ("errors",     "cat_errors",         ["error_", "message_file_not_found", "message_file_deleted", "message_file_expired", "message_file_private", "message_cancelled"]),
    ("all",        "cat_search_all",     []),
]


def _category_prefixes(cat_id: str) -> list[str]:
    for cid, _, prefixes in _CATEGORIES:
        if cid == cat_id:
            return prefixes
    return []


def _load_default(lang: str) -> dict:
    path = _LOCALES_DIR / f"{lang}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@router.callback_query(lambda c: c.data and c.data.startswith("adm_t:"))
async def admin_texts_callback(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await call.answer("Access denied.", show_alert=True)
        return

    lang = user.language or "fa"
    parts = call.data.split(":")
    action = parts[1]

    if action == "lang":
        chosen_lang = parts[2]
        await _show_categories(call, session, chosen_lang, lang)

    elif action == "cat":
        chosen_lang = parts[2]
        cat_id = parts[3]
        page = int(parts[4]) if len(parts) > 4 else 1
        await _show_text_list(call, session, chosen_lang, cat_id, page, lang)

    elif action == "edit":
        record_id = int(parts[2])
        cat_id = parts[3] if len(parts) > 3 else "all"
        result = await session.execute(select(BotText).where(BotText.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            await call.answer("Not found.", show_alert=True)
            return

        await state.set_state(AdminTextStates.entering_value)
        await state.update_data(record_id=record_id, record_lang=record.language, record_cat=cat_id)

        btn_reset = await get_text(session, "btn_admin_text_reset", lang)
        btn_cancel = await get_text(session, "btn_admin_text_cancel", lang)
        kb = InlineKeyboardBuilder()
        kb.button(text=btn_reset, callback_data=f"adm_t:reset:{record_id}")
        kb.button(text=btn_cancel, callback_data=f"adm_t:cat:{record.language}:{cat_id}:1")
        kb.adjust(2)

        text = await get_text(
            session, "message_admin_text_current", lang,
            key=record.key,
            value=record.value[:400],
        )
        await call.message.answer(text, reply_markup=kb.as_markup())

    elif action == "reset":
        record_id = int(parts[2])
        await state.clear()
        result = await session.execute(select(BotText).where(BotText.id == record_id))
        record = result.scalar_one_or_none()
        if record:
            defaults = _load_default(record.language)
            if record.key in defaults:
                record.value = defaults[record.key]
                await session.commit()
        text = await get_text(session, "message_admin_text_reset", lang)
        await call.message.answer(text)

    await call.answer()


@router.message(AdminTextStates.entering_value)
async def receive_text_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await state.clear()
        return

    lang = user.language or "fa"
    data = await state.get_data()
    record_id = data.get("record_id")
    record_lang = data.get("record_lang", "fa")
    record_cat = data.get("record_cat", "all")
    await state.clear()

    if record_id:
        result = await session.execute(select(BotText).where(BotText.id == record_id))
        record = result.scalar_one_or_none()
        if record and message.text:
            record.value = message.text.strip()
            await session.commit()

    text = await get_text(session, "message_admin_text_updated", lang)
    await message.answer(text)

    await _render_list(message, session, record_lang, record_cat, 1, lang)


async def _filtered_records(session: AsyncSession, chosen_lang: str, cat_id: str) -> list[BotText]:
    result = await session.execute(
        select(BotText).where(BotText.language == chosen_lang).order_by(BotText.key)
    )
    records = list(result.scalars().all())
    prefixes = _category_prefixes(cat_id)
    if not prefixes:  # "all" / search
        return records
    return [r for r in records if any(r.key.startswith(p) for p in prefixes)]


async def _show_categories(call: CallbackQuery, session: AsyncSession, chosen_lang: str, ui_lang: str) -> None:
    kb = InlineKeyboardBuilder()
    for cid, label_key, _ in _CATEGORIES:
        label = await get_text(session, label_key, ui_lang)
        kb.button(text=label, callback_data=f"adm_t:cat:{chosen_lang}:{cid}:1")
    back_label = await get_text(session, "btn_back", ui_lang)
    kb.button(text=back_label, callback_data="admin:texts_menu")
    kb.adjust(2)
    text = await get_text(session, "message_admin_texts_categories", ui_lang, lang=chosen_lang.upper())
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=kb.as_markup())


def _build_list_markup(records: list[BotText], chosen_lang: str, cat_id: str, page: int, total_pages: int, back_label: str):
    chunk = records[(page - 1) * _PAGE_SIZE: page * _PAGE_SIZE]
    kb = InlineKeyboardBuilder()
    for rec in chunk:
        short_key = rec.key if len(rec.key) <= 30 else rec.key[:27] + "..."
        kb.button(text=short_key, callback_data=f"adm_t:edit:{rec.id}:{cat_id}")
    nav: list[tuple[str, str]] = []
    if page > 1:
        nav.append(("◀️", f"adm_t:cat:{chosen_lang}:{cat_id}:{page - 1}"))
    nav.append((f"{page}/{total_pages}", "adm_t:noop"))
    if page < total_pages:
        nav.append(("▶️", f"adm_t:cat:{chosen_lang}:{cat_id}:{page + 1}"))
    for lbl, cb in nav:
        kb.button(text=lbl, callback_data=cb)
    kb.button(text=back_label, callback_data=f"adm_t:lang:{chosen_lang}")
    kb.adjust(*([1] * len(chunk) + [len(nav)] + [1]))
    return kb.as_markup(), len(chunk)


async def _show_text_list(call: CallbackQuery, session: AsyncSession, chosen_lang: str, cat_id: str, page: int, ui_lang: str) -> None:
    records = await _filtered_records(session, chosen_lang, cat_id)
    total_pages = max(1, math.ceil(len(records) / _PAGE_SIZE))
    page = min(max(1, page), total_pages)
    text = await get_text(
        session, "message_admin_texts_list", ui_lang,
        lang=chosen_lang.upper(), page=page, total_pages=total_pages,
    )
    back_label = await get_text(session, "btn_back", ui_lang)
    markup, _ = _build_list_markup(records, chosen_lang, cat_id, page, total_pages, back_label)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)


async def _render_list(message: Message, session: AsyncSession, chosen_lang: str, cat_id: str, page: int, ui_lang: str) -> None:
    records = await _filtered_records(session, chosen_lang, cat_id)
    total_pages = max(1, math.ceil(len(records) / _PAGE_SIZE))
    page = min(max(1, page), total_pages)
    text = await get_text(
        session, "message_admin_texts_list", ui_lang,
        lang=chosen_lang.upper(), page=page, total_pages=total_pages,
    )
    back_label = await get_text(session, "btn_back", ui_lang)
    markup, _ = _build_list_markup(records, chosen_lang, cat_id, page, total_pages, back_label)
    await message.answer(text, reply_markup=markup)
