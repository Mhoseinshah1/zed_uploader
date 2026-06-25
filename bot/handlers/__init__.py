from aiogram import Router

from .start import router as start_router

main_router = Router()
main_router.include_router(start_router)

__all__ = ["main_router"]
