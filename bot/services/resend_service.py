from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message

from bot.database.models import StoredFile


async def resend_stored_file(bot: Bot, message: Message, stored: StoredFile) -> None:
    """Re-deliver stored content to the user using the saved Telegram file_id or metadata.

    Never downloads or writes files to disk — only passes file_id back to Telegram.
    """
    ftype = stored.file_type
    fid = stored.telegram_file_id
    caption = stored.caption or None
    chat_id = message.chat.id

    if ftype == "photo":
        await bot.send_photo(chat_id, fid, caption=caption)

    elif ftype == "video":
        await bot.send_video(chat_id, fid, caption=caption)

    elif ftype == "document":
        await bot.send_document(chat_id, fid, caption=caption)

    elif ftype == "audio":
        await bot.send_audio(chat_id, fid, caption=caption)

    elif ftype == "voice":
        await bot.send_voice(chat_id, fid)

    elif ftype == "animation":
        await bot.send_animation(chat_id, fid, caption=caption)

    elif ftype == "sticker":
        await bot.send_sticker(chat_id, fid)

    elif ftype == "text":
        text = stored.text_content or stored.caption or "—"
        await bot.send_message(chat_id, text)

    elif ftype == "contact":
        meta = stored.metadata_json or {}
        phone = meta.get("phone_number", "")
        first = meta.get("first_name", "")
        last = meta.get("last_name")
        vcard = meta.get("vcard")
        if phone and first:
            await bot.send_contact(chat_id, phone_number=phone, first_name=first, last_name=last, vcard=vcard)
        else:
            await bot.send_message(chat_id, f"📞 {phone or '—'}")

    elif ftype == "location":
        meta = stored.metadata_json or {}
        lat = meta.get("latitude")
        lon = meta.get("longitude")
        if lat is not None and lon is not None:
            await bot.send_location(chat_id, latitude=lat, longitude=lon)
        else:
            await bot.send_message(chat_id, "📍 Location data unavailable.")

    else:
        await bot.send_message(chat_id, f"[unsupported type: {ftype}]")
