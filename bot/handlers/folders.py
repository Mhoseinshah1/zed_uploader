from __future__ import annotations

import math

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.file_service import display_views, is_file_expired
from bot.services.folder_service import (
    count_files_in_folder,
    create_folder,
    delete_folder,
    get_files_in_folder,
    get_folder,
    list_folders,
    rename_folder,
)
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user
from bot.states import FolderStates

router = Router()

_PAGE_SIZE = 5


@router.callback_query(lambda c: c.data and c.data.startswith("fld:"))
async def folders_callback(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    parts = call.data.split(":")
    action = parts[1]

    if action == "list":
        await _render_folder_list(call.message, session, user, lang)

    elif action == "new":
        await state.set_state(FolderStates.waiting_for_name)
        await call.message.answer(await get_text(session, "message_folder_ask_name", lang))

    elif action == "open":
        folder_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 1
        await _render_folder_files(call.message, session, user, folder_id, page, lang)

    elif action == "rn":
        folder_id = int(parts[2])
        fld = await get_folder(session, folder_id)
        if fld and fld.owner_id == user.id:
            await state.set_state(FolderStates.waiting_for_rename)
            await state.update_data(folder_id=folder_id)
            await call.message.answer(await get_text(session, "message_folder_ask_rename", lang))

    elif action == "del":
        folder_id = int(parts[2])
        fld = await get_folder(session, folder_id)
        if fld and fld.owner_id == user.id:
            await delete_folder(session, fld)
            await call.message.answer(await get_text(session, "message_folder_deleted", lang))
            await _render_folder_list(call.message, session, user, lang)

    await call.answer()


@router.message(FolderStates.waiting_for_name)
async def receive_folder_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    await state.clear()
    name = (message.text or "").strip()
    if not name or name == "/cancel":
        await message.answer(await get_text(session, "message_cancelled", lang))
        return
    await create_folder(session, user.id, name)
    await message.answer(await get_text(session, "message_folder_created", lang))
    await _render_folder_list(message, session, user, lang)


@router.message(FolderStates.waiting_for_rename)
async def receive_folder_rename(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    data = await state.get_data()
    await state.clear()
    name = (message.text or "").strip()
    if not name or name == "/cancel":
        await message.answer(await get_text(session, "message_cancelled", lang))
        return
    fld = await get_folder(session, data.get("folder_id", 0))
    if fld and fld.owner_id == user.id:
        await rename_folder(session, fld, name)
        await message.answer(await get_text(session, "message_folder_renamed", lang))
        await _render_folder_list(message, session, user, lang)


async def _render_folder_list(target: Message, session: AsyncSession, user, lang: str) -> None:
    folders = await list_folders(session, user.id)
    kb = InlineKeyboardBuilder()
    for fld in folders:
        count = await count_files_in_folder(session, user.id, fld.id)
        kb.button(text=f"📂 {fld.name} ({count})", callback_data=f"fld:open:{fld.id}:1")
        kb.button(text="✏️", callback_data=f"fld:rn:{fld.id}")
        kb.button(text="🗑", callback_data=f"fld:del:{fld.id}")
    new_label = await get_text(session, "btn_folder_new", lang)
    back_label = await get_text(session, "btn_back", lang)
    kb.button(text=new_label, callback_data="fld:new")
    kb.button(text=back_label, callback_data="myf:p:1")
    kb.adjust(*([3] * len(folders) + [1, 1]))
    text = await get_text(session, "message_folders_list", lang, count=len(folders))
    await target.answer(text, reply_markup=kb.as_markup())


async def _render_folder_files(
    target: Message, session: AsyncSession, user, folder_id: int, page: int, lang: str,
) -> None:
    fld = await get_folder(session, folder_id)
    if fld is None or fld.owner_id != user.id:
        await target.answer(await get_text(session, "message_folder_not_found", lang))
        return
    offset = (page - 1) * _PAGE_SIZE
    files, total = await get_files_in_folder(session, user.id, folder_id, limit=_PAGE_SIZE, offset=offset)
    total_pages = max(1, math.ceil(total / _PAGE_SIZE)) if total else 1

    if total == 0:
        lines = await get_text(session, "message_folder_empty", lang)
    else:
        lines = "\n".join(
            f"<code>{f.code}</code> | {f.file_type} | 👁{display_views(f)} | "
            + ("⏳" if is_file_expired(f) else "✅")
            for f in files
        )
    text = await get_text(
        session, "message_folder_files", lang,
        name=fld.name, page=page, total_pages=total_pages, items=lines,
    )
    kb = InlineKeyboardBuilder()
    if page > 1:
        kb.button(text="◀️", callback_data=f"fld:open:{folder_id}:{page - 1}")
    if page < total_pages:
        kb.button(text="▶️", callback_data=f"fld:open:{folder_id}:{page + 1}")
    kb.button(text=await get_text(session, "btn_back", lang), callback_data="fld:list")
    kb.adjust(2, 1)
    await target.answer(text, reply_markup=kb.as_markup())
