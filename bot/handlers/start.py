from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import language_selection_keyboard, main_menu_keyboard
from bot.services.delivery_service import deliver_file
from bot.services.file_service import (
    add_like,
    add_report,
    check_file_password,
    get_file_by_code,
)
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user
from bot.states import PasswordStates

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]
_LANG_BTN_KEYS = ["btn_lang_fa", "btn_lang_en"]


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
    command: CommandObject,
) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(
        session,
        telegram_id=tg.id,
        username=tg.username,
        first_name=tg.first_name or "",
    )

    payload = (command.args or "").strip()
    if payload:
        await deliver_file(bot, message, session, state, user, payload)
        return

    if not user.language:
        btn = await get_texts(session, _LANG_BTN_KEYS, "fa")
        text = await get_text(session, "message_choose_language", "fa")
        await message.answer(text, reply_markup=language_selection_keyboard(btn))
        return

    lang = user.language
    btn = await get_texts(session, _MENU_BTN_KEYS, lang)
    welcome = await get_text(session, "message_welcome", lang, name=user.first_name)
    menu_text = await get_text(session, "message_main_menu", lang)
    await message.answer(welcome)
    await message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))


@router.callback_query(lambda c: c.data and c.data.startswith("get_file_again:"))
async def get_file_again(call: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    code = call.data.split(":", 1)[1]
    await call.answer()
    # Re-run the full pipeline (forced join + password re-checked) for the resend.
    await deliver_file(bot, call.message, session, state, user, code)


@router.callback_query(lambda c: c.data and c.data.startswith("check_join:"))
async def check_join(call: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    code = call.data.split(":", 1)[1]
    status = await deliver_file(bot, call.message, session, state, user, code)
    if status == "needs_join":
        lang = user.language or "fa"
        await call.answer(await get_text(session, "message_join_not_complete", lang), show_alert=True)
    else:
        await call.answer()


@router.message(PasswordStates.waiting_for_password)
async def receive_password(message: Message, session: AsyncSession, bot: Bot, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    data = await state.get_data()
    code = data.get("file_code", "")

    stored = await get_file_by_code(session, code)
    if stored is None:
        await state.clear()
        await message.answer(await get_text(session, "message_file_not_found", lang))
        return

    if check_file_password(stored, (message.text or "").strip()):
        await state.clear()
        await deliver_file(bot, message, session, state, user, code, password_verified=True)
    else:
        await message.answer(await get_text(session, "message_password_wrong", lang))


@router.callback_query(lambda c: c.data and c.data.startswith("flike:"))
async def like_file(call: CallbackQuery, session: AsyncSession) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    code = call.data.split(":", 1)[1]
    stored = await get_file_by_code(session, code)
    if stored is None or stored.is_deleted:
        await call.answer(await get_text(session, "message_file_not_found", lang), show_alert=True)
        return
    await add_like(session, stored)
    await call.answer(await get_text(session, "message_file_liked", lang))


@router.callback_query(lambda c: c.data and c.data.startswith("freport:"))
async def report_file(call: CallbackQuery, session: AsyncSession) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    lang = user.language or "fa"
    code = call.data.split(":", 1)[1]
    stored = await get_file_by_code(session, code)
    if stored is None or stored.is_deleted:
        await call.answer(await get_text(session, "message_file_not_found", lang), show_alert=True)
        return
    await add_report(session, stored, user)
    await _maybe_auto_disable(session, stored)
    await call.answer(await get_text(session, "message_file_reported", lang), show_alert=True)


async def _maybe_auto_disable(session: AsyncSession, stored) -> None:
    """Auto-disable a file once reports reach the configured threshold (if enabled)."""
    from bot.services.setting_service import get_setting
    raw = await get_setting(session, "max_reports", "0")
    try:
        threshold = int(raw)
    except ValueError:
        threshold = 0
    if threshold > 0 and stored.reports_count >= threshold and not stored.is_deleted:
        stored.is_deleted = True
        await session.commit()
