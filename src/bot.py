import os
from datetime import datetime, UTC, timedelta
import tempfile
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    MenuButtonCommands,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from .models import CalendarEvent, EventAttachment
from .calendar_service import GoogleCalendarService
from .openai_service import OpenAIService
from .logger_config import setup_logger, archive_old_logs
from typing import Dict, List, Optional, Tuple, Any

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logger = setup_logger("__main__")

# Получение токена бота из переменных окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError(
        "Не найден токен Telegram бота. Убедитесь, что переменная TELEGRAM_BOT_TOKEN установлена."
    )

# Инициализация сервисов
calendar_service = GoogleCalendarService()
openai_service = OpenAIService()

# Словарь для хранения временных данных пользователей
user_data = {}

# Список команд для меню бота
BOT_COMMANDS = [
    BotCommand("start", "Начать работу с ботом"),
    BotCommand("help", "Показать справку"),
    BotCommand("events", "Показать ближайшие события"),
    BotCommand("summary", "Создать сводку событий за день"),
    BotCommand("create", "Создать новое событие"),
    BotCommand("settings", "Настройки бота"),
]

# Состояния для ConversationHandler
(
    CHOOSING_ACTION,
    ENTERING_SUMMARY,
    ENTERING_DATE,
    ENTERING_TIME,
    ENTERING_LOCATION,
    ENTERING_DESCRIPTION,
    CHOOSING_RECURRENCE,
    ENTERING_RECURRENCE_INTERVAL,
    ENTERING_RECURRENCE_DAYS,
    ENTERING_RECURRENCE_UNTIL,
    ENTERING_RECURRENCE_COUNT,
    CONFIRMING_EVENT,
) = range(12)

# Форматы для ввода даты и времени
DATE_FORMAT = "%d.%m.%Y"
TIME_FORMAT = "%H:%M"

# Словарь для перевода дней недели
DAYS_TRANSLATION = {
    "понедельник": "MO",
    "вторник": "TU",
    "среда": "WE",
    "четверг": "TH",
    "пятница": "FR",
    "суббота": "SA",
    "воскресенье": "SU",
    "пн": "MO",
    "вт": "TU",
    "ср": "WE",
    "чт": "TH",
    "пт": "FR",
    "сб": "SA",
    "вс": "SU",
}

# Словарь для перевода частоты повторения
FREQUENCY_TRANSLATION = {
    "ежедневно": "DAILY",
    "еженедельно": "WEEKLY",
    "ежемесячно": "MONTHLY",
    "ежегодно": "YEARLY",
}


async def setup_commands(application: Application) -> None:
    """Настраивает команды бота и меню"""
    await application.bot.set_my_commands(BOT_COMMANDS)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Команды бота настроены")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я бот для создания событий в Google Calendar. "
        "Отправьте мне текст, аудио или файл, и я добавлю его в ваш календарь. "
        "Я использую OpenAI для извлечения информации о событиях из ваших сообщений.\n\n"
        "Используйте меню команд для навигации или отправьте /help для получения справки."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = (
        "Я могу помочь вам создавать события в Google Calendar.\n\n"
        "Вот что я умею:\n"
        "- Отправьте мне текст с описанием события, и я извлеку из него информацию\n"
        "- Прикрепите файлы к событию\n"
        "- Отправьте аудиосообщение, и я преобразую его в текст и создам событие\n"
        "- Запросите сводку событий за день\n\n"
        "Команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/events - Показать ближайшие события\n"
        "/summary - Создать сводку событий за день\n"
        "/create - Создать новое событие\n"
        "/settings - Настройки бота"
    )
    await update.message.reply_text(help_text)


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /create - интерактивное создание события"""
    keyboard = [
        [InlineKeyboardButton("Обычное событие", callback_data="create_regular")],
        [
            InlineKeyboardButton(
                "Повторяющееся событие", callback_data="create_recurring"
            )
        ],
        [InlineKeyboardButton("Отмена", callback_data="cancel_creation")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Выберите тип события, которое хотите создать:", reply_markup=reply_markup
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /settings - настройки бота"""
    keyboard = [
        [InlineKeyboardButton("Часовой пояс", callback_data="settings_timezone")],
        [InlineKeyboardButton("Язык уведомлений", callback_data="settings_language")],
        [InlineKeyboardButton("Назад", callback_data="cancel_settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Настройки бота:\n\nЗдесь вы можете настроить параметры бота.",
        reply_markup=reply_markup,
    )


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /events - показывает ближайшие события"""
    events = calendar_service.get_events(max_results=5)

    if not events:
        await update.message.reply_text("Ближайших событий не найдено.")
        return

    message = "Ваши ближайшие события:\n\n"
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        try:
            # Пробуем разные форматы даты
            if "Z" in start:
                start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
            else:
                start_time = datetime.fromisoformat(start)
        except ValueError:
            # Если не удалось распарсить, используем строку как есть
            formatted_time = start
        else:
            formatted_time = start_time.strftime("%d.%m.%Y %H:%M")

        message += f"📅 {formatted_time} - {event['summary']}\n"

    await update.message.reply_text(message)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /summary - создает сводку событий за день"""
    # Получаем события за сегодня
    now = datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Здесь нужно реализовать получение событий за конкретный день
    # Пока используем просто ближайшие события
    events = calendar_service.get_events(max_results=10)

    if not events:
        await update.message.reply_text("Событий для создания сводки не найдено.")
        return

    # Генерируем сводку с помощью OpenAI
    summary = openai_service.generate_daily_summary(events)

    await update.message.reply_text(f"Сводка событий:\n\n{summary}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text

    # Проверяем, находится ли пользователь в процессе создания события
    if user_id in user_data and "creation_step" in user_data[user_id]:
        await handle_creation_step(update, context, user_id, text)
        return

    # Стандартная обработка текстовых сообщений
    processing_message = await update.message.reply_text(
        "Обрабатываю ваше сообщение и извлекаю информацию о событиях..."
    )

    # Извлекаем информацию о событиях с помощью OpenAI
    calendar_events = openai_service.extract_event_info(text)

    if not calendar_events:
        await processing_message.edit_text(
            "Не удалось извлечь информацию о событиях. Пожалуйста, попробуйте еще раз."
        )
        return

    # Сохраняем события во временных данных пользователя
    if len(calendar_events) == 1:
        user_data[user_id] = {"event": calendar_events[0]}
    else:
        user_data[user_id] = {"events": calendar_events}

    # Удаляем сообщение о обработке
    await processing_message.delete()

    if len(calendar_events) == 1:
        # Если найдено только одно событие, показываем стандартный диалог подтверждения
        event = calendar_events[0]
        keyboard = [
            [
                InlineKeyboardButton("Да", callback_data="confirm_event"),
                InlineKeyboardButton("Отмена", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        event_details = format_event_details(event)
        await update.message.reply_text(
            f"Создать событие в календаре?\n\n{event_details}",
            reply_markup=reply_markup,
        )
    else:
        # Если найдено несколько событий, показываем их список и спрашиваем, какие создать
        message = f"Найдено {len(calendar_events)} событий:\n\n"

        for i, event in enumerate(calendar_events, 1):
            message += f"{i}. {format_event_details(event)}\n\n"

        message += "Выберите действие:"

        # Добавляем кнопки для выбора конкретного события
        keyboard = []
        for i, event in enumerate(calendar_events, 1):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"Создать событие {i}", callback_data=f"create_event_{i - 1}"
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "Создать все события", callback_data="confirm_all_events"
                ),
                InlineKeyboardButton("Отмена", callback_data="cancel_event"),
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup)


async def handle_creation_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str
) -> None:
    """Обрабатывает шаги интерактивного создания события"""
    step = user_data[user_id]["creation_step"]
    is_recurring = user_data[user_id].get("is_recurring", False)

    if step == "title":
        # Сохраняем название события
        user_data[user_id]["title"] = text
        user_data[user_id]["creation_step"] = "date"

        await update.message.reply_text(
            "Введите дату и время начала события (например, 25.03.2025 15:30):"
        )

    elif step == "date":
        try:
            # Пытаемся распарсить дату
            date_formats = [
                "%d.%m.%Y %H:%M",
                "%d.%m.%Y",
                "%d/%m/%Y %H:%M",
                "%d/%m/%Y",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
            ]

            start_time = None
            for date_format in date_formats:
                try:
                    if " " in date_format and " " in text:
                        start_time = datetime.strptime(text, date_format)
                    elif " " not in date_format and " " not in text:
                        # Если формат без времени, устанавливаем время на 9:00
                        start_time = datetime.strptime(text, date_format).replace(
                            hour=9, minute=0
                        )

                    if start_time:
                        break
                except ValueError:
                    continue

            if not start_time:
                raise ValueError("Не удалось распарсить дату")

            # Добавляем часовой пояс
            start_time = start_time.replace(tzinfo=UTC)

            # Сохраняем дату начала
            user_data[user_id]["start_time"] = start_time
            user_data[user_id]["creation_step"] = "duration"

            await update.message.reply_text(
                "Введите продолжительность события в часах (например, 1.5):"
            )

        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ ЧЧ:ММ:"
            )

    elif step == "duration":
        try:
            # Пытаемся распарсить продолжительность
            duration = float(text.replace(",", "."))

            # Вычисляем время окончания
            start_time = user_data[user_id]["start_time"]
            hours = int(duration)
            minutes = int((duration - hours) * 60)
            end_time = start_time + timedelta(hours=hours, minutes=minutes)

            # Сохраняем время окончания
            user_data[user_id]["end_time"] = end_time
            user_data[user_id]["creation_step"] = "location"

            await update.message.reply_text(
                "Введите место проведения события (или '-' если его нет):"
            )

        except ValueError:
            await update.message.reply_text(
                "Неверный формат продолжительности. Пожалуйста, введите число (например, 1.5):"
            )

    elif step == "location":
        # Сохраняем место проведения
        if text != "-":
            user_data[user_id]["location"] = text

        # Если событие повторяющееся, запрашиваем информацию о повторении
        if is_recurring:
            user_data[user_id]["creation_step"] = "recurrence_frequency"

            keyboard = [
                [InlineKeyboardButton("Ежедневно", callback_data="recurrence_daily")],
                [
                    InlineKeyboardButton(
                        "Еженедельно", callback_data="recurrence_weekly"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ежемесячно", callback_data="recurrence_monthly"
                    )
                ],
                [InlineKeyboardButton("Ежегодно", callback_data="recurrence_yearly")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Выберите частоту повторения:", reply_markup=reply_markup
            )
        else:
            user_data[user_id]["creation_step"] = "description"
            await update.message.reply_text(
                "Введите описание события (или '-' если его нет):"
            )

    elif step == "recurrence_interval":
        try:
            # Пытаемся распарсить интервал
            interval = int(text)

            if interval < 1:
                raise ValueError("Интервал должен быть положительным числом")

            # Сохраняем интервал
            user_data[user_id]["recurrence"]["interval"] = interval

            # Запрашиваем количество повторений или дату окончания
            user_data[user_id]["creation_step"] = "recurrence_end"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "Без ограничения", callback_data="recurrence_no_end"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Указать количество", callback_data="recurrence_count"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Указать дату окончания", callback_data="recurrence_until"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Выберите, когда должны закончиться повторения:",
                reply_markup=reply_markup,
            )

        except ValueError:
            await update.message.reply_text(
                "Неверный формат интервала. Пожалуйста, введите целое положительное число:"
            )

    elif step == "recurrence_count":
        try:
            # Пытаемся распарсить количество повторений
            count = int(text)

            if count < 1:
                raise ValueError(
                    "Количество повторений должно быть положительным числом"
                )

            # Сохраняем количество повторений
            user_data[user_id]["recurrence"]["count"] = count

            # Переходим к описанию
            user_data[user_id]["creation_step"] = "description"
            await update.message.reply_text(
                "Введите описание события (или '-' если его нет):"
            )

        except ValueError:
            await update.message.reply_text(
                "Неверный формат количества повторений. Пожалуйста, введите целое положительное число:"
            )

    elif step == "recurrence_until":
        try:
            # Пытаемся распарсить дату окончания
            date_formats = ["%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"]

            until_date = None
            for date_format in date_formats:
                try:
                    until_date = datetime.strptime(text, date_format)
                    if until_date:
                        break
                except ValueError:
                    continue

            if not until_date:
                raise ValueError("Не удалось распарсить дату")

            # Устанавливаем время на конец дня и добавляем часовой пояс
            until_date = until_date.replace(hour=23, minute=59, second=59, tzinfo=UTC)

            # Проверяем, что дата окончания позже даты начала
            if until_date <= user_data[user_id]["start_time"]:
                await update.message.reply_text(
                    "Дата окончания должна быть позже даты начала. Пожалуйста, введите корректную дату:"
                )
                return

            # Сохраняем дату окончания
            user_data[user_id]["recurrence"]["until"] = until_date

            # Переходим к описанию
            user_data[user_id]["creation_step"] = "description"
            await update.message.reply_text(
                "Введите описание события (или '-' если его нет):"
            )

        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:"
            )

    elif step == "description":
        # Сохраняем описание
        if text != "-":
            user_data[user_id]["description"] = text

        # Создаем событие
        from .models import CalendarEvent, RecurrenceInfo

        # Получаем данные события
        title = user_data[user_id]["title"]
        start_time = user_data[user_id]["start_time"]
        end_time = user_data[user_id].get("end_time")
        location = user_data[user_id].get("location")
        description = user_data[user_id].get("description")

        # Создаем объект RecurrenceInfo, если это повторяющееся событие
        recurrence = None
        if is_recurring and "recurrence" in user_data[user_id]:
            recurrence_data = user_data[user_id]["recurrence"]
            recurrence = RecurrenceInfo(
                frequency=recurrence_data.get("frequency", "WEEKLY"),
                interval=recurrence_data.get("interval", 1),
                days=recurrence_data.get("days"),
                until=recurrence_data.get("until"),
                count=recurrence_data.get("count"),
            )

        # Создаем объект CalendarEvent
        event = CalendarEvent(
            summary=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            location=location,
            recurrence=recurrence,
        )

        # Сохраняем событие во временных данных пользователя
        user_data[user_id] = {"event": event}

        # Показываем предпросмотр события
        keyboard = [
            [
                InlineKeyboardButton("Да", callback_data="confirm_event"),
                InlineKeyboardButton("Отмена", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        event_details = format_event_details(event)
        await update.message.reply_text(
            f"Создать следующее событие?\n\n{event_details}", reply_markup=reply_markup
        )


def format_event_details(event: CalendarEvent) -> str:
    """Форматирует детали события для отображения"""
    details = f"Заголовок: {event.summary}\n"

    # Преобразуем строковые даты в объекты datetime для форматирования
    try:
        start_datetime = datetime.fromisoformat(event.start_time)
        details += f"Время начала: {start_datetime.strftime('%d.%m.%Y %H:%M')}\n"
    except (ValueError, TypeError):
        details += f"Время начала: {event.start_time}\n"

    if event.end_time:
        try:
            end_datetime = datetime.fromisoformat(event.end_time)
            details += f"Время окончания: {end_datetime.strftime('%d.%m.%Y %H:%M')}\n"
        except (ValueError, TypeError):
            details += f"Время окончания: {event.end_time}\n"

    if event.location:
        details += f"Место: {event.location}\n"

    # Добавляем информацию о повторении
    if event.recurrence:
        details += "\nПовторение: "

        # Словарь для перевода частоты повторения
        frequency_map = {
            "DAILY": "ежедневно",
            "WEEKLY": "еженедельно",
            "MONTHLY": "ежемесячно",
            "YEARLY": "ежегодно",
        }

        # Словарь для перевода дней недели
        days_map = {
            "MO": "понедельник",
            "TU": "вторник",
            "WE": "среда",
            "TH": "четверг",
            "FR": "пятница",
            "SA": "суббота",
            "SU": "воскресенье",
        }

        # Формируем строку с информацией о повторении
        frequency_str = frequency_map.get(
            event.recurrence.frequency, event.recurrence.frequency
        )

        if event.recurrence.interval > 1:
            details += f"каждые {event.recurrence.interval} "
            if event.recurrence.frequency == "DAILY":
                details += "дней"
            elif event.recurrence.frequency == "WEEKLY":
                details += "недель"
            elif event.recurrence.frequency == "MONTHLY":
                details += "месяцев"
            elif event.recurrence.frequency == "YEARLY":
                details += "лет"
        else:
            details += frequency_str

        # Добавляем информацию о днях недели
        if event.recurrence.days:
            days_str = ", ".join(
                [days_map.get(day, day) for day in event.recurrence.days]
            )
            details += f" по {days_str}"

        # Добавляем информацию о дате окончания или количестве повторений
        if event.recurrence.until:
            details += f" до {event.recurrence.until.strftime('%d.%m.%Y')}"
        elif event.recurrence.count:
            details += f", {event.recurrence.count} раз"

        details += "\n"

    if event.description:
        details += f"\nОписание: {event.description}"

    return details


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик аудиосообщений"""
    user_id = update.effective_user.id
    audio = update.message.audio or update.message.voice

    if not audio:
        await update.message.reply_text("Аудиофайл не найден.")
        return

    # Сообщаем пользователю, что обрабатываем его запрос
    processing_message = await update.message.reply_text(
        "Обрабатываю аудиосообщение, преобразую в текст и извлекаю информацию о событии..."
    )

    # Получаем информацию о файле
    file_id = audio.file_id
    file_name = getattr(
        audio,
        "file_name",
        f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg",
    )
    file_type = "audio"

    # Создаем временный файл для сохранения аудио
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".ogg",
        prefix=f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}_",
    ) as temp_file:
        audio_file_path = temp_file.name

    # Скачиваем аудиофайл
    audio_file = await context.bot.get_file(file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
        await audio_file.download_to_drive(temp_file.name)
        temp_file_path = temp_file.name

    # Преобразуем аудио в текст с помощью OpenAI
    transcribed_text = openai_service.transcribe_audio(temp_file_path)

    # Удаляем временный файл
    os.unlink(temp_file_path)

    if not transcribed_text:
        await processing_message.edit_text(
            "Не удалось преобразовать аудио в текст. Пожалуйста, попробуйте еще раз."
        )
        return

    # Извлекаем информацию о событиях из текста
    calendar_events = openai_service.extract_event_info(transcribed_text)

    if not calendar_events:
        await processing_message.edit_text(
            "Не удалось извлечь информацию о событиях из аудио. Пожалуйста, попробуйте еще раз."
        )
        return

    # Добавляем вложение к первому событию
    attachment = EventAttachment(
        file_id=file_id, file_name=file_name, file_type=file_type
    )

    # Добавляем транскрипцию к описанию
    for event in calendar_events:
        if event.description:
            event.description = (
                f"{event.description}\n\nТранскрипция: {transcribed_text}"
            )
        else:
            event.description = f"Транскрипция: {transcribed_text}"

        # Добавляем вложение только к первому событию
        if calendar_events.index(event) == 0:
            # Инициализируем attachments как пустой список, если он None
            if event.attachments is None:
                event.attachments = []
            event.attachments.append(attachment)

    # Сохраняем события во временных данных пользователя
    if len(calendar_events) == 1:
        user_data[user_id] = {"event": calendar_events[0]}
    else:
        user_data[user_id] = {"events": calendar_events}

    # Удаляем сообщение о обработке
    await processing_message.delete()

    # Показываем результаты пользователю
    if len(calendar_events) == 1:
        # Если найдено только одно событие
        event = calendar_events[0]
        keyboard = [
            [
                InlineKeyboardButton("Да", callback_data="confirm_event"),
                InlineKeyboardButton("Отмена", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        event_details = format_event_details(event)
        await update.message.reply_text(
            f"Создать событие из аудиосообщения?\n\n{event_details}",
            reply_markup=reply_markup,
        )
    else:
        # Если найдено несколько событий
        message = f"Найдено {len(calendar_events)} событий в аудиосообщении:\n\n"

        for i, event in enumerate(calendar_events, 1):
            message += f"{i}. {format_event_details(event)}\n\n"

        message += "Выберите действие:"
        keyboard = [
            [
                InlineKeyboardButton(
                    "Создать все события", callback_data="confirm_all_events"
                ),
                InlineKeyboardButton("Отмена", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик документов/файлов"""
    user_id = update.effective_user.id
    document = update.message.document

    if not document:
        await update.message.reply_text("Файл не найден.")
        return

    # Получаем информацию о файле
    file_id = document.file_id
    file_name = document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_type = document.mime_type or "document"

    # Создаем вложение
    attachment = EventAttachment(
        file_id=file_id, file_name=file_name, file_type=file_type
    )

    # Создаем базовое событие
    now = datetime.now(UTC)
    event = CalendarEvent(
        summary=f"Файл: {file_name}",
        description=f"Файл отправлен {now.strftime('%d.%m.%Y %H:%M')}",
        start_time=now,
        end_time=now.replace(hour=now.hour + 1),
        attachments=[attachment],
    )

    # Сохраняем событие во временных данных пользователя
    user_data[user_id] = {"event": event}

    # Спрашиваем, хочет ли пользователь добавить событие в календарь
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data="confirm_event"),
            InlineKeyboardButton("Отмена", callback_data="cancel_event"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Создать событие с файлом в календаре?\n\n"
        f"Заголовок: {event.summary}\n"
        f"Время: {format_datetime(event.start_time)}\n"
        f"Файл: {file_name}",
        reply_markup=reply_markup,
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    callback_data = query.data

    # Обработка создания событий
    if callback_data == "confirm_event":
        # Получаем событие из временных данных пользователя
        if user_id not in user_data or "event" not in user_data[user_id]:
            await query.edit_message_text("Ошибка: данные события не найдены.")
            return

        event = user_data[user_id]["event"]
        created_event = calendar_service.create_event(event)

        if created_event:
            await query.edit_message_text(
                f"Событие успешно создано в календаре!\n\n"
                f"Заголовок: {event.summary}\n"
                f"Время: {format_datetime(event.start_time)}\n"
                f"Ссылка: {created_event.get('htmlLink', 'Недоступна')}"
            )
        else:
            await query.edit_message_text(
                "Произошла ошибка при создании события. Пожалуйста, попробуйте позже."
            )

    # Обработка выбора конкретного события из списка
    elif callback_data.startswith("create_event_"):
        try:
            # Получаем индекс выбранного события
            event_index = int(callback_data.split("_")[-1])

            # Получаем список событий из временных данных пользователя
            if user_id not in user_data or "events" not in user_data[user_id]:
                await query.edit_message_text("Ошибка: данные событий не найдены.")
                return

            events = user_data[user_id]["events"]

            # Проверяем, что индекс в пределах списка
            if event_index < 0 or event_index >= len(events):
                await query.edit_message_text("Ошибка: выбранное событие не найдено.")
                return

            # Сохраняем выбранное событие
            event = events[event_index]
            user_data[user_id]["event"] = event

            # Создаем событие в календаре
            created_event = calendar_service.create_event(event)

            if created_event:
                await query.edit_message_text(
                    f"Событие успешно создано в календаре!\n\n"
                    f"Заголовок: {event.summary}\n"
                    f"Время: {format_datetime(event.start_time)}\n"
                    f"Ссылка: {created_event.get('htmlLink', 'Недоступна')}"
                )
            else:
                await query.edit_message_text(
                    "Произошла ошибка при создании события. Пожалуйста, попробуйте позже."
                )
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке выбора события: {e}")
            await query.edit_message_text(
                "Произошла ошибка при обработке выбора события."
            )

    elif callback_data == "confirm_all_events":
        # Получаем события из временных данных пользователя
        if user_id not in user_data or "events" not in user_data[user_id]:
            await query.edit_message_text("Ошибка: данные событий не найдены.")
            return

        events = user_data[user_id]["events"]
        created_events = []
        failed_events = []

        # Создаем все события
        for event in events:
            created_event = calendar_service.create_event(event)
            if created_event:
                created_events.append((event, created_event))
            else:
                failed_events.append(event)

        # Формируем отчет о создании событий
        message = f"Создано событий: {len(created_events)} из {len(events)}\n\n"

        if created_events:
            message += "Успешно созданные события:\n"
            for event, created in created_events:
                message += f"✅ {event.summary} - {created.get('htmlLink', 'Ссылка недоступна')}\n"

        if failed_events:
            message += "\nНе удалось создать следующие события:\n"
            for event in failed_events:
                message += f"❌ {event.summary}\n"

        await query.edit_message_text(message)

    # Обработка команды создания события
    elif callback_data == "create_regular":
        # Запрашиваем название события
        user_data[user_id] = {"creation_step": "title"}
        await query.edit_message_text("Введите название события:")

    elif callback_data == "create_recurring":
        # Запрашиваем название повторяющегося события
        user_data[user_id] = {"creation_step": "title", "is_recurring": True}
        await query.edit_message_text("Введите название повторяющегося события:")

    # Обработка настроек повторяющихся событий
    elif callback_data == "recurrence_no_end":
        # Без ограничения по времени
        user_data[user_id]["creation_step"] = "description"
        await query.edit_message_text(
            "Введите описание события (или '-' если его нет):"
        )

    elif callback_data == "recurrence_count":
        # Запрашиваем количество повторений
        user_data[user_id]["creation_step"] = "recurrence_count"
        await query.edit_message_text("Введите количество повторений:")

    elif callback_data == "recurrence_until":
        # Запрашиваем дату окончания
        user_data[user_id]["creation_step"] = "recurrence_until"
        await query.edit_message_text(
            "Введите дату окончания повторений (например, 31.12.2025):"
        )

    # Обработка настроек
    elif callback_data == "settings_timezone":
        await query.edit_message_text(
            "Функция настройки часового пояса будет доступна в следующих версиях."
        )

    elif callback_data == "settings_language":
        await query.edit_message_text(
            "Функция настройки языка будет доступна в следующих версиях."
        )

    # Обработка отмены
    elif callback_data in ["cancel_event", "cancel_creation", "cancel_settings"]:
        await query.edit_message_text("Действие отменено.")
        if user_id in user_data:
            del user_data[user_id]


def format_datetime(datetime_str: str) -> str:
    """Форматирует строку datetime в удобочитаемый формат"""
    try:
        dt = datetime.fromisoformat(datetime_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return datetime_str


def main() -> None:
    """Запускает бота"""
    # Архивируем старые логи
    try:
        archive_old_logs()
        logger.info("Старые логи успешно архивированы")
    except Exception as e:
        logger.error(f"Ошибка при архивировании логов: {e}")

    # Создаем приложение и добавляем обработчики
    application = Application.builder().token(TOKEN).build()

    # Настраиваем команды бота
    application.post_init = setup_commands

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("create", create_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("summary", summary_command))

    # Добавляем обработчики сообщений
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Добавляем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    # Запускаем бота
    application.run_polling()
    logger.info("Бот запущен")


if __name__ == "__main__":
    main()
