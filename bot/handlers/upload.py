from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Animation,
    Audio,
    Contact,
    Document,
    KeyboardButton,
    Location,
    Message,
    PhotoSize,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Sticker,
    Video,
    Voice,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_keyboard
from bot.services.file_service import (
    build_deep_link,
    create_stored_file,
)
from bot.services.text_service import get_text, get_texts
from bot.services.user_service import get_or_create_user
from bot.states import UploadStates

router = Router()

_MENU_BTN_KEYS = [
    "btn_save_file", "btn_my_files", "btn_profile",
    "btn_settings", "btn_change_language", "btn_support", "btn_admin_panel",
]

# Key used to cache bot username in bot.data dict (set at startup)
BOT_USERNAME_KEY = "bot_username"


# ── Filter: matches save-file button text ──────────────────────────────────────

class SaveFileButtonFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool | dict:
        if not message.text:
            return False
        tg = message.from_user
        user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
        btn_fa = await get_text(session, "btn_save_file", "fa")
        btn_en = await get_text(session, "btn_save_file", "en")
        if message.text not in (btn_fa, btn_en):
            return False
        return {"db_user": user}


# ── Cancel filter: matches cancel/back button ──────────────────────────────────

class CancelFilter(Filter):
    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        if not message.text:
            return False
        btn_cancel_fa = await get_text(session, "btn_cancel", "fa")
        btn_cancel_en = await get_text(session, "btn_cancel", "en")
        btn_back_fa = await get_text(session, "btn_back", "fa")
        btn_back_en = await get_text(session, "btn_back", "en")
        return message.text in (btn_cancel_fa, btn_cancel_en, btn_back_fa, btn_back_en)


# ── Entry: user presses Save File ──────────────────────────────────────────────

@router.message(SaveFileButtonFilter())
async def start_save_flow(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    db_user,
) -> None:
    lang = db_user.language or "fa"
    prompt = await get_text(session, "message_send_file_to_save", lang)
    cancel_btn = await get_text(session, "btn_cancel", lang)

    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=cancel_btn)]],
        resize_keyboard=True,
    )
    await state.set_state(UploadStates.waiting_for_file)
    await state.update_data(user_id=db_user.id, lang=lang)
    await message.answer(prompt, reply_markup=cancel_kb)


# ── Cancel while waiting ───────────────────────────────────────────────────────

@router.message(UploadStates.waiting_for_file, CancelFilter())
async def cancel_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "fa")
    await state.clear()

    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")
    btn = await get_texts(session, _MENU_BTN_KEYS, lang)
    cancelled_text = await get_text(session, "message_save_cancelled", lang)
    menu_text = await get_text(session, "message_main_menu", lang)

    await message.answer(cancelled_text, reply_markup=ReplyKeyboardRemove())
    await message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))


# ── Receive content while waiting ─────────────────────────────────────────────

@router.message(UploadStates.waiting_for_file)
async def receive_file(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    lang = data.get("lang", "fa")

    tg = message.from_user
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name or "")

    stored = await _extract_and_store(message, session, user, lang)

    # Always clear FSM state and restore menu, regardless of success or unsupported type
    await state.clear()

    if stored is None:
        # Unsupported type: message already sent inside _extract_and_store;
        # restore the main menu keyboard so the user isn't left without navigation.
        btn = await get_texts(session, _MENU_BTN_KEYS, lang)
        menu_text = await get_text(session, "message_main_menu", lang)
        await message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))
        return

    # Resolve bot username from bot.data cache set at startup
    bot_username: str = bot.data.get(BOT_USERNAME_KEY, "")
    if not bot_username:
        me = await bot.get_me()
        bot_username = me.username or ""

    link = build_deep_link(stored.code, bot_username)
    success_text = await get_text(session, "message_file_saved_success", lang)
    link_text = await get_text(session, "message_file_link", lang, link=link)
    btn = await get_texts(session, _MENU_BTN_KEYS, lang)
    menu_text = await get_text(session, "message_main_menu", lang)

    await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
    await message.answer(link_text)
    await message.answer(menu_text, reply_markup=main_menu_keyboard(btn, user))


async def _extract_and_store(
    message: Message,
    session: AsyncSession,
    user,
    lang: str,
):
    """Extract metadata from message and persist to StoredFile. Returns None on unsupported type.

    NOTE: animation MUST be checked before document — Telegram sets both fields
    on GIF messages, and the more specific type (animation) takes priority.
    """

    # ── animation (GIF) — must come before document ────────────────────────────
    if message.animation:
        an: Animation = message.animation
        return await create_stored_file(
            session, user,
            file_type="animation",
            telegram_file_id=an.file_id,
            telegram_file_unique_id=an.file_unique_id,
            caption=message.caption,
            original_file_name=an.file_name,
            file_size=an.file_size,
            mime_type=an.mime_type,
        )

    # ── photo ──────────────────────────────────────────────────────────────────
    if message.photo:
        largest: PhotoSize = max(message.photo, key=lambda p: p.file_size or 0)
        return await create_stored_file(
            session, user,
            file_type="photo",
            telegram_file_id=largest.file_id,
            telegram_file_unique_id=largest.file_unique_id,
            caption=message.caption,
            file_size=largest.file_size,
        )

    # ── video ──────────────────────────────────────────────────────────────────
    if message.video:
        v: Video = message.video
        return await create_stored_file(
            session, user,
            file_type="video",
            telegram_file_id=v.file_id,
            telegram_file_unique_id=v.file_unique_id,
            caption=message.caption,
            original_file_name=v.file_name,
            file_size=v.file_size,
            mime_type=v.mime_type,
        )

    # ── document ───────────────────────────────────────────────────────────────
    if message.document:
        d: Document = message.document
        return await create_stored_file(
            session, user,
            file_type="document",
            telegram_file_id=d.file_id,
            telegram_file_unique_id=d.file_unique_id,
            caption=message.caption,
            original_file_name=d.file_name,
            file_size=d.file_size,
            mime_type=d.mime_type,
        )

    # ── audio ──────────────────────────────────────────────────────────────────
    if message.audio:
        a: Audio = message.audio
        return await create_stored_file(
            session, user,
            file_type="audio",
            telegram_file_id=a.file_id,
            telegram_file_unique_id=a.file_unique_id,
            caption=message.caption,
            original_file_name=a.file_name,
            file_size=a.file_size,
            mime_type=a.mime_type,
        )

    # ── voice ──────────────────────────────────────────────────────────────────
    if message.voice:
        vo: Voice = message.voice
        return await create_stored_file(
            session, user,
            file_type="voice",
            telegram_file_id=vo.file_id,
            telegram_file_unique_id=vo.file_unique_id,
            file_size=vo.file_size,
            mime_type=vo.mime_type,
        )

    # ── sticker ────────────────────────────────────────────────────────────────
    if message.sticker:
        st: Sticker = message.sticker
        return await create_stored_file(
            session, user,
            file_type="sticker",
            telegram_file_id=st.file_id,
            telegram_file_unique_id=st.file_unique_id,
            file_size=st.file_size,
        )

    # ── text ───────────────────────────────────────────────────────────────────
    if message.text:
        return await create_stored_file(
            session, user,
            file_type="text",
            text_content=message.text,
        )

    # ── contact ────────────────────────────────────────────────────────────────
    if message.contact:
        c: Contact = message.contact
        return await create_stored_file(
            session, user,
            file_type="contact",
            metadata_json={
                "phone_number": c.phone_number,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "user_id": c.user_id,
                "vcard": c.vcard,
            },
        )

    # ── location ───────────────────────────────────────────────────────────────
    if message.location:
        loc: Location = message.location
        return await create_stored_file(
            session, user,
            file_type="location",
            metadata_json={
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "horizontal_accuracy": loc.horizontal_accuracy,
            },
        )

    # ── unsupported ────────────────────────────────────────────────────────────
    unsupported_text = await get_text(session, "message_unsupported_file_type", lang)
    await message.answer(unsupported_text)
    return None
