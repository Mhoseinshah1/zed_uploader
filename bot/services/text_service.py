from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import BotText

_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_locale_cache: dict[str, dict[str, str]] = {}


def _load_locale(lang: str) -> dict[str, str]:
    if lang not in _locale_cache:
        path = _LOCALES_DIR / f"{lang}.json"
        if path.exists():
            _locale_cache[lang] = json.loads(path.read_text(encoding="utf-8"))
        else:
            _locale_cache[lang] = {}
    return _locale_cache[lang]


async def get_text(
    session: AsyncSession,
    key: str,
    lang: str,
    fallback_lang: str = "fa",
    **kwargs: str,
) -> str:
    result = await session.execute(
        select(BotText).where(BotText.key == key, BotText.language == lang)
    )
    row = result.scalar_one_or_none()

    if row:
        text = row.value
    else:
        locale = _load_locale(lang)
        if key not in locale and lang != fallback_lang:
            locale = _load_locale(fallback_lang)
        text = locale.get(key, key)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text


async def get_texts(
    session: AsyncSession,
    keys: list[str],
    lang: str,
    fallback_lang: str = "fa",
) -> dict[str, str]:
    result = await session.execute(
        select(BotText).where(BotText.key.in_(keys), BotText.language == lang)
    )
    db_rows = {row.key: row.value for row in result.scalars()}

    locale = _load_locale(lang)
    fallback = _load_locale(fallback_lang) if lang != fallback_lang else locale

    out: dict[str, str] = {}
    for key in keys:
        if key in db_rows:
            out[key] = db_rows[key]
        elif key in locale:
            out[key] = locale[key]
        elif key in fallback:
            out[key] = fallback[key]
        else:
            out[key] = key
    return out


async def seed_default_texts(session: AsyncSession) -> None:
    rows = []
    for lang in ("fa", "en"):
        for key, value in _load_locale(lang).items():
            rows.append({"key": key, "language": lang, "value": value})

    if not rows:
        return

    stmt = (
        pg_insert(BotText)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_bot_texts_key_language")
    )
    await session.execute(stmt)
    await session.commit()
