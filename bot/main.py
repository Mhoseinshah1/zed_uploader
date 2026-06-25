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


async def on_startup(bot: Bot, dispatcher: Dispatcher) -> None:
    logger.info("Running database initialization...")
    await init_db()

    logger.info("Seeding default bot texts...")
    async with async_session_factory() as session:
        await seed_default_texts(session)

    # Resolve bot username once and store in dispatcher workflow_data.
    # Handlers receive it as an injected `bot_username: str` parameter.
    if settings.BOT_USERNAME:
        bot_username = settings.BOT_USERNAME.lstrip("@")
    else:
        me = await bot.get_me()
        bot_username = me.username or ""
        logger.info("Resolved bot username via get_me(): @%s", bot_username)

    dispatcher["bot_username"] = bot_username
    logger.info("Bot started. Username: @%s", bot_username)


async def main() -> None:
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(main_router)

    dp.startup.register(on_startup)

    logger.info("Starting long polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
