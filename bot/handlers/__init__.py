from aiogram import Router

from .start import router as start_router
from .language import router as language_router
from .admin import router as admin_router
from .menu import router as menu_router

main_router = Router()
main_router.include_router(start_router)
main_router.include_router(language_router)
main_router.include_router(admin_router)
main_router.include_router(menu_router)

__all__ = ["main_router"]
