from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import User


def main_menu_keyboard(
    btn: dict[str, str],
    user: User,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=btn["btn_save_file"])],
        [
            KeyboardButton(text=btn["btn_my_files"]),
            KeyboardButton(text=btn["btn_profile"]),
        ],
        [
            KeyboardButton(text=btn["btn_settings"]),
            KeyboardButton(text=btn["btn_change_language"]),
        ],
        [KeyboardButton(text=btn["btn_support"])],
    ]
    if user.is_admin:
        rows.append([KeyboardButton(text=btn["btn_admin_panel"])])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def language_selection_keyboard(btn: dict[str, str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=btn["btn_lang_fa"], callback_data="lang:fa")
    builder.button(text=btn["btn_lang_en"], callback_data="lang:en")
    builder.adjust(2)
    return builder.as_markup()


def admin_panel_keyboard(btn: dict[str, str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=btn["admin_btn_stats"], callback_data="admin:stats")
    builder.button(text=btn["admin_btn_manage_texts"], callback_data="admin:texts")
    builder.button(text=btn["admin_btn_settings"], callback_data="admin:settings")
    builder.button(text=btn["admin_btn_files"], callback_data="admin:files")
    builder.button(text=btn["admin_btn_back"], callback_data="admin:back")
    builder.adjust(1)
    return builder.as_markup()
