import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database import init_db
from bot.database.session import async_session_factory
from bot.handlers import main_router
from bot.middlewares import DbSessionMiddleware
from bot.services.text_service import seed_default_texts

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Resolved once at startup and injected into FSM handlers via bot.get_me()
_bot_username: str = ""


async def on_startup(bot: Bot) -> None:
    global _bot_username

    logger.info("Running database initialization...")
    await init_db()

    logger.info("Seeding default bot texts...")
    async with async_session_factory() as session:
        await seed_default_texts(session)

    # Cache bot username so deep-link generation works even if BOT_USERNAME is unset
    if not settings.BOT_USERNAME:
        me = await bot.get_me()
        _bot_username = me.username or ""
        logger.info("Resolved bot username: @%s", _bot_username)
    else:
        _bot_username = settings.BOT_USERNAME.lstrip("@")

    logger.info("Bot started.")


async def on_shutdown(bot: Bot) -> None:
    logger.info("Bot shutting down...")
    await bot.session.close()


async def main() -> None:
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(main_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting long polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
