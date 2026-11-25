from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

CANCEL = "❌ Отмена"
START_TOUR = "🏖 Подобрать тур"
CONTINUE = "🏖 Продолжить"
NEW_APPLICATION = "🆕 Новая заявка"


def reply(rows: list[list[KeyboardButton | str]], *, resize: bool = True) -> ReplyKeyboardMarkup:
    normalized = [
        [item if isinstance(item, KeyboardButton) else KeyboardButton(text=item) for item in row]
        for row in rows
    ]
    return ReplyKeyboardMarkup(keyboard=normalized, resize_keyboard=resize, is_persistent=True)


def start_keyboard() -> ReplyKeyboardMarkup:
    return reply([[START_TOUR]])


def resume_or_new_keyboard() -> ReplyKeyboardMarkup:
    return reply([[CONTINUE], [NEW_APPLICATION]])


def consent_keyboard() -> ReplyKeyboardMarkup:
    return reply([["✅ Согласен, начать"], ["❌ Не согласен"]])


def destination_keyboard() -> ReplyKeyboardMarkup:
    return reply([
        ["🇹🇷 Турция", "🇪🇬 Египет"],
        ["🇦🇪 ОАЭ", "🇹🇭 Таиланд"],
        ["🇻🇳 Вьетнам", "🇷🇺 Россия"],
        ["✏️ Другое"],
        [CANCEL],
    ])


def vacation_keyboard() -> ReplyKeyboardMarkup:
    return reply([
        ["🏖 Пляж", "🏛 Экскурсии"],
        ["⛷ Горы", "Всё равно"],
        [CANCEL],
    ])


def tourists_keyboard() -> ReplyKeyboardMarkup:
    return reply([
        ["1 взрослый", "2 взрослых"],
        ["2 + 1 ребёнок", "2 + 2 детей"],
        ["✏️ Другое"],
        [CANCEL],
    ])


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return reply([[CANCEL]])


def phone_keyboard() -> ReplyKeyboardMarkup:
    return reply([
        [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)],
        ["Ввести номер вручную"],
        [CANCEL],
    ])


def confirm_keyboard() -> ReplyKeyboardMarkup:
    return reply([
        ["✅ Отправить заявку"],
        ["✏️ Изменить ответы"],
        [CANCEL],
    ])


def edit_keyboard() -> ReplyKeyboardMarkup:
    return reply([
        ["🌍 Страна", "🏝 Тип отдыха"],
        ["📅 Даты", "👥 Туристы"],
        ["💰 Бюджет", "👤 Имя"],
        ["📱 Телефон"],
        ["⬅️ Назад к заявке"],
        [CANCEL],
    ])


def manager_contact_keyboard(manager_username: str) -> InlineKeyboardMarkup:
    """Inline button that opens the manager's personal Telegram chat."""
    username = manager_username.strip().lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"https://t.me/{username}")]
    ])


def reminder_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=CONTINUE, callback_data="resume_application")]
    ])


def remove_keyboard():
    from aiogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()
