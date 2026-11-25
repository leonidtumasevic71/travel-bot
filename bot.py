import asyncio
import logging
import re
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

import database as db
from config import settings
from keyboards import (
    CANCEL, CONTINUE, NEW_APPLICATION, START_TOUR,
    cancel_keyboard, confirm_keyboard, consent_keyboard, destination_keyboard,
    edit_keyboard, manager_contact_keyboard, phone_keyboard, reminder_inline_keyboard, remove_keyboard,
    resume_or_new_keyboard, start_keyboard, tourists_keyboard, vacation_keyboard,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("just_travel_bot")
dp = Dispatcher()

DESTINATIONS = {
    "🇹🇷 Турция", "🇪🇬 Египет", "🇦🇪 ОАЭ", "🇹🇭 Таиланд", "🇻🇳 Вьетнам", "🇷🇺 Россия"
}
VACATION_TYPES = {"🏖 Пляж", "🏛 Экскурсии", "⛷ Горы", "Всё равно"}
TOURISTS_OPTIONS = {"1 взрослый", "2 взрослых", "2 + 1 ребёнок", "2 + 2 детей"}
EDIT_FIELDS = {
    "🌍 Страна": ("destination", "страну"),
    "🏝 Тип отдыха": ("vacation_type", "тип отдыха"),
    "📅 Даты": ("travel_dates", "даты поездки"),
    "👥 Туристы": ("tourists", "количество туристов"),
    "💰 Бюджет": ("budget", "бюджет"),
    "👤 Имя": ("client_name", "имя"),
    "📱 Телефон": ("phone", "номер телефона"),
}


def user_label(message: Message) -> tuple[str | None, str | None]:
    user = message.from_user
    if not user:
        return None, None
    return user.username, user.first_name


def valid_text(value: str, max_length: int = 250) -> str | None:
    value = value.strip()
    if not value or len(value) > max_length:
        return None
    return value


async def send_welcome(message: Message) -> None:
    intro = (
        "<b>Что умеет этот бот?</b>\n"
        "Для начала консультации уточним Ваши пожелания и направим вашу заявку агенту 🤍🌊"
    )
    if settings.welcome_image.is_file():
        await message.answer_photo(FSInputFile(settings.welcome_image), caption=intro)
    else:
        await message.answer(intro)

    await message.answer(
        f"Привет! Я бот агентства <b>{escape(settings.brand_name)}</b> 🌴\n\n"
        "Помогу оформить заявку на тур. Нажмите кнопку, чтобы начать:",
        reply_markup=start_keyboard(),
    )
    if settings.manager_username:
        await message.answer(
            "Есть вопросы? Вы можете написать менеджеру напрямую:",
            reply_markup=manager_contact_keyboard(settings.manager_username),
        )


async def ask_consent(message: Message) -> None:
    policy_text = "политикой конфиденциальности"
    if settings.privacy_policy_url:
        safe_url = escape(settings.privacy_policy_url, quote=True)
        policy_text = f'<a href="{safe_url}">политикой конфиденциальности</a>'
    await message.answer(
        "Прежде чем продолжить: используя бота, вы соглашаетесь на обработку "
        f"персональных данных (имя, телефон и данные заявки) турагентством "
        f"«{escape(settings.brand_name)}» в соответствии с {policy_text}.",
        reply_markup=consent_keyboard(),
    )


async def prompt_step(bot: Bot, chat_id: int, app: dict) -> None:
    step = app["step"]
    prompts = {
        "destination": ("🌍 Куда хотите поехать?", destination_keyboard()),
        "destination_custom": ("Напишите, куда хотите поехать:", cancel_keyboard()),
        "vacation": ("🏝 Какой тип отдыха предпочитаете?", vacation_keyboard()),
        "dates": (
            "📅 Укажите примерные даты поездки:\n"
            "(например: 15–22 июля или с 10 августа на 10 ночей)", cancel_keyboard()
        ),
        "tourists": ("👥 Сколько человек едет?", tourists_keyboard()),
        "tourists_custom": ("Напишите свой вариант (например: 3 взрослых и 1 ребёнок):", cancel_keyboard()),
        "budget": ("💰 Примерный бюджет на человека?\n(Например, 80–100 тысяч на человека)", cancel_keyboard()),
        "name": ("👤 Как к вам обращаться?", cancel_keyboard()),
        "phone": ("📱 Поделитесь номером телефона или введите его вручную:", phone_keyboard()),
        "phone_manual": ("Введите номер телефона в международном формате:", cancel_keyboard()),
    }
    if step in prompts:
        text, markup = prompts[step]
        await bot.send_message(chat_id, text, reply_markup=markup)
    elif step == "confirm":
        await send_confirmation(bot, chat_id, app)
    elif step == "edit_menu":
        await bot.send_message(chat_id, "Что хотите изменить?", reply_markup=edit_keyboard())
    elif step.startswith("edit_"):
        field_key = step.removeprefix("edit_")
        labels = {
            "destination": "страну", "vacation_type": "тип отдыха", "travel_dates": "даты поездки",
            "tourists": "количество туристов", "budget": "бюджет", "client_name": "имя", "phone": "номер телефона",
        }
        await bot.send_message(chat_id, f"Введите новое значение: {labels.get(field_key, 'ответ')}", reply_markup=cancel_keyboard())
    else:
        await bot.send_message(chat_id, "Нажмите «Подобрать тур», чтобы начать.", reply_markup=start_keyboard())


async def send_confirmation(bot: Bot, chat_id: int, app: dict) -> None:
    fields = [
        ("Страна", app.get("destination")),
        ("Тип отдыха", app.get("vacation_type")),
        ("Даты", app.get("travel_dates")),
        ("Туристы", app.get("tourists")),
        ("Бюджет на человека", app.get("budget")),
        ("Имя", app.get("client_name")),
        ("Телефон", app.get("phone")),
    ]
    summary = "\n".join(f"<b>{label}:</b> {escape(str(value or '—'))}" for label, value in fields)
    await bot.send_message(
        chat_id,
        "🧾 <b>Проверьте вашу заявку</b>\n\n" + summary + "\n\nВсё верно? Отправьте заявку менеджеру.",
        reply_markup=confirm_keyboard(),
    )


async def ask_destination(bot: Bot, chat_id: int) -> None:
    db.update_application(chat_id, step="destination")
    await bot.send_message(chat_id, "🌍 Куда хотите поехать?", reply_markup=destination_keyboard())


async def show_current_step(message: Message) -> None:
    app = db.get_application(message.from_user.id)
    if app:
        await prompt_step(message.bot, message.chat.id, app)


async def start_new_application(message: Message) -> None:
    username, first_name = user_label(message)
    db.create_or_reset_application(message.from_user.id, username, first_name, reset=True)
    db.update_application(message.from_user.id, step="consent")
    await ask_consent(message)


@dp.message(CommandStart())
async def command_start(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Пожалуйста, откройте бота в личном чате.")
        return
    username, first_name = user_label(message)
    db.create_or_reset_application(message.from_user.id, username, first_name)
    app = db.get_application(message.from_user.id)
    if app and app["status"] == "draft" and app["step"] not in {"new", "consent"}:
        await send_welcome(message)
        await message.answer(
            "👋 У вас есть незавершённая заявка. Хотите продолжить заполнение или начать заново?",
            reply_markup=resume_or_new_keyboard(),
        )
        return
    await send_welcome(message)


@dp.message(Command("id"))
async def command_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram chat_id: <code>{message.chat.id}</code>")


@dp.message(Command("help"))
async def command_help(message: Message) -> None:
    await message.answer(
        "Я помогу оформить заявку на подбор тура.\n"
        "/start — открыть бота\n/cancel — отменить заполнение\n/id — узнать chat_id"
    )


@dp.message(Command("cancel"))
async def command_cancel(message: Message) -> None:
    db.cancel_application(message.from_user.id)
    await message.answer(
        "Заявка отменена. Чтобы заполнить новую, нажмите кнопку ниже.",
        reply_markup=start_keyboard(),
    )


@dp.callback_query(F.data == "resume_application")
async def callback_resume(callback: CallbackQuery) -> None:
    app = db.get_application(callback.from_user.id)
    await callback.answer()
    if not app or app["status"] != "draft":
        await callback.message.answer("Незавершённая заявка не найдена. Нажмите /start.")
        return
    await callback.message.answer("Продолжаем заполнение вашей заявки 🌴")
    db.update_application(callback.from_user.id, reminder_sent=0)
    await prompt_step(callback.bot, callback.message.chat.id, db.get_application(callback.from_user.id))


@dp.message(F.contact)
async def contact_received(message: Message) -> None:
    app = db.get_application(message.from_user.id)
    if not app or app["step"] != "phone":
        await message.answer("Чтобы отправить номер телефона, сначала начните оформление заявки: /start")
        return
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, отправьте свой номер телефона с помощью кнопки ниже.", reply_markup=phone_keyboard())
        return
    db.update_application(message.from_user.id, phone=contact.phone_number, step="confirm")
    await send_confirmation(message.bot, message.chat.id, db.get_application(message.from_user.id))


@dp.message(F.text)
async def handle_text(message: Message) -> None:
    if message.chat.type != "private":
        return
    text = message.text.strip()
    user_id = message.from_user.id
    username, first_name = user_label(message)
    db.create_or_reset_application(user_id, username, first_name)
    app = db.get_application(user_id)
    step = app["step"]

    if text == CANCEL:
        db.cancel_application(user_id)
        await message.answer("Заявка отменена. Чтобы начать заново, нажмите кнопку ниже.", reply_markup=start_keyboard())
        return

    if text == START_TOUR:
        if app["status"] == "draft" and step not in {"new", "consent"}:
            await message.answer("У вас уже есть незавершённая заявка. Продолжить её или начать заново?", reply_markup=resume_or_new_keyboard())
            return
        db.update_application(user_id, step="consent", status="draft")
        await ask_consent(message)
        return

    if text == CONTINUE:
        if app["status"] == "draft":
            await message.answer("Продолжаем заполнение 🌴")
            db.update_application(user_id, reminder_sent=0)
            await show_current_step(message)
        else:
            await message.answer("Активная заявка не найдена. Начните новую.", reply_markup=start_keyboard())
        return

    if text == NEW_APPLICATION:
        await start_new_application(message)
        return

    if text == "✅ Согласен, начать":
        if step != "consent":
            await message.answer("Сначала нажмите «Подобрать тур».", reply_markup=start_keyboard())
            return
        db.update_application(user_id, consent=1, step="destination")
        await message.answer("✅ Спасибо! Начинаем подбор тура.")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if text == "❌ Не согласен":
        db.cancel_application(user_id)
        await message.answer("Без согласия на обработку данных оформить заявку не получится. Вы можете вернуться позже.", reply_markup=start_keyboard())
        return

    if text == "✏️ Изменить ответы":
        if step != "confirm":
            await message.answer("Сейчас нечего редактировать.")
            return
        db.update_application(user_id, step="edit_menu")
        await message.answer("Что хотите изменить?", reply_markup=edit_keyboard())
        return

    if text == "⬅️ Назад к заявке":
        db.update_application(user_id, step="confirm")
        await send_confirmation(message.bot, message.chat.id, db.get_application(user_id))
        return

    if text in EDIT_FIELDS:
        if step != "edit_menu":
            await message.answer("Чтобы изменить ответы, сначала откройте редактирование заявки.")
            return
        field_key, label = EDIT_FIELDS[text]
        db.update_application(user_id, step=f"edit_{field_key}")
        await message.answer(f"Введите новое значение: {label}.", reply_markup=cancel_keyboard())
        return

    if text == "✅ Отправить заявку":
        if step != "confirm":
            await message.answer("Сначала заполните анкету до конца.")
            return
        await submit_application(message)
        return

    if step in {"new", "cancelled", "submitted"}:
        await message.answer("Нажмите «🏖 Подобрать тур», чтобы начать.", reply_markup=start_keyboard())
        return

    value = valid_text(text)
    if not value:
        await message.answer("Пожалуйста, введите ответ длиной не более 250 символов.")
        return

    # During editing, any text updates the selected field and returns to the summary.
    if step.startswith("edit_"):
        field_key = step.removeprefix("edit_")
        allowed = {"destination", "vacation_type", "travel_dates", "tourists", "budget", "client_name", "phone"}
        if field_key not in allowed:
            await message.answer("Не удалось определить поле. Вернитесь к заявке.", reply_markup=edit_keyboard())
            return
        if field_key == "phone" and len(re.sub(r"\D", "", value)) < 7:
            await message.answer("Проверьте номер телефона и попробуйте ещё раз.", reply_markup=cancel_keyboard())
            return
        db.update_application(user_id, **{field_key: value}, step="confirm")
        await send_confirmation(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "destination":
        if value == "✏️ Другое":
            db.update_application(user_id, step="destination_custom")
            await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        elif value in DESTINATIONS:
            db.update_application(user_id, destination=value, step="vacation")
            await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        else:
            await message.answer("Выберите страну с помощью кнопок или нажмите «Другое».", reply_markup=destination_keyboard())
        return

    if step == "destination_custom":
        db.update_application(user_id, destination=value, step="vacation")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "vacation":
        if value not in VACATION_TYPES:
            await message.answer("Выберите один из предложенных вариантов.", reply_markup=vacation_keyboard())
            return
        db.update_application(user_id, vacation_type=value, step="dates")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "dates":
        db.update_application(user_id, travel_dates=value, step="tourists")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "tourists":
        if value == "✏️ Другое":
            db.update_application(user_id, step="tourists_custom")
            await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        elif value in TOURISTS_OPTIONS:
            db.update_application(user_id, tourists=value, step="budget")
            await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        else:
            await message.answer("Выберите вариант кнопкой или нажмите «Другое».", reply_markup=tourists_keyboard())
        return

    if step == "tourists_custom":
        db.update_application(user_id, tourists=value, step="budget")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "budget":
        db.update_application(user_id, budget=value, step="name")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "name":
        db.update_application(user_id, client_name=value, step="phone")
        await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "phone":
        if value == "Ввести номер вручную":
            db.update_application(user_id, step="phone_manual")
            await prompt_step(message.bot, message.chat.id, db.get_application(user_id))
            return
        await message.answer("Нажмите кнопку отправки контакта или выберите ручной ввод.", reply_markup=phone_keyboard())
        return

    if step == "phone_manual":
        digits = re.sub(r"\D", "", value)
        if len(digits) < 7:
            await message.answer("Номер выглядит слишком коротким. Введите его ещё раз, например +375291234567.", reply_markup=cancel_keyboard())
            return
        db.update_application(user_id, phone=value, step="confirm")
        await send_confirmation(message.bot, message.chat.id, db.get_application(user_id))
        return

    if step == "edit_menu":
        await message.answer("Выберите поле, которое хотите изменить, с помощью кнопок.", reply_markup=edit_keyboard())
        return

    if step == "confirm":
        await message.answer("Проверьте заявку и нажмите «Отправить заявку» или «Изменить ответы».", reply_markup=confirm_keyboard())
        return

    await message.answer("Нажмите /start, чтобы открыть меню.", reply_markup=start_keyboard())


async def submit_application(message: Message) -> None:
    user_id = message.from_user.id
    app = db.get_application(user_id)
    if not app:
        await message.answer("Заявка не найдена. Начните заново командой /start.")
        return
    if app.get("status") == "submitted":
        number = app.get("application_number")
        number_text = f" №{number}" if number is not None else ""
        await message.answer(f"Эта заявка уже отправлена менеджеру{number_text}.")
        return

    # The number is persisted before sending, so a failed delivery retry keeps the same number.
    application_number = db.assign_application_number(user_id)
    username = f"@{app['username']}" if app.get("username") else "не указан"
    manager_text = (
        f"🆕 <b>Заявка №{application_number} на подбор тура</b>\n\n"
        f"<b>Имя:</b> {escape(str(app.get('client_name') or '—'))}\n"
        f"<b>Телефон:</b> {escape(str(app.get('phone') or '—'))}\n"
        f"<b>Telegram:</b> {escape(username)}\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Страна:</b> {escape(str(app.get('destination') or '—'))}\n"
        f"<b>Тип отдыха:</b> {escape(str(app.get('vacation_type') or '—'))}\n"
        f"<b>Даты:</b> {escape(str(app.get('travel_dates') or '—'))}\n"
        f"<b>Туристы:</b> {escape(str(app.get('tourists') or '—'))}\n"
        f"<b>Бюджет на человека:</b> {escape(str(app.get('budget') or '—'))}"
    )

    if not settings.manager_chat_id:
        await message.answer(
            "⚠️ Заявка пока не отправлена: не настроен получатель заявок. "
            "Пожалуйста, попробуйте позже или напишите менеджеру напрямую.",
            reply_markup=manager_contact_keyboard(settings.manager_username) if settings.manager_username else None,
        )
        return

    try:
        manager_chat_id = int(settings.manager_chat_id)
        await message.bot.send_message(manager_chat_id, manager_text)
    except (ValueError, TelegramAPIError) as exc:
        logger.exception("Could not send application to manager: %s", exc)
        await message.answer(
            "Не удалось передать заявку менеджеру. Ваши ответы сохранены — попробуйте отправить ещё раз позже.",
            reply_markup=confirm_keyboard(),
        )
        return

    db.mark_submitted(user_id)
    await message.answer(
        f"✅ <b>Заявка №{application_number} отправлена!</b>\nМенеджер получил ваши пожелания и скоро свяжется с вами 🌴",
        reply_markup=manager_contact_keyboard(settings.manager_username) if settings.manager_username else None,
    )


async def reminder_worker(bot: Bot) -> None:
    """Send one reminder for each draft that has been inactive for the configured period."""
    while True:
        try:
            due = db.get_due_reminders(settings.reminder_after_minutes)
            for app in due:
                user_id = int(app["user_id"])
                # Mark first to avoid duplicate reminders if Telegram returns an error.
                db.mark_reminder_sent(user_id)
                try:
                    await bot.send_message(
                        user_id,
                        "👋 Вы начали подбор тура, но не завершили!\n\n"
                        "Вернитесь и оставьте заявку — менеджер подберёт лучший вариант 🌴",
                        reply_markup=reminder_inline_keyboard(),
                    )
                except TelegramAPIError:
                    logger.info("Reminder could not be delivered to user_id=%s", user_id)
        except Exception:
            logger.exception("Reminder worker error")
        await asyncio.sleep(60)


async def main() -> None:
    if not settings.bot_token or settings.bot_token == "PASTE_NEW_TOKEN_HERE":
        raise RuntimeError("Укажите новый BOT_TOKEN в файле .env. Старый опубликованный токен необходимо отозвать через BotFather.")

    db.init_db()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    reminder_task = asyncio.create_task(reminder_worker(bot))
    logger.info("Starting %s bot", settings.brand_name)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
