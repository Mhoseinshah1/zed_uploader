from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.setting_service import get_setting


def normalize_username(raw: str) -> str:
    """Accepts 'name', '@name', 'https://t.me/name' → returns bare 'name'."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    raw = raw.replace("https://", "").replace("http://", "")
    raw = raw.replace("t.me/", "").replace("telegram.me/", "")
    raw = raw.lstrip("@/")
    return raw.split("/")[0].split("?")[0]


def username_to_url(username: str) -> str:
    username = normalize_username(username)
    return f"https://t.me/{username}" if username else ""


async def get_support_info(session: AsyncSession) -> dict:
    """Resolve support display values from BotSetting, normalized."""
    username = normalize_username(await get_setting(session, "support_username", ""))
    url = await get_setting(session, "support_url", "")
    if not url and username:
        url = username_to_url(username)
    return {
        "username": username,
        "url": url,
        "text": await get_setting(session, "support_text", ""),
        "button_text": await get_setting(session, "support_button_text", ""),
    }
