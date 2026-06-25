from __future__ import annotations

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.forced_join_service import (
    add_channel,
    delete_channel,
    get_channel,
    is_forced_join_enabled,
    list_channels,
    set_forced_join_enabled,
    toggle_channel,
)
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user
from bot.states import ForcedJoinStates

router = Router()


async def build_forced_join_keyboard(session: AsyncSession, lang: str):
    enabled = await is_forced_join_enabled(session)
    channels = await list_channels(session)
    kb = InlineKeyboardBuilder()

    toggle_label = await get_text(
        session, "btn_fj_disable" if enabled else "btn_fj_enable", lang
    )
    kb.button(text=toggle_label, callback_data="adm_fj:toggle")
    add_label = await get_text(session, "btn_fj_add_channel", lang)
    kb.button(text=add_label, callback_data="adm_fj:add")

    for ch in channels:
        mark = "✅" if ch.is_active else "🚫"
        kb.button(text=f"{mark} {ch.title}", callback_data=f"adm_fj:ch:{ch.id}")

    back = await get_text(session, "btn_back", lang)
    kb.button(text=back, callback_data="admin:back")
    kb.adjust(2, *([1] * len(channels)), 1)
    return kb.as_markup()


async def _show_menu(target, session: AsyncSession, lang: str) -> None:
    enabled = await is_forced_join_enabled(session)
    status = await get_text(
        session, "fj_status_on" if enabled else "fj_status_off", lang
    )
    text = await get_text(session, "message_forced_join_admin", lang, status=status)
    markup = await build_forced_join_keyboard(session, lang)
    await target.answer(text, reply_markup=markup)


@router.callback_query(lambda c: c.data and c.data.startswith("adm_fj:"))
async def forced_join_callback(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    tg = call.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await call.answer("Access denied.", show_alert=True)
        return

    lang = user.language or "fa"
    parts = call.data.split(":")
    action = parts[1]

    if action == "menu":
        await _show_menu(call.message, session, lang)

    elif action == "toggle":
        new_val = not await is_forced_join_enabled(session)
        await set_forced_join_enabled(session, new_val)
        await _show_menu(call.message, session, lang)

    elif action == "add":
        await state.set_state(ForcedJoinStates.waiting_for_invite_link)
        await call.message.answer(await get_text(session, "message_fj_ask_invite", lang))

    elif action == "ch":
        ch = await get_channel(session, int(parts[2]))
        if not ch:
            await call.answer("Not found.", show_alert=True)
            return
        status = await get_text(session, "fj_status_on" if ch.is_active else "fj_status_off", lang)
        text = await get_text(
            session, "message_fj_channel_detail", lang,
            title=ch.title, chat_id=ch.chat_id,
            invite_link=ch.invite_link or "—", status=status,
        )
        kb = InlineKeyboardBuilder()
        tog = await get_text(session, "btn_fj_toggle_channel", lang)
        dele = await get_text(session, "btn_fj_delete_channel", lang)
        back = await get_text(session, "btn_back", lang)
        kb.button(text=tog, callback_data=f"adm_fj:tog:{ch.id}")
        kb.button(text=dele, callback_data=f"adm_fj:del:{ch.id}")
        kb.button(text=back, callback_data="adm_fj:menu")
        kb.adjust(2, 1)
        await call.message.answer(text, reply_markup=kb.as_markup())

    elif action == "tog":
        ch = await get_channel(session, int(parts[2]))
        if ch:
            await toggle_channel(session, ch)
        await _show_menu(call.message, session, lang)

    elif action == "del":
        ch = await get_channel(session, int(parts[2]))
        if ch:
            await delete_channel(session, ch)
            await call.message.answer(await get_text(session, "message_fj_channel_deleted", lang))
        await _show_menu(call.message, session, lang)

    await call.answer()


@router.message(ForcedJoinStates.waiting_for_invite_link)
async def receive_invite_link(message: Message, session: AsyncSession, state: FSMContext) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await state.clear()
        return
    lang = user.language or "fa"
    link = (message.text or "").strip()
    if link == "/cancel":
        await state.clear()
        await message.answer(await get_text(session, "message_cancelled", lang))
        return
    await state.update_data(invite_link=link)
    await state.set_state(ForcedJoinStates.waiting_for_chat_id)
    await message.answer(await get_text(session, "message_fj_ask_chat_id", lang))


@router.message(ForcedJoinStates.waiting_for_chat_id)
async def receive_chat_id(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await state.clear()
        return
    lang = user.language or "fa"
    data = await state.get_data()
    invite_link = data.get("invite_link")

    chat_id: int | None = None
    # Admin forwarded a message from the channel
    if message.forward_from_chat is not None:
        chat_id = message.forward_from_chat.id
    else:
        raw = (message.text or "").strip()
        if raw == "/cancel":
            await state.clear()
            await message.answer(await get_text(session, "message_cancelled", lang))
            return
        try:
            chat_id = int(raw)
        except ValueError:
            await message.answer(await get_text(session, "message_fj_invalid_chat_id", lang))
            return

    await state.clear()

    title = str(chat_id)
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or chat.full_name or str(chat_id)
        if not invite_link and getattr(chat, "username", None):
            invite_link = f"https://t.me/{chat.username}"
    except TelegramAPIError:
        # Bot not in channel yet — store anyway; membership checks will warn.
        await message.answer(await get_text(session, "message_fj_bot_not_admin", lang))

    ch = await add_channel(session, chat_id=chat_id, title=title, invite_link=invite_link)
    await message.answer(
        await get_text(session, "message_fj_channel_added", lang, title=ch.title, chat_id=ch.chat_id)
    )
