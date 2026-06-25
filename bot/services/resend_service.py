from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message

from bot.database.models import StoredFile


async def resend_stored_file(bot: Bot, message: Message, stored: StoredFile) -> Message | None:
    """Re-deliver stored content using saved Telegram file_id or metadata.

    Returns the sent Message so callers can schedule auto-deletion.
    Never downloads or writes files to disk — only passes file_id back to Telegram.
    """
    ftype = stored.file_type
    fid = stored.telegram_file_id
    caption = stored.caption or None
    chat_id = message.chat.id

    if ftype == "photo":
        return await bot.send_photo(chat_id, fid, caption=caption)

    elif ftype == "video":
        return await bot.send_video(chat_id, fid, caption=caption)

    elif ftype == "document":
        return await bot.send_document(chat_id, fid, caption=caption)

    elif ftype == "audio":
        return await bot.send_audio(chat_id, fid, caption=caption)

    elif ftype == "voice":
        return await bot.send_voice(chat_id, fid)

    elif ftype == "animation":
        return await bot.send_animation(chat_id, fid, caption=caption)

    elif ftype == "sticker":
        return await bot.send_sticker(chat_id, fid)

    elif ftype == "text":
        text = stored.text_content or stored.caption or "—"
        return await bot.send_message(chat_id, text)

    elif ftype == "contact":
        meta = stored.metadata_json or {}
        phone = meta.get("phone_number", "")
        first = meta.get("first_name", "")
        last = meta.get("last_name")
        vcard = meta.get("vcard")
        if phone and first:
            return await bot.send_contact(chat_id, phone_number=phone, first_name=first, last_name=last, vcard=vcard)
        else:
            return await bot.send_message(chat_id, f"📞 {phone or '—'}")

    elif ftype == "location":
        meta = stored.metadata_json or {}
        lat = meta.get("latitude")
        lon = meta.get("longitude")
        if lat is not None and lon is not None:
            return await bot.send_location(chat_id, latitude=lat, longitude=lon)
        else:
            return await bot.send_message(chat_id, "📍 Location data unavailable.")

    else:
        return await bot.send_message(chat_id, f"[unsupported type: {ftype}]")
