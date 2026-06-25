from aiogram import Router

from .start import router as start_router
from .language import router as language_router
from .admin import router as admin_router
from .admin_texts import router as admin_texts_router
from .admin_settings import router as admin_settings_router
from .upload import router as upload_router
from .myfiles import router as myfiles_router
from .settings_handler import router as settings_router
from .support_handler import router as support_router
from .menu import router as menu_router

main_router = Router()
main_router.include_router(start_router)
main_router.include_router(language_router)
main_router.include_router(admin_router)
main_router.include_router(admin_texts_router)
main_router.include_router(admin_settings_router)
main_router.include_router(upload_router)
main_router.include_router(myfiles_router)
main_router.include_router(settings_router)
main_router.include_router(support_router)
main_router.include_router(menu_router)

__all__ = ["main_router"]
