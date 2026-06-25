from aiogram.fsm.state import State, StatesGroup


class UploadStates(StatesGroup):
    waiting_for_file = State()


class SettingsStates(StatesGroup):
    waiting_for_signature = State()
    waiting_for_expiration_custom = State()
    waiting_for_auto_delete_custom = State()


class AdminTextStates(StatesGroup):
    choosing_lang = State()
    choosing_key = State()
    entering_value = State()


class AdminSettingsStates(StatesGroup):
    entering_value = State()
