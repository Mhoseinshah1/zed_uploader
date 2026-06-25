from __future__ import annotations

import math

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_keyboard
from bot.services.file_service import (
    build_deep_link,
    get_file_by_id,
    get_user_files,
    is_file_expired,
    soft_delete_file,
    toggle_file_active,
)
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user

router = Router()

_PAGE_SIZE = 5
_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]

_FILE_TYPE_ICONS = {
    "photo": "🖼",
    "video": "🎬",
    "document": "📄",
    "audio": "🎵",
    "voice": "🎤",
    "animation": "🎞",
    "sticker": "🎭",
    "text": "📝",
    "contact": "👤",
    "location": "📍",
}


class MyFilesButtonFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool | dict:
        if not message.text:
            return False
        tg = message.from_user
        user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
        fa = await get_text(session, "btn_my_files", "fa")
        en = await get_text(session, "btn_my_files", "en")
        if message.text not in (fa, en):
            return False
        return {"db_user": user}


@router.message(MyFilesButtonFilter())
async def show_my_files(message: Message, session: AsyncSession, db_user, bot_username: str = "") -> None:
    await _render_files_page(message, session, db_user, page=1, bot_username=bot_username, edit=False)


@router.callback_query(lambda c: c.data and c.data.startswith("myf:"))
async def myfiles_callback(call: CallbackQuery, session: AsyncSession, bot_username: str = "") -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    parts = call.data.split(":")

    action = parts[1]

    if action == "p":
        page = int(parts[2])
        await _render_files_page(call, session, user, page=page, bot_username=bot_username, edit=True)
        await call.answer()

    elif action == "l":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored and stored.owner_id == user.id:
            link = build_deep_link(stored.code, bot_username)
            link_text = await get_text(session, "message_file_link", lang, link=link)
            await call.message.answer(link_text)
        await call.answer()

    elif action == "s":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored and stored.owner_id == user.id:
            status = _file_status_label(stored, lang)
            stats_text = await get_text(
                session, "message_file_stats", lang,
                code=stored.code,
                type=_FILE_TYPE_ICONS.get(stored.file_type, "📎") + " " + stored.file_type,
                views=stored.views_count,
                likes=stored.likes_count,
                reports=stored.reports_count,
                created_at=stored.created_at.strftime("%Y-%m-%d %H:%M") if stored.created_at else "—",
                status=status,
            )
            await call.message.answer(stats_text)
        await call.answer()

    elif action == "d":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored and stored.owner_id == user.id:
            confirm_text = await get_text(session, "message_file_delete_confirm", lang, code=stored.code)
            btn_yes = await get_text(session, "btn_file_delete_confirm", lang)
            btn_cancel = await get_text(session, "btn_cancel", lang)
            kb = InlineKeyboardBuilder()
            kb.button(text=btn_yes, callback_data=f"myf:dc:{file_id}")
            kb.button(text=btn_cancel, callback_data="myf:p:1")
            kb.adjust(2)
            await call.message.answer(confirm_text, reply_markup=kb.as_markup())
        await call.answer()

    elif action == "dc":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored and stored.owner_id == user.id:
            await soft_delete_file(session, stored)
            text = await get_text(session, "message_file_deleted_success", lang)
            await call.message.answer(text)
        await call.answer()

    elif action == "t":
        file_id = int(parts[2])
        stored = await get_file_by_id(session, file_id)
        if stored and stored.owner_id == user.id:
            now_deleted = await toggle_file_active(session, stored)
            if now_deleted:
                text = await get_text(session, "message_file_disabled", lang)
            else:
                text = await get_text(session, "message_file_enabled", lang)
            await call.message.answer(text)
        await call.answer()

    elif action == "back":
        btn = await get_texts(session, _MENU_BTN_KEYS, lang)
        menu_text = await get_text(session, "message_main_menu", lang)
        await call.message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))
        await call.answer()


async def _render_files_page(
    target: Message | CallbackQuery,
    session: AsyncSession,
    user,
    page: int,
    bot_username: str,
    edit: bool,
) -> None:
    lang = user.language or "fa"
    offset = (page - 1) * _PAGE_SIZE
    files, total = await get_user_files(session, user.id, include_deleted=True, limit=_PAGE_SIZE, offset=offset)

    if total == 0:
        text = await get_text(session, "message_my_files_empty", lang)
        msg = target if isinstance(target, Message) else target.message
        await msg.answer(text)
        return

    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    page = min(page, total_pages)

    item_key = await get_text(session, "message_file_item", lang)
    items_lines: list[str] = []
    for i, f in enumerate(files, start=1 + offset):
        status = _file_status_label(f, lang)
        icon = _FILE_TYPE_ICONS.get(f.file_type, "📎")
        line = item_key.format(
            num=i,
            type=icon + " " + f.file_type,
            code=f.code,
            created_at=f.created_at.strftime("%Y-%m-%d") if f.created_at else "—",
            views=f.views_count,
            status=status,
        )
        items_lines.append(line)

    header = await get_text(
        session, "message_my_files_list", lang,
        page=page, total_pages=total_pages,
        items="\n\n".join(items_lines),
    )

    kb = InlineKeyboardBuilder()
    btn_link = await get_text(session, "btn_file_get_link", lang)
    btn_stats = await get_text(session, "btn_file_stats", lang)
    btn_del = await get_text(session, "btn_file_delete", lang)
    btn_tog = await get_text(session, "btn_file_toggle", lang)
    btn_prev = await get_text(session, "btn_prev_page", lang)
    btn_next = await get_text(session, "btn_next_page", lang)
    btn_back = await get_text(session, "btn_back", lang)

    for f in files:
        fid = f.id
        kb.button(text=btn_link, callback_data=f"myf:l:{fid}")
        kb.button(text=btn_stats, callback_data=f"myf:s:{fid}")
        kb.button(text=btn_del, callback_data=f"myf:d:{fid}")
        kb.button(text=btn_tog, callback_data=f"myf:t:{fid}")
        kb.adjust(4)

    nav_row: list[tuple[str, str]] = []
    if page > 1:
        nav_row.append((btn_prev, f"myf:p:{page - 1}"))
    nav_row.append((f"{page}/{total_pages}", "myf:noop"))
    if page < total_pages:
        nav_row.append((btn_next, f"myf:p:{page + 1}"))
    for label, cb in nav_row:
        kb.button(text=label, callback_data=cb)
    kb.adjust(*([4] * len(files) + [len(nav_row)]))

    kb.button(text=btn_back, callback_data="myf:back")
    kb.adjust(*([4] * len(files) + [len(nav_row)] + [1]))

    markup = kb.as_markup()

    if edit and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(header, reply_markup=markup)
        except Exception:
            await target.message.answer(header, reply_markup=markup)
    else:
        msg = target if isinstance(target, Message) else target.message
        await msg.answer(header, reply_markup=markup)


def _file_status_label(stored, lang: str) -> str:
    if is_file_expired(stored):
        return "⏳ منقضی" if lang == "fa" else "⏳ Expired"
    if stored.is_deleted:
        return "🗑 حذف‌شده" if lang == "fa" else "🗑 Deleted"
    return "✅ فعال" if lang == "fa" else "✅ Active"
