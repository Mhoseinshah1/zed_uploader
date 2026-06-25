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


class PasswordStates(StatesGroup):
    waiting_for_password = State()      # viewer entering password to open a file
    waiting_for_new_password = State()  # owner/admin setting a file password


class ForcedJoinStates(StatesGroup):
    waiting_for_invite_link = State()
    waiting_for_chat_id = State()


class AdminFileStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_expiration = State()
    waiting_for_password = State()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_forward = State()


class MyFilesStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_expiration = State()


class AdminUserStates(StatesGroup):
    waiting_for_user_id = State()
