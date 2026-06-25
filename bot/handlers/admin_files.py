from __future__ import annotations

import math

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.file_service import (
    build_deep_link,
    display_views,
    get_file_by_id,
    get_files_by_owner_telegram_id,
    is_file_expired,
    regenerate_code,
    remove_file_expiration,
    remove_file_password,
    set_fake_views,
    set_file_expiration,
    set_file_password,
    soft_delete_file,
    toggle_file_active,
    toggle_public,
)
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.states import AdminFileStates

router = Router()

_PAGE_SIZE = 5
_CATS = ["all", "active", "deleted", "expired"]


async def ask_for_user_id(message: Message, session: AsyncSession, state: FSMContext, lang: str) -> None:
    await state.set_state(AdminFileStates.waiting_for_user_id)
    await message.answer(await get_text(session, "message_admin_files_ask_user", lang))


@router.message(AdminFileStates.waiting_for_user_id)
async def receive_user_id(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    admin, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not admin.is_admin:
        await state.clear()
        return
    lang = admin.language or "fa"
    raw = (message.text or "").strip()
    if raw == "/cancel":
        await state.clear()
        await message.answer(await get_text(session, "message_cancelled", lang))
        return
    try:
        target_id = int(raw)
    except ValueError:
        await message.answer(await get_text(session, "message_admin_files_bad_id", lang))
        return
    await state.clear()
    await _show_user_overview(message, session, lang, target_id)


async def _show_user_overview(target: Message, session: AsyncSession, lang: str, telegram_id: int) -> None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        await target.answer(await get_text(session, "message_admin_user_not_found", lang))
        return
    _, total = await get_files_by_owner_telegram_id(session, telegram_id, "all", limit=1, offset=0)
    _, active = await get_files_by_owner_telegram_id(session, telegram_id, "active", limit=1, offset=0)
    _, deleted = await get_files_by_owner_telegram_id(session, telegram_id, "deleted", limit=1, offset=0)
    _, expired = await get_files_by_owner_telegram_id(session, telegram_id, "expired", limit=1, offset=0)

    text = await get_text(
        session, "message_admin_user_overview", lang,
        telegram_id=user.telegram_id,
        username=user.username or "—",
        first_name=user.first_name or "—",
        total=total, active=active, deleted=deleted, expired=expired,
    )
    kb = InlineKeyboardBuilder()
    for cat in _CATS:
        label = await get_text(session, f"btn_admin_files_cat_{cat}", lang)
        kb.button(text=label, callback_data=f"afm:cat:{telegram_id}:{cat}:1")
    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="admin:back")
    kb.adjust(2, 2, 1)
    await target.answer(text, reply_markup=kb.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("afm:"))
async def admin_files_callback(
    call: CallbackQuery, session: AsyncSession, state: FSMContext, bot_username: str = "",
) -> None:
    tg = call.from_user
    admin, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not admin.is_admin:
        await call.answer("Access denied.", show_alert=True)
        return
    lang = admin.language or "fa"
    parts = call.data.split(":")
    action = parts[1]

    if action == "cat":
        telegram_id, cat, page = int(parts[2]), parts[3], int(parts[4])
        await _show_files_page(call, session, lang, telegram_id, cat, page, bot_username)
        await call.answer()
        return

    # Per-file actions reference file id: afm:<action>:<file_id>:<telegram_id>:<cat>:<page>
    file_id = int(parts[2])
    telegram_id, cat, page = int(parts[3]), parts[4], int(parts[5])
    stored = await get_file_by_id(session, file_id)
    if stored is None:
        await call.answer("Not found.", show_alert=True)
        return

    if action == "l":
        link = build_deep_link(stored.code, bot_username)
        await call.message.answer(await get_text(session, "message_file_link", lang, link=link))
    elif action == "rg":
        new_code = await regenerate_code(session, stored)
        link = build_deep_link(new_code, bot_username)
        await call.message.answer(await get_text(session, "message_file_regenerated", lang, link=link))
    elif action == "s":
        await call.message.answer(
            await get_text(
                session, "message_file_stats", lang,
                code=stored.code, type=stored.file_type,
                views=display_views(stored), likes=stored.likes_count,
                reports=stored.reports_count,
                created_at=stored.created_at.strftime("%Y-%m-%d %H:%M") if stored.created_at else "—",
                status=_status(stored, lang),
            )
        )
    elif action == "d":
        await soft_delete_file(session, stored)
        await call.message.answer(await get_text(session, "message_admin_file_deleted", lang))
    elif action == "e":
        await toggle_file_active(session, stored)
        await call.message.answer(await get_text(session, "message_admin_file_toggled_on", lang))
    elif action == "rmexp":
        await remove_file_expiration(session, stored)
        await call.message.answer(await get_text(session, "message_expiration_removed", lang))
    elif action == "rmpw":
        await remove_file_password(session, stored)
        await call.message.answer(await get_text(session, "message_password_removed", lang))
    elif action == "exp":
        await state.set_state(AdminFileStates.waiting_for_expiration)
        await state.update_data(file_id=file_id)
        await call.message.answer(await get_text(session, "message_admin_ask_expiration", lang))
    elif action == "pw":
        await state.set_state(AdminFileStates.waiting_for_password)
        await state.update_data(file_id=file_id)
        await call.message.answer(await get_text(session, "message_admin_ask_password", lang))
    elif action == "pub":
        now_public = await toggle_public(session, stored)
        key = "message_file_made_public" if now_public else "message_file_made_private"
        await call.message.answer(await get_text(session, key, lang))
    elif action == "fv":
        await state.set_state(AdminFileStates.waiting_for_fake_views)
        await state.update_data(file_id=file_id)
        await call.message.answer(await get_text(session, "message_admin_ask_fake_views", lang))

    await call.answer()


@router.message(AdminFileStates.waiting_for_expiration)
async def receive_expiration(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    admin, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not admin.is_admin:
        await state.clear()
        return
    lang = admin.language or "fa"
    data = await state.get_data()
    await state.clear()
    stored = await get_file_by_id(session, data.get("file_id", 0))
    if stored is None:
        return
    try:
        seconds = int((message.text or "").strip())
    except ValueError:
        await message.answer(await get_text(session, "message_settings_invalid_number", lang))
        return
    await set_file_expiration(session, stored, seconds if seconds > 0 else None)
    await message.answer(await get_text(session, "message_expiration_set", lang))


@router.message(AdminFileStates.waiting_for_password)
async def receive_password(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    admin, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not admin.is_admin:
        await state.clear()
        return
    lang = admin.language or "fa"
    data = await state.get_data()
    await state.clear()
    stored = await get_file_by_id(session, data.get("file_id", 0))
    if stored is None:
        return
    pw = (message.text or "").strip()
    if pw == "/remove":
        await remove_file_password(session, stored)
        await message.answer(await get_text(session, "message_password_removed", lang))
    else:
        await set_file_password(session, stored, pw)
        await message.answer(await get_text(session, "message_password_set", lang))


@router.message(AdminFileStates.waiting_for_fake_views)
async def receive_fake_views(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    admin, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not admin.is_admin:
        await state.clear()
        return
    lang = admin.language or "fa"
    data = await state.get_data()
    await state.clear()
    stored = await get_file_by_id(session, data.get("file_id", 0))
    if stored is None:
        return
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer(await get_text(session, "message_settings_invalid_number", lang))
        return
    await set_fake_views(session, stored, amount)
    await message.answer(await get_text(session, "message_admin_fake_views_set", lang))


async def _show_files_page(
    call: CallbackQuery, session: AsyncSession, lang: str,
    telegram_id: int, cat: str, page: int, bot_username: str,
) -> None:
    offset = (page - 1) * _PAGE_SIZE
    files, total = await get_files_by_owner_telegram_id(session, telegram_id, cat, limit=_PAGE_SIZE, offset=offset)
    if total == 0:
        await call.message.answer(await get_text(session, "message_admin_files_empty", lang))
        return
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))

    lines = []
    for i, f in enumerate(files, start=1 + offset):
        lines.append(
            f"#{i} <code>{f.code}</code> | {f.file_type} | 👁{display_views(f)} | {_status(f, lang)}"
        )
    header = await get_text(
        session, "message_admin_files_list", lang,
        page=page, total_pages=total_pages, items="\n".join(lines),
    )

    kb = InlineKeyboardBuilder()
    suffix = f"{telegram_id}:{cat}:{page}"
    adj: list[int] = []
    for f in files:
        kb.button(text=f"🔗 {f.code}", callback_data=f"afm:l:{f.id}:{suffix}")
        kb.button(text="♻️", callback_data=f"afm:rg:{f.id}:{suffix}")
        kb.button(text="📊", callback_data=f"afm:s:{f.id}:{suffix}")
        kb.button(text="🗑", callback_data=f"afm:d:{f.id}:{suffix}")
        kb.button(text="✅", callback_data=f"afm:e:{f.id}:{suffix}")
        kb.button(text="⏳", callback_data=f"afm:exp:{f.id}:{suffix}")
        kb.button(text="🧹", callback_data=f"afm:rmexp:{f.id}:{suffix}")
        kb.button(text="🔐", callback_data=f"afm:pw:{f.id}:{suffix}")
        kb.button(text="🌐" if f.is_public else "🔒", callback_data=f"afm:pub:{f.id}:{suffix}")
        kb.button(text="👁±", callback_data=f"afm:fv:{f.id}:{suffix}")
        adj.append(10)

    nav: list[tuple[str, str]] = []
    if page > 1:
        nav.append(("◀️", f"afm:cat:{telegram_id}:{cat}:{page - 1}"))
    nav.append((f"{page}/{total_pages}", "afm:noop"))
    if page < total_pages:
        nav.append(("▶️", f"afm:cat:{telegram_id}:{cat}:{page + 1}"))
    for lbl, cb in nav:
        kb.button(text=lbl, callback_data=cb)
    adj.append(len(nav))

    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data=f"afm:cat:{telegram_id}:all:1")
    adj.append(1)
    kb.adjust(*adj)
    await call.message.answer(header, reply_markup=kb.as_markup())


def _status(stored, lang: str) -> str:
    if is_file_expired(stored):
        return "⏳" + (" منقضی" if lang == "fa" else " Expired")
    if stored.is_deleted:
        return "🗑" + (" حذف‌شده" if lang == "fa" else " Deleted")
    return "✅" + (" فعال" if lang == "fa" else " Active")
