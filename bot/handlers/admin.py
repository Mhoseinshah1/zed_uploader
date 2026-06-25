from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import FileReport, RequiredChannel, StoredFile, User
from bot.handlers.admin_files import ask_for_user_id
from bot.handlers.admin_settings import build_admin_settings_keyboard
from bot.handlers.broadcast import start_forward_broadcast, start_text_broadcast
from bot.keyboards.main_menu import admin_panel_keyboard, main_menu_keyboard
from bot.services.forced_join_service import is_forced_join_enabled
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.states import AdminUserStates

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_ADMIN_BTN_KEYS = [
    "admin_btn_stats", "admin_btn_users", "admin_btn_files",
    "admin_btn_forced_join", "admin_btn_manage_texts", "admin_btn_settings",
    "admin_btn_support", "admin_btn_broadcast", "admin_btn_fwd_broadcast",
    "admin_btn_reports", "admin_btn_back",
]

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
async def admin_callback(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
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

    elif action == "users":
        await state.set_state(AdminUserStates.waiting_for_user_id)
        await call.message.answer(await get_text(session, "message_admin_users_ask", lang))

    elif action == "support":
        text = await get_text(session, "message_admin_settings", lang)
        markup = await build_admin_settings_keyboard(session, lang)
        await call.message.answer(text, reply_markup=markup)

    elif action == "broadcast":
        await start_text_broadcast(call.message, session, state, lang)

    elif action == "fwd_broadcast":
        await start_forward_broadcast(call.message, session, state, lang)

    elif action == "reports":
        await _show_reports(call, session, lang)

    elif action == "ublock":
        target = await get_user_by_telegram_id(session, int(parts[2]))
        if target:
            target.is_blocked = not target.is_blocked
            await session.commit()
            key = "message_admin_user_blocked" if target.is_blocked else "message_admin_user_unblocked"
            await call.message.answer(await get_text(session, key, lang))

    elif action == "rdel":
        from bot.services.file_service import get_file_by_id, soft_delete_file
        stored = await get_file_by_id(session, int(parts[2]))
        if stored:
            await soft_delete_file(session, stored)
            await call.message.answer(await get_text(session, "message_admin_file_deleted", lang))

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
        await ask_for_user_id(call.message, session, state, lang)

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
    total_likes = (await session.execute(select(func.sum(StoredFile.likes_count)))).scalar_one() or 0
    total_reports = (await session.execute(select(func.count()).select_from(FileReport))).scalar_one()
    total_channels = (await session.execute(select(func.count()).select_from(RequiredChannel))).scalar_one()
    fj_enabled = await is_forced_join_enabled(session)
    fj_status = await get_text(session, "fj_status_on" if fj_enabled else "fj_status_off", lang)

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
        total_likes=total_likes,
        total_reports=total_reports,
        total_channels=total_channels,
        forced_join=fj_status,
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


async def _show_reports(call: CallbackQuery, session: AsyncSession, lang: str) -> None:
    """Top reported, still-active files."""
    result = await session.execute(
        select(StoredFile)
        .where(StoredFile.reports_count > 0, StoredFile.is_deleted == False)  # noqa: E712
        .order_by(StoredFile.reports_count.desc())
        .limit(10)
    )
    files = list(result.scalars().all())
    if not files:
        await call.message.answer(await get_text(session, "message_admin_reports_empty", lang))
        return

    lines = [
        f"<code>{f.code}</code> | {f.file_type} | ⚠️{f.reports_count} | 👁{f.views_count}"
        for f in files
    ]
    text = await get_text(session, "message_admin_reports", lang, items="\n".join(lines))
    kb = InlineKeyboardBuilder()
    for f in files:
        kb.button(text=f"🗑 {f.code}", callback_data=f"admin:rdel:{f.id}")
    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="admin:back")
    kb.adjust(1)
    await call.message.answer(text, reply_markup=kb.as_markup())


@router.message(AdminUserStates.waiting_for_user_id)
async def receive_admin_user_id(message: Message, session: AsyncSession, state: FSMContext) -> None:
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

    target = await get_user_by_telegram_id(session, target_id)
    if target is None:
        await message.answer(await get_text(session, "message_admin_user_not_found", lang))
        return

    file_count = (await session.execute(
        select(func.count()).select_from(StoredFile).where(StoredFile.owner_id == target.id)
    )).scalar_one()
    block_status = await get_text(
        session, "user_blocked" if target.is_blocked else "user_active", lang
    )
    text = await get_text(
        session, "message_admin_user_info", lang,
        telegram_id=target.telegram_id,
        username=target.username or "—",
        first_name=target.first_name or "—",
        file_count=file_count,
        created_at=target.created_at.strftime("%Y-%m-%d") if target.created_at else "—",
        status=block_status,
    )
    kb = InlineKeyboardBuilder()
    toggle_key = "btn_admin_unblock" if target.is_blocked else "btn_admin_block"
    kb.button(text=await get_text(session, toggle_key, lang), callback_data=f"admin:ublock:{target.telegram_id}")
    kb.button(text=await get_text(session, "btn_admin_view_user_files", lang), callback_data=f"afm:cat:{target.telegram_id}:all:1")
    kb.button(text=await get_text(session, "btn_back", lang), callback_data="admin:back")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup())


