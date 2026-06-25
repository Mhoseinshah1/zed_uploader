from __future__ import annotations

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.broadcast_service import run_broadcast
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user
from bot.states import BroadcastStates

router = Router()


async def start_text_broadcast(message: Message, session: AsyncSession, state: FSMContext, lang: str) -> None:
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(await get_text(session, "message_broadcast_ask", lang))


async def start_forward_broadcast(message: Message, session: AsyncSession, state: FSMContext, lang: str) -> None:
    await state.set_state(BroadcastStates.waiting_for_forward)
    await message.answer(await get_text(session, "message_broadcast_ask_forward", lang))


@router.message(BroadcastStates.waiting_for_message)
async def receive_broadcast_text(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await state.clear()
        return
    lang = user.language or "fa"
    text = message.text or ""
    if text.strip() == "/cancel":
        await state.clear()
        await message.answer(await get_text(session, "message_cancelled", lang))
        return
    await state.clear()
    await message.answer(await get_text(session, "message_broadcast_started", lang))
    record = await run_broadcast(bot, session, text=text)
    await message.answer(
        await get_text(
            session, "message_broadcast_done", lang,
            total=record.total_users, sent=record.sent_count, failed=record.failed_count,
        )
    )


@router.message(BroadcastStates.waiting_for_forward)
async def receive_broadcast_forward(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    if not user.is_admin:
        await state.clear()
        return
    lang = user.language or "fa"
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer(await get_text(session, "message_cancelled", lang))
        return
    await state.clear()
    await message.answer(await get_text(session, "message_broadcast_started", lang))
    record = await run_broadcast(
        bot, session,
        forward_from_chat_id=message.chat.id,
        forward_message_id=message.message_id,
    )
    await message.answer(
        await get_text(
            session, "message_broadcast_done", lang,
            total=record.total_users, sent=record.sent_count, failed=record.failed_count,
        )
    )
