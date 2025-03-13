# Telegram Bot for Google Calendar

This bot allows you to create events in Google Calendar through Telegram. It can process text messages, audio recordings, and files, adding them to the calendar in a structured manner. The bot uses the OpenAI API to extract event information from text and convert voice messages to text.

## Features

- Create events in Google Calendar from text messages with automatic information extraction
- Convert voice messages to text and create events based on them
- Attach audio recordings and files to events
- View upcoming events in the calendar
- Create daily event summaries
- Structured data storage using Pydantic
- Containerization with Docker

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and find [@BotFather](https://t.me/BotFather)
2. Send the command `/newbot` and follow the instructions
3. Obtain the bot token and save it

### 2. Set Up Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google Calendar API
4. Create OAuth 2.0 credentials
5. Download the JSON file with the credentials and save it as `credentials.json` in the root folder of the project

### 3. Obtain OpenAI API Key

1. Register or log in to [OpenAI Platform](https://platform.openai.com/)
2. Go to the API Keys section
3. Create a new API key and save it

### 4. Set Up Environment Variables

1. Copy the `.env.example` file to `.env`
2. Fill in the environment variables:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   OPENAI_API_KEY=your_openai_api_key_here
   ```

## Running

### Local Run

1. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

2. Run the bot:
   ```sh
   python bot.py
   ```

### Run with Docker

1. Build and run the container:
   ```sh
   docker-compose up -d
   ```

2. To view logs:
   ```sh
   docker-compose logs -f
   ```

## Usage

1. **Create an event from text**:
   - Send a text message with the event description to the bot
   - The bot will automatically extract event information using OpenAI
   - Confirm the creation of the event by clicking "Yes"

2. **Create an event from a voice message**:
   - Send a voice message to the bot
   - The bot will convert it to text using OpenAI and extract event information
   - Confirm the creation of the event by clicking "Yes"

3. **Create an event with a file**:
   - Send any file to the bot
   - The bot will suggest creating an event with the attached file
   - Confirm the creation of the event by clicking "Yes"

4. **View upcoming events**:
   - Send the command `/events`
   - The bot will show a list of upcoming events in your calendar

5. **Create a daily event summary**:
   - Send the command `/summary`
   - The bot will create a daily event summary using OpenAI

## Bot Commands

- `/start` - Start working with the bot
- `/help` - Show help
- `/events` - Show upcoming events
- `/summary` - Create a daily event summary

## Usage Examples

### Text Message

Send the bot a message:
```
Meeting with a client tomorrow at 3:00 PM at the office on Lenin 10. Discuss the new project and prepare a presentation.
```

The bot will extract event information:
- Title: Meeting with a client
- Date and time: tomorrow at 3:00 PM
- Location: office on Lenin 10
- Description: Discuss the new project and prepare a presentation

### Voice Message

Send the bot a voice message with the text:
```
Remind me to call mom on Saturday at 12 PM
```

The bot will convert the audio to text and extract event information:
- Title: Call mom
- Date and time: Saturday, 12:00 PM
- Description: Reminder to call

## Future Development

- Improve recognition of structured information from text
- Add event reminders
- Integrate with other calendar services
- Support recurring events
- Improve the user interface with inline buttons