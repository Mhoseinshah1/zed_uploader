from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "سلام! 👋\n"
        "به ربات خوش آمدید.\n"
        "این ربات در حال توسعه است."
    )
