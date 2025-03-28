import os
import json
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
from openai import OpenAI
from models import CalendarEvent, RecurrenceInfo, EventAttachment
from logger_config import setup_logger

# Get configured logger
logger = setup_logger("openai_service")


class OpenAIService:
    """Service for working with OpenAI API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning(
                "OpenAI API key not found. Information extraction functions will be unavailable."
            )
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def extract_event_info(self, text: str) -> List[CalendarEvent]:
        """Extracts information about events from text using OpenAI API"""
        if not self.client:
            logger.error("OpenAI API key not configured")
            return []

        try:
            current_year = datetime.now().year
            current_date = datetime.now().date()
            current_weekday = datetime.now().strftime("%A")

            # Create system prompt with instructions
            system_prompt = f"""
            You are an assistant who extracts structured information about events from text.
            You should be particularly attentive to dates, times, and recurring events.
            
            Date processing rules:
            1. Today's day of the week: {current_weekday}
            2. If a day of the week is specified, such as "Sun", "Mon", etc., consider it to be the nearest day of the week in the current or next week
            3. If the year is not explicitly specified, use the current year: {current_year}
            4. All dates should be in YYYY-MM-DDTHH:MM:SS format (ISO format string)
            5. If only month and day are specified, use {current_year} as the year
            6. If a day of the week is specified, calculate the date relative to {current_date}
          
            Rules for processing recurring events:
            1. If an event repeats every week, specify frequency: "WEEKLY", interval: 1
            2. If an event repeats on specific days of the week, specify them in the days field
            3. Use day codes: MO, TU, WE, TH, FR, SA, SU
            4. If an end date for repetitions is specified, indicate it in the until field in YYYY-MM-DD format
            
            Return the result in JSON format with the following fields:
            - summary: event title (required)
            - description: event description (optional)
            - start_time: start time in ISO format (required)
            - end_time: end time in ISO format (optional)
            - location: event location (optional)
            - recurrence: recurrence information (optional)
              - frequency: recurrence frequency (DAILY, WEEKLY, MONTHLY, YEARLY)
              - interval: recurrence interval (number)
              - days: days of the week for recurrence (array of strings: MO, TU, WE, TH, FR, SA, SU)
              - until: end date of recurrences in YYYY-MM-DD format
              - count: number of recurrences (number)
            """

            # Create user prompt with text for analysis
            user_prompt = (
                f"Extract information about events from the following text: {text}"
            )

            # Use chat.completions.create method with JSON response format
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            # Get result as JSON string
            result_json = response.choices[0].message.content
            logger.info(f"Received response from OpenAI: {result_json}")

            # Parse JSON
            try:
                event_data = json.loads(result_json)

                # Check that we received a dictionary
                if not isinstance(event_data, dict):
                    logger.error(f"Invalid response format from OpenAI: {event_data}")
                    return []

                # Check required fields
                if "summary" not in event_data or "start_time" not in event_data:
                    logger.error(
                        f"Required fields missing in the response: {event_data}"
                    )
                    return []

                # Create RecurrenceInfo object if recurrence data exists
                recurrence = None
                if "recurrence" in event_data and event_data["recurrence"]:
                    recurrence_data = event_data["recurrence"]
                    recurrence = RecurrenceInfo(
                        frequency=recurrence_data.get("frequency", "WEEKLY"),
                        interval=recurrence_data.get("interval"),
                        days=recurrence_data.get("days"),
                        until=recurrence_data.get("until"),
                        count=recurrence_data.get("count"),
                    )

                # Create list of attachments if they exist
                attachments = []
                if "attachments" in event_data and event_data["attachments"]:
                    for attachment_data in event_data["attachments"]:
                        attachment = EventAttachment(
                            file_id=attachment_data.get("file_id", ""),
                            file_name=attachment_data.get("file_name", ""),
                            file_type=attachment_data.get("file_type", ""),
                            file_url=attachment_data.get("file_url"),
                        )
                        attachments.append(attachment)

                # Create CalendarEvent object
                event = CalendarEvent(
                    summary=event_data.get("summary", "Event without title"),
                    description=event_data.get("description"),
                    start_time=event_data.get("start_time"),
                    end_time=event_data.get("end_time"),
                    location=event_data.get("location"),
                    attachments=attachments if attachments else None,
                    recurrence=recurrence,
                )

                # Return list with one event
                return [event]
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON: {e}, response: {result_json}")
                return []
            except Exception as e:
                logger.error(f"Error creating CalendarEvent object: {e}")
                return []

        except Exception as e:
            logger.error(f"Error extracting event information: {e}")
            return []

    def transcribe_audio(self, audio_file_path: str) -> str:
        """Converts audio to text using OpenAI API"""
        if not self.client:
            logger.error("OpenAI API key not configured")
            return ""

        try:
            with open(audio_file_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file
                )

            logger.info(
                f"Audio successfully converted to text: {transcription.text[:50]}..."
            )
            return transcription.text

        except Exception as e:
            logger.error(f"Error converting audio to text: {e}")
            return ""

    def generate_daily_summary(self, events: List[Any]) -> str:
        """Generates a summary of events for the day"""
        if not self.client or not events:
            return "No events to create a summary for."

        try:
            # Form text with events, considering different object types
            events_text = []
            for event in events:
                if isinstance(event, dict):
                    # If it's a dictionary from Google Calendar API
                    title = event.get("summary", "Event without title")
                    description = event.get("description", "No description")
                    events_text.append(f"- {title}: {description}")
                else:
                    # If it's a CalendarEvent object
                    title = (
                        event.summary
                        if hasattr(event, "summary")
                        else "Event without title"
                    )
                    description = (
                        event.description
                        if hasattr(event, "description")
                        else "No description"
                    )
                    events_text.append(f"- {title}: {description or 'No description'}")

            events_text_str = "\n".join(events_text)

            prompt = f"""
            Create a brief summary of the following events for the day:
            
            {events_text_str}
            
            The summary should be informative and concise.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant who creates brief and informative event summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            summary = response.choices[0].message.content
            logger.info(f"Generated event summary: {summary[:50]}...")
            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Failed to create event summary."
