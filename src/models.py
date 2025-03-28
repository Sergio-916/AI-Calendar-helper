from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class EventAttachment(BaseModel):
    """Model for event attachments"""

    file_id: str
    file_name: str
    file_type: str
    file_url: Optional[str] = None


class RecurrenceInfo(BaseModel):
    """Model for event recurrence information"""

    frequency: str  # DAILY, WEEKLY, MONTHLY, YEARLY
    interval: Optional[int] = None  # Recurrence interval (every N days/weeks/months)
    days: Optional[List[str]] = (
        None  # Days of the week for recurrence (MO, TU, WE, TH, FR, SA, SU)
    )
    until: Optional[str] = None  # End date of recurrence in YYYY-MM-DD format
    count: Optional[int] = None  # Number of recurrences


class CalendarEvent(BaseModel):
    """Model for calendar event"""

    summary: str
    description: Optional[str] = None
    start_time: str  # Start time in ISO format (YYYY-MM-DDTHH:MM:SS)
    end_time: Optional[str] = None  # End time in ISO format
    location: Optional[str] = None
    attachments: Optional[List[EventAttachment]] = None
    recurrence: Optional[RecurrenceInfo] = None

    def to_google_event(self) -> dict:
        """Converts the model to Google Calendar event format"""
        # Use one timezone for all dates
        timezone = "America/Argentina/Buenos_Aires"

        try:
            # Convert strings to datetime objects
            start_datetime = datetime.fromisoformat(self.start_time)

            event = {
                "summary": self.summary,
                "start": {
                    "dateTime": self.start_time,
                    "timeZone": timezone,
                },
            }

            if self.description:
                event["description"] = self.description

            if self.end_time:
                event["end"] = {
                    "dateTime": self.end_time,
                    "timeZone": timezone,
                }
            else:
                # If end time is not specified, set it to one hour after the start
                end_time = (
                    start_datetime.replace(hour=start_datetime.hour + 1)
                ).isoformat()
                event["end"] = {
                    "dateTime": end_time,
                    "timeZone": timezone,
                }

            if self.location:
                event["location"] = self.location

            # Add recurrence information
            if self.recurrence:
                recurrence_rule = ["RRULE:"]

                # Recurrence frequency
                recurrence_rule.append(f"FREQ={self.recurrence.frequency}")

                # Recurrence interval
                if (
                    self.recurrence.interval is not None
                    and self.recurrence.interval > 1
                ):
                    recurrence_rule.append(f"INTERVAL={self.recurrence.interval}")

                # Days of the week for recurrence
                if self.recurrence.days:
                    days_str = ",".join(self.recurrence.days)
                    recurrence_rule.append(f"BYDAY={days_str}")

                # End date of recurrence
                if self.recurrence.until:
                    # Convert date string to RRULE format
                    until_date = datetime.fromisoformat(
                        self.recurrence.until.replace("-", "")
                    )
                    until_str = until_date.strftime("%Y%m%dT%H%M%SZ")
                    recurrence_rule.append(f"UNTIL={until_str}")

                # Number of recurrences
                if self.recurrence.count:
                    recurrence_rule.append(f"COUNT={self.recurrence.count}")

                # Add recurrence rule to the event
                event["recurrence"] = [";".join(recurrence_rule)]

            # Add attachment information to the description
            if self.attachments:
                attachment_text = "\n\nAttachments:\n"
                for attachment in self.attachments:
                    attachment_text += (
                        f"- {attachment.file_name} ({attachment.file_type})"
                    )
                    if attachment.file_url:
                        attachment_text += f": {attachment.file_url}"
                    attachment_text += "\n"

                if "description" in event:
                    event["description"] += attachment_text
                else:
                    event["description"] = attachment_text

            return event
        except Exception as e:
            # In case of error, return a basic event
            return {
                "summary": self.summary,
                "description": self.description,
                "start": {"dateTime": self.start_time, "timeZone": timezone},
                "end": {
                    "dateTime": self.end_time or self.start_time,
                    "timeZone": timezone,
                },
            }
