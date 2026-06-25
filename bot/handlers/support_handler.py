from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.setting_service import get_setting
from bot.services.text_service import get_text
from bot.services.user_service import get_or_create_user

router = Router()


class SupportButtonFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool | dict:
        if not message.text:
            return False
        tg = message.from_user
        user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
        fa = await get_text(session, "btn_support", "fa")
        en = await get_text(session, "btn_support", "en")
        if message.text not in (fa, en):
            return False
        return {"db_user": user}


@router.message(SupportButtonFilter())
async def show_support(message: Message, session: AsyncSession, db_user) -> None:
    lang = db_user.language or "fa"

    support_text = await get_setting(session, "support_text") or await get_text(session, "default_support_text", lang)
    support_url = await get_setting(session, "support_url")
    support_btn_text = await get_setting(session, "support_btn_text") or await get_text(session, "btn_support_contact", lang)

    text = await get_text(session, "message_support", lang, support_text=support_text)

    if support_url:
        kb = InlineKeyboardBuilder()
        kb.button(text=support_btn_text, url=support_url)
        await message.answer(text, reply_markup=kb.as_markup())
    else:
        await message.answer(text)
