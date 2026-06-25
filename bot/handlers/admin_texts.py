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
        page = 1
        await _show_text_list(call, session, chosen_lang, page, lang)

    elif action == "page":
        chosen_lang = parts[2]
        page = int(parts[3])
        await _show_text_list(call, session, chosen_lang, page, lang)

    elif action == "edit":
        record_id = int(parts[2])
        result = await session.execute(select(BotText).where(BotText.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            await call.answer("Not found.", show_alert=True)
            return

        await state.set_state(AdminTextStates.entering_value)
        await state.update_data(record_id=record_id, record_lang=record.language)

        btn_reset = await get_text(session, "btn_admin_text_reset", lang)
        btn_cancel = await get_text(session, "btn_admin_text_cancel", lang)
        kb = InlineKeyboardBuilder()
        kb.button(text=btn_reset, callback_data=f"adm_t:reset:{record_id}")
        kb.button(text=btn_cancel, callback_data=f"adm_t:lang:{record.language}")
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
    await state.clear()

    if record_id:
        result = await session.execute(select(BotText).where(BotText.id == record_id))
        record = result.scalar_one_or_none()
        if record and message.text:
            record.value = message.text.strip()
            await session.commit()

    text = await get_text(session, "message_admin_text_updated", lang)
    await message.answer(text)

    await _show_text_list_msg(message, session, record_lang, 1, lang)


async def _show_text_list(call: CallbackQuery, session: AsyncSession, chosen_lang: str, page: int, ui_lang: str) -> None:
    result = await session.execute(
        select(BotText).where(BotText.language == chosen_lang).order_by(BotText.key)
    )
    records = list(result.scalars().all())
    total = len(records)
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    page = min(page, total_pages)
    chunk = records[(page - 1) * _PAGE_SIZE: page * _PAGE_SIZE]

    text = await get_text(
        session, "message_admin_texts_list", ui_lang,
        lang=chosen_lang.upper(),
        page=page,
        total_pages=total_pages,
    )

    kb = InlineKeyboardBuilder()
    for rec in chunk:
        short_key = rec.key if len(rec.key) <= 30 else rec.key[:27] + "..."
        kb.button(text=short_key, callback_data=f"adm_t:edit:{rec.id}")

    nav: list[tuple[str, str]] = []
    if page > 1:
        nav.append(("◀️", f"adm_t:page:{chosen_lang}:{page - 1}"))
    nav.append((f"{page}/{total_pages}", "adm_t:noop"))
    if page < total_pages:
        nav.append(("▶️", f"adm_t:page:{chosen_lang}:{page + 1}"))
    for lbl, cb in nav:
        kb.button(text=lbl, callback_data=cb)

    back_label = await get_text(session, "btn_back", ui_lang)
    kb.button(text=back_label, callback_data="admin:texts_menu")
    kb.adjust(*([1] * len(chunk) + [len(nav)] + [1]))

    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=kb.as_markup())


async def _show_text_list_msg(message: Message, session: AsyncSession, chosen_lang: str, page: int, ui_lang: str) -> None:
    result = await session.execute(
        select(BotText).where(BotText.language == chosen_lang).order_by(BotText.key)
    )
    records = list(result.scalars().all())
    total = len(records)
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    chunk = records[(page - 1) * _PAGE_SIZE: page * _PAGE_SIZE]

    text = await get_text(
        session, "message_admin_texts_list", ui_lang,
        lang=chosen_lang.upper(),
        page=page,
        total_pages=total_pages,
    )

    kb = InlineKeyboardBuilder()
    for rec in chunk:
        short_key = rec.key if len(rec.key) <= 30 else rec.key[:27] + "..."
        kb.button(text=short_key, callback_data=f"adm_t:edit:{rec.id}")

    if page > 1:
        kb.button(text="◀️", callback_data=f"adm_t:page:{chosen_lang}:{page - 1}")
    if page < total_pages:
        kb.button(text="▶️", callback_data=f"adm_t:page:{chosen_lang}:{page + 1}")

    back_label = await get_text(session, "btn_back", ui_lang)
    kb.button(text=back_label, callback_data="admin:texts_menu")
    kb.adjust(*([1] * len(chunk) + [2] + [1]))

    await message.answer(text, reply_markup=kb.as_markup())
