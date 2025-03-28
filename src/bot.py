import os
from datetime import datetime, UTC
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
from models import CalendarEvent, EventAttachment
from calendar_service import GoogleCalendarService
from openai_service import OpenAIService
from logger_config import setup_logger, archive_old_logs
from typing import Dict, List, Optional, Tuple, Any

# Loading environment variables
load_dotenv()

# Setting up logging
logger = setup_logger("__main__")

# Getting bot token from environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError(
        "Telegram bot token not found. Make sure the TELEGRAM_BOT_TOKEN variable is set."
    )

# Initializing services
calendar_service = GoogleCalendarService()
openai_service = OpenAIService()

# Dictionary for storing temporary user data
user_data = {}

# List of commands for bot menu
BOT_COMMANDS = [
    BotCommand("start", "Start working with the bot"),
    BotCommand("help", "Show help"),
    BotCommand("events", "Show upcoming events"),
    BotCommand("summary", "Create a summary of events for the day"),
    BotCommand("settings", "Bot settings"),
]

# States for ConversationHandler
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

# Formats for date and time input
DATE_FORMAT = "%d.%m.%Y"
TIME_FORMAT = "%H:%M"

# Dictionary for days of week translation
DAYS_TRANSLATION = {
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
    "sunday": "SU",
    "mon": "MO",
    "tue": "TU",
    "wed": "WE",
    "thu": "TH",
    "fri": "FR",
    "sat": "SA",
    "sun": "SU",
}

# Dictionary for recurrence frequency translation
FREQUENCY_TRANSLATION = {
    "daily": "DAILY",
    "weekly": "WEEKLY",
    "monthly": "MONTHLY",
    "yearly": "YEARLY",
}


async def setup_commands(application: Application) -> None:
    """Sets up bot commands and menu"""
    await application.bot.set_my_commands(BOT_COMMANDS)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Bot commands are set up")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command"""
    await update.message.reply_text(
        "Hello! I'm a bot for creating events in Google Calendar. "
        "Send me text, audio, or a file, and I'll add it to your calendar. "
        "I use OpenAI to extract information about events from your messages.\n\n"
        "Use the command menu for navigation or send /help for assistance."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /help command"""
    help_text = (
        "I can help you create events in Google Calendar.\n\n"
        "Here's what I can do:\n"
        "- Send me text with an event description, and I'll extract information from it\n"
        "- Attach files to events\n"
        "- Send a voice message, and I'll convert it to text and create an event\n"
        "- Request a summary of events for the day\n\n"
        "Commands:\n"
        "/start - Start working with the bot\n"
        "/help - Show this message\n"
        "/events - Show upcoming events\n"
        "/summary - Create a summary of events for the day\n"
        "/settings - Bot settings"
    )
    await update.message.reply_text(help_text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /settings command - bot settings"""
    keyboard = [
        [InlineKeyboardButton("Time zone", callback_data="settings_timezone")],
        [
            InlineKeyboardButton(
                "Notification language", callback_data="settings_language"
            )
        ],
        [InlineKeyboardButton("Back", callback_data="cancel_settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Bot settings:\n\nHere you can configure bot parameters.",
        reply_markup=reply_markup,
    )


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /events command - shows upcoming events"""
    events = calendar_service.get_events(max_results=5)

    if not events:
        await update.message.reply_text("No upcoming events found.")
        return

    message = "Your upcoming events:\n\n"
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        try:
            # Try different date formats
            if "Z" in start:
                start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
            else:
                start_time = datetime.fromisoformat(start)
        except ValueError:
            # If parsing fails, use the string as is
            formatted_time = start
        else:
            formatted_time = start_time.strftime("%d.%m.%Y %H:%M")

        message += f"📅 {formatted_time} - {event['summary']}\n"

    await update.message.reply_text(message)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /summary command - creates a summary of events for the day"""
    # Get events for today
    now = datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Here we need to implement getting events for a specific day
    # For now, just use upcoming events
    events = calendar_service.get_events(max_results=10)

    if not events:
        await update.message.reply_text("No events found to create a summary.")
        return

    # Generate summary using OpenAI
    summary = openai_service.generate_daily_summary(events)

    await update.message.reply_text(f"Events summary:\n\n{summary}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for text messages"""
    user_id = update.effective_user.id
    text = update.message.text

    # Standard processing of text messages
    processing_message = await update.message.reply_text(
        "Processing your message and extracting event information..."
    )

    # Extract event information using OpenAI
    calendar_events = openai_service.extract_event_info(text)

    if not calendar_events:
        await processing_message.edit_text(
            "Failed to extract event information. Please try again."
        )
        return

    # Save events in user's temporary data
    if len(calendar_events) == 1:
        user_data[user_id] = {"event": calendar_events[0]}
    else:
        user_data[user_id] = {"events": calendar_events}

    # Delete processing message
    await processing_message.delete()

    if len(calendar_events) == 1:
        # If only one event is found, show standard confirmation dialog
        event = calendar_events[0]
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="confirm_event"),
                InlineKeyboardButton("Cancel", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        event_details = format_event_details(event)
        await update.message.reply_text(
            f"Create an event in the calendar?\n\n{event_details}",
            reply_markup=reply_markup,
        )
    else:
        # If multiple events are found, show a list and ask which ones to create
        message = f"Found {len(calendar_events)} events:\n\n"

        for i, event in enumerate(calendar_events, 1):
            message += f"{i}. {format_event_details(event)}\n\n"

        message += "Choose an action:"

        # Add buttons for selecting specific events
        keyboard = []
        for i, event in enumerate(calendar_events, 1):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"Create event {i}", callback_data=f"create_event_{i - 1}"
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "Create all events", callback_data="confirm_all_events"
                ),
                InlineKeyboardButton("Cancel", callback_data="cancel_event"),
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup)


def format_event_details(event: CalendarEvent) -> str:
    """Formats event details for display"""
    details = f"Title: {event.summary}\n"

    # Convert string dates to datetime objects for formatting
    try:
        start_datetime = datetime.fromisoformat(event.start_time)
        details += f"Start time: {start_datetime.strftime('%d.%m.%Y %H:%M')}\n"
    except (ValueError, TypeError):
        details += f"Start time: {event.start_time}\n"

    if event.end_time:
        try:
            end_datetime = datetime.fromisoformat(event.end_time)
            details += f"End time: {end_datetime.strftime('%d.%m.%Y %H:%M')}\n"
        except (ValueError, TypeError):
            details += f"End time: {event.end_time}\n"

    if event.location:
        details += f"Location: {event.location}\n"

    # Add recurrence information
    if event.recurrence:
        details += "\nRecurrence: "

        # Dictionary for recurrence frequency translation
        frequency_map = {
            "DAILY": "daily",
            "WEEKLY": "weekly",
            "MONTHLY": "monthly",
            "YEARLY": "yearly",
        }

        # Dictionary for days of week translation
        days_map = {
            "MO": "Monday",
            "TU": "Tuesday",
            "WE": "Wednesday",
            "TH": "Thursday",
            "FR": "Friday",
            "SA": "Saturday",
            "SU": "Sunday",
        }

        # Form string with recurrence information
        frequency_str = frequency_map.get(
            event.recurrence.frequency, event.recurrence.frequency
        )

        if event.recurrence.interval > 1:
            details += f"every {event.recurrence.interval} "
            if event.recurrence.frequency == "DAILY":
                details += "days"
            elif event.recurrence.frequency == "WEEKLY":
                details += "weeks"
            elif event.recurrence.frequency == "MONTHLY":
                details += "months"
            elif event.recurrence.frequency == "YEARLY":
                details += "years"
        else:
            details += frequency_str

        # Add information about days of the week
        if event.recurrence.days:
            days_str = ", ".join(
                [days_map.get(day, day) for day in event.recurrence.days]
            )
            details += f" on {days_str}"

        # Add information about end date or number of recurrences
        if hasattr(event.recurrence, "until") and event.recurrence.until:
            try:
                until_date = datetime.fromisoformat(event.recurrence.until)
                details += f" until {until_date.strftime('%d.%m.%Y')}"
            except (ValueError, TypeError):
                details += f" until {event.recurrence.until}"
        elif hasattr(event.recurrence, "count") and event.recurrence.count:
            details += f", {event.recurrence.count} times"

        details += "\n"

    if event.description:
        details += f"\nDescription: {event.description}"

    return details


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for audio messages"""
    user_id = update.effective_user.id
    audio = update.message.audio or update.message.voice

    if not audio:
        await update.message.reply_text("Audio file not found.")
        return

    # Inform the user that we're processing their request
    processing_message = await update.message.reply_text(
        "Processing audio message, converting to text and extracting event information..."
    )

    # Get file information
    file_id = audio.file_id
    file_name = getattr(
        audio,
        "file_name",
        f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg",
    )
    file_type = "audio"

    # Create temporary file for saving audio
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".ogg",
        prefix=f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}_",
    ) as temp_file:
        audio_file_path = temp_file.name

    # Download audio file
    audio_file = await context.bot.get_file(file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
        await audio_file.download_to_drive(temp_file.name)
        temp_file_path = temp_file.name

    # Convert audio to text using OpenAI
    transcribed_text = openai_service.transcribe_audio(temp_file_path)

    # Delete temporary file
    os.unlink(temp_file_path)

    if not transcribed_text:
        await processing_message.edit_text(
            "Failed to convert audio to text. Please try again."
        )
        return

    # Extract event information from text
    calendar_events = openai_service.extract_event_info(transcribed_text)

    if not calendar_events:
        await processing_message.edit_text(
            "Failed to extract event information from audio. Please try again."
        )
        return

    # Add attachment to the first event
    attachment = EventAttachment(
        file_id=file_id, file_name=file_name, file_type=file_type
    )

    # Add transcription to description
    for event in calendar_events:
        if event.description:
            event.description = (
                f"{event.description}\n\nTranscription: {transcribed_text}"
            )
        else:
            event.description = f"Transcription: {transcribed_text}"

        # Add attachment only to the first event
        if calendar_events.index(event) == 0:
            # Initialize attachments as empty list if it's None
            if event.attachments is None:
                event.attachments = []
            event.attachments.append(attachment)

    # Save events in user's temporary data
    if len(calendar_events) == 1:
        user_data[user_id] = {"event": calendar_events[0]}
    else:
        user_data[user_id] = {"events": calendar_events}

    # Delete processing message
    await processing_message.delete()

    # Show results to the user
    if len(calendar_events) == 1:
        # If only one event is found
        event = calendar_events[0]
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="confirm_event"),
                InlineKeyboardButton("Cancel", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        event_details = format_event_details(event)
        await update.message.reply_text(
            f"Create an event from audio message?\n\n{event_details}",
            reply_markup=reply_markup,
        )
    else:
        # If multiple events are found
        message = f"Found {len(calendar_events)} events in audio message:\n\n"

        for i, event in enumerate(calendar_events, 1):
            message += f"{i}. {format_event_details(event)}\n\n"

        message += "Choose an action:"
        keyboard = [
            [
                InlineKeyboardButton(
                    "Create all events", callback_data="confirm_all_events"
                ),
                InlineKeyboardButton("Cancel", callback_data="cancel_event"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for documents/files"""
    user_id = update.effective_user.id
    document = update.message.document
    caption = update.message.caption  # Get caption for the file

    if not document:
        await update.message.reply_text("File not found.")
        return

    # Get file information
    file_id = document.file_id
    file_name = document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_type = document.mime_type or "document"

    # Create attachment
    attachment = EventAttachment(
        file_id=file_id, file_name=file_name, file_type=file_type
    )

    # If there's a caption for the file, use OpenAI to extract event information
    if caption:
        events = openai_service.extract_event_info(caption)
        if events:
            event = events[0]
            # Add attachment to the event
            if event.attachments is None:
                event.attachments = []
            event.attachments.append(attachment)
            # Add file information to description
            file_info = f"\n\nAttached file: {file_name}"
            event.description = (event.description or "") + file_info
        else:
            # If extraction failed, create a basic event
            now = datetime.now(UTC)
            event = CalendarEvent(
                summary=caption,
                description=f"Attached file: {file_name}",
                start_time=now.isoformat(),
                end_time=now.replace(hour=now.hour + 1).isoformat(),
                attachments=[attachment],
            )
    else:
        # If there's no caption, create a basic event
        now = datetime.now(UTC)
        event = CalendarEvent(
            summary=f"File: {file_name}",
            description=f"Attached file: {file_name}",
            start_time=now.isoformat(),
            end_time=now.replace(hour=now.hour + 1).isoformat(),
            attachments=[attachment],
        )

    # Save event in user's temporary data
    user_data[user_id] = {"event": event}

    # Ask if the user wants to add the event to calendar
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data="confirm_event"),
            InlineKeyboardButton("Cancel", callback_data="cancel_event"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Create an event with file in calendar?\n\n"
        f"Title: {event.summary}\n"
        f"Time: from {format_datetime(event.start_time)}"
        f"{' to ' + format_datetime(event.end_time) if event.end_time else ''}\n"
        f"File: {file_name}",
        reply_markup=reply_markup,
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for button clicks"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    callback_data = query.data

    # Event creation processing
    if callback_data == "confirm_event":
        # Get event from user's temporary data
        if user_id not in user_data or "event" not in user_data[user_id]:
            await query.edit_message_text("Error: event data not found.")
            return

        event = user_data[user_id]["event"]
        created_event = calendar_service.create_event(event)

        if created_event:
            await query.edit_message_text(
                f"Event successfully created in calendar!\n\n"
                f"Title: {event.summary}\n"
                f"Time: {format_datetime(event.start_time)}\n"
                f"Link: {created_event.get('htmlLink', 'Not available')}"
            )
        else:
            await query.edit_message_text(
                "An error occurred when creating the event. Please try again later."
            )

    # Processing selection of specific event from list
    elif callback_data.startswith("create_event_"):
        try:
            # Get index of selected event
            event_index = int(callback_data.split("_")[-1])

            # Get list of events from user's temporary data
            if user_id not in user_data or "events" not in user_data[user_id]:
                await query.edit_message_text("Error: event data not found.")
                return

            events = user_data[user_id]["events"]

            # Check that index is within list bounds
            if event_index < 0 or event_index >= len(events):
                await query.edit_message_text("Error: selected event not found.")
                return

            # Save selected event
            event = events[event_index]
            user_data[user_id]["event"] = event

            # Create event in calendar
            created_event = calendar_service.create_event(event)

            if created_event:
                await query.edit_message_text(
                    f"Event successfully created in calendar!\n\n"
                    f"Title: {event.summary}\n"
                    f"Time: {format_datetime(event.start_time)}\n"
                    f"Link: {created_event.get('htmlLink', 'Not available')}"
                )
            else:
                await query.edit_message_text(
                    "An error occurred when creating the event. Please try again later."
                )
        except (ValueError, IndexError) as e:
            logger.error(f"Error processing event selection: {e}")
            await query.edit_message_text(
                "An error occurred processing event selection."
            )

    elif callback_data == "confirm_all_events":
        # Get events from user's temporary data
        if user_id not in user_data or "events" not in user_data[user_id]:
            await query.edit_message_text("Error: event data not found.")
            return

        events = user_data[user_id]["events"]
        created_events = []
        failed_events = []

        # Create all events
        for event in events:
            created_event = calendar_service.create_event(event)
            if created_event:
                created_events.append((event, created_event))
            else:
                failed_events.append(event)

        # Form report about event creation
        message = f"Events created: {len(created_events)} of {len(events)}\n\n"

        if created_events:
            message += "Successfully created events:\n"
            for event, created in created_events:
                message += f"✅ {event.summary} - {created.get('htmlLink', 'Link not available')}\n"

        if failed_events:
            message += "\nFailed to create the following events:\n"
            for event in failed_events:
                message += f"❌ {event.summary}\n"

        await query.edit_message_text(message)

    # Settings processing
    elif callback_data == "settings_timezone":
        await query.edit_message_text(
            "Time zone settings will be available in future versions."
        )

    elif callback_data == "settings_language":
        await query.edit_message_text(
            "Language settings will be available in future versions."
        )

    # Cancel processing
    elif callback_data in ["cancel_event", "cancel_creation", "cancel_settings"]:
        await query.edit_message_text("Action cancelled.")
        if user_id in user_data:
            del user_data[user_id]


def format_datetime(datetime_str: str) -> str:
    """Formats datetime string to human-readable format"""
    try:
        dt = datetime.fromisoformat(datetime_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return datetime_str


def main() -> None:
    """Launches the bot"""
    # Archive old logs
    try:
        archive_old_logs()
        logger.info("Old logs successfully archived")
    except Exception as e:
        logger.error(f"Error archiving logs: {e}")

    # Create application and add handlers
    application = Application.builder().token(TOKEN).build()

    # Set up bot commands
    application.post_init = setup_commands

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("summary", summary_command))

    # Add message handlers
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Add button handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Launch the bot
    application.run_polling()
    logger.info("Bot launched")


if __name__ == "__main__":
    main()
