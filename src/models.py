from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class EventAttachment(BaseModel):
    """Модель для вложений к событию"""

    file_id: str
    file_name: str
    file_type: str
    file_url: Optional[str] = None


class RecurrenceInfo(BaseModel):
    """Модель для информации о повторении события"""

    frequency: str  # DAILY, WEEKLY, MONTHLY, YEARLY
    interval: Optional[int] = None  # Интервал повторения (каждые N дней/недель/месяцев)
    days: Optional[List[str]] = (
        None  # Дни недели для повторения (MO, TU, WE, TH, FR, SA, SU)
    )
    until: Optional[str] = None  # Дата окончания повторений в формате YYYY-MM-DD
    count: Optional[int] = None  # Количество повторений


class CalendarEvent(BaseModel):
    """Модель для события календаря"""

    summary: str
    description: Optional[str] = None
    start_time: str  # Время начала в формате ISO (YYYY-MM-DDTHH:MM:SS)
    end_time: Optional[str] = None  # Время окончания в формате ISO
    location: Optional[str] = None
    attachments: Optional[List[EventAttachment]] = None
    recurrence: Optional[RecurrenceInfo] = None

    def to_google_event(self) -> dict:
        """Преобразует модель в формат события Google Calendar"""
        # Используем один часовой пояс для всех дат
        timezone = "America/Argentina/Buenos_Aires"

        try:
            # Преобразуем строки в объекты datetime
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
                # Если конечное время не указано, устанавливаем его на час позже начала
                end_time = (
                    start_datetime.replace(hour=start_datetime.hour + 1)
                ).isoformat()
                event["end"] = {
                    "dateTime": end_time,
                    "timeZone": timezone,
                }

            if self.location:
                event["location"] = self.location

            # Добавляем информацию о повторении события
            if self.recurrence:
                recurrence_rule = ["RRULE:"]

                # Частота повторения
                recurrence_rule.append(f"FREQ={self.recurrence.frequency}")

                # Интервал повторения
                if (
                    self.recurrence.interval is not None
                    and self.recurrence.interval > 1
                ):
                    recurrence_rule.append(f"INTERVAL={self.recurrence.interval}")

                # Дни недели для повторения
                if self.recurrence.days:
                    days_str = ",".join(self.recurrence.days)
                    recurrence_rule.append(f"BYDAY={days_str}")

                # Дата окончания повторений
                if self.recurrence.until:
                    # Преобразуем строку даты в формат для RRULE
                    until_date = datetime.fromisoformat(
                        self.recurrence.until.replace("-", "")
                    )
                    until_str = until_date.strftime("%Y%m%dT%H%M%SZ")
                    recurrence_rule.append(f"UNTIL={until_str}")

                # Количество повторений
                if self.recurrence.count:
                    recurrence_rule.append(f"COUNT={self.recurrence.count}")

                # Добавляем правило повторения в событие
                event["recurrence"] = [";".join(recurrence_rule)]

            # Добавляем информацию о вложениях в описание
            if self.attachments:
                attachment_text = "\n\nВложения:\n"
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
            # В случае ошибки возвращаем базовое событие
            return {
                "summary": self.summary,
                "description": self.description,
                "start": {"dateTime": self.start_time, "timeZone": timezone},
                "end": {
                    "dateTime": self.end_time or self.start_time,
                    "timeZone": timezone,
                },
            }
