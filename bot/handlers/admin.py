from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import FileReport, FileView, StoredFile, User
from bot.handlers.admin_settings import build_admin_settings_keyboard
from bot.keyboards.main_menu import admin_panel_keyboard, main_menu_keyboard
from bot.services.file_service import get_all_files, get_file_by_id, soft_delete_file, toggle_file_active, is_file_expired
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_ADMIN_BTN_KEYS = [
    "admin_btn_stats", "admin_btn_manage_texts",
    "admin_btn_settings", "admin_btn_files", "admin_btn_back",
]

_FILES_PAGE_SIZE = 5
_FILE_TYPE_ICONS = {
    "photo": "🖼", "video": "🎬", "document": "📄", "audio": "🎵",
    "voice": "🎤", "animation": "🎞", "sticker": "🎭",
    "text": "📝", "contact": "👤", "location": "📍",
}


class AdminPanelFilter(Filter):
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
    parts = call.data.split(":")
    action = parts[1]

    if action == "stats":
        await _show_stats(call, session, lang)

    elif action == "stats_refresh":
        await _show_stats(call, session, lang, edit=True)

    elif action == "texts_menu":
        intro = await get_text(session, "message_admin_texts_intro", lang)
        kb = InlineKeyboardBuilder()
        kb.button(text="🇮🇷 FA", callback_data="adm_t:lang:fa")
        kb.button(text="🇬🇧 EN", callback_data="adm_t:lang:en")
        back = await get_text(session, "btn_back", lang)
        kb.button(text=back, callback_data="admin:back")
        kb.adjust(2, 1)
        await call.message.answer(intro, reply_markup=kb.as_markup())

    elif action == "texts":
        intro = await get_text(session, "message_admin_texts_intro", lang)
        kb = InlineKeyboardBuilder()
        kb.button(text="🇮🇷 FA", callback_data="adm_t:lang:fa")
        kb.button(text="🇬🇧 EN", callback_data="adm_t:lang:en")
        back = await get_text(session, "btn_back", lang)
        kb.button(text=back, callback_data="admin:back")
        kb.adjust(2, 1)
        await call.message.answer(intro, reply_markup=kb.as_markup())

    elif action == "settings":
        text = await get_text(session, "message_admin_settings", lang)
        markup = await build_admin_settings_keyboard(session, lang)
        await call.message.answer(text, reply_markup=markup)

    elif action == "files":
        page = int(parts[2]) if len(parts) > 2 else 1
        await _show_admin_files(call, session, lang, page)

    elif action == "files_del":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored:
            await soft_delete_file(session, stored)
            text = await get_text(session, "message_admin_file_deleted", lang)
            await call.message.answer(text)

    elif action == "files_tog":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored:
            now_deleted = await toggle_file_active(session, stored)
            if now_deleted:
                text = await get_text(session, "message_admin_file_toggled_off", lang)
            else:
                text = await get_text(session, "message_admin_file_toggled_on", lang)
            await call.message.answer(text)

    elif action == "back":
        btn = await get_texts(session, _MENU_BTN_KEYS, lang)
        menu_text = await get_text(session, "message_main_menu", lang)
        await call.message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))

    await call.answer()


async def _show_stats(call: CallbackQuery, session: AsyncSession, lang: str, edit: bool = False) -> None:
    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    today_users = (await session.execute(
        select(func.count()).select_from(User).where(User.created_at >= today_start)
    )).scalar_one()
    week_users = (await session.execute(
        select(func.count()).select_from(User).where(User.created_at >= week_start)
    )).scalar_one()

    total_files = (await session.execute(select(func.count()).select_from(StoredFile))).scalar_one()
    deleted_files = (await session.execute(
        select(func.count()).select_from(StoredFile).where(StoredFile.is_deleted == True)  # noqa: E712
    )).scalar_one()
    expired_files = (await session.execute(
        select(func.count()).select_from(StoredFile).where(StoredFile.is_expired == True)  # noqa: E712
    )).scalar_one()
    active_files = total_files - deleted_files - expired_files

    total_views = (await session.execute(select(func.sum(StoredFile.views_count)))).scalar_one() or 0
    total_reports = (await session.execute(select(func.count()).select_from(FileReport))).scalar_one()

    text = await get_text(
        session, "message_admin_stats", lang,
        total_users=total_users,
        today_users=today_users,
        week_users=week_users,
        total_files=total_files,
        active_files=active_files,
        deleted_files=deleted_files,
        expired_files=expired_files,
        total_views=total_views,
        total_reports=total_reports,
    )

    btn_refresh = await get_text(session, "btn_admin_stats_refresh", lang)
    btn_back = await get_text(session, "btn_back", lang)
    kb = InlineKeyboardBuilder()
    kb.button(text=btn_refresh, callback_data="admin:stats_refresh")
    kb.button(text=btn_back, callback_data="admin:back")
    kb.adjust(1)

    if edit:
        try:
            await call.message.edit_text(text, reply_markup=kb.as_markup())
        except Exception:
            await call.message.answer(text, reply_markup=kb.as_markup())
    else:
        await call.message.answer(text, reply_markup=kb.as_markup())


async def _show_admin_files(call: CallbackQuery, session: AsyncSession, lang: str, page: int) -> None:
    files, total = await get_all_files(session, limit=_FILES_PAGE_SIZE, offset=(page - 1) * _FILES_PAGE_SIZE)
    total_pages = max(1, math.ceil(total / _FILES_PAGE_SIZE))
    page = min(page, total_pages)

    if total == 0:
        await call.message.answer("📁 No files found.")
        return

    items_lines: list[str] = []
    for i, f in enumerate(files, start=1 + (page - 1) * _FILES_PAGE_SIZE):
        if is_file_expired(f):
            status = "⏳"
        elif f.is_deleted:
            status = "🗑"
        else:
            status = "✅"
        icon = _FILE_TYPE_ICONS.get(f.file_type, "📎")
        owner_info = f"#{f.owner_id}"
        line = f"#{i} <code>{f.code}</code> | {icon}{f.file_type} | 👁{f.views_count} | {status}\nOwner: {owner_info}"
        items_lines.append(line)

    text = await get_text(
        session, "message_admin_files", lang,
        page=page, total_pages=total_pages,
        items="\n\n".join(items_lines),
    )

    kb = InlineKeyboardBuilder()
    for f in files:
        kb.button(text="🗑", callback_data=f"admin:files_del:{f.id}")
        kb.button(text="🔄", callback_data=f"admin:files_tog:{f.id}")
        kb.adjust(2)

    nav: list[tuple[str, str]] = []
    if page > 1:
        nav.append(("◀️", f"admin:files:{page - 1}"))
    nav.append((f"{page}/{total_pages}", "admin:noop"))
    if page < total_pages:
        nav.append(("▶️", f"admin:files:{page + 1}"))
    for lbl, cb in nav:
        kb.button(text=lbl, callback_data=cb)

    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="admin:back")
    kb.adjust(*([2] * len(files) + [len(nav)] + [1]))

    await call.message.answer(text, reply_markup=kb.as_markup())
