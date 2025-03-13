import os
import pickle
from datetime import datetime, UTC
import json
from typing import Dict, List, Optional, Any
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from models import CalendarEvent
from logger_config import setup_logger
from google.oauth2.service_account import Credentials

# Получаем настроенный логгер
logger = setup_logger("calendar_service")

# Определяем области доступа
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarService:
    """Сервис для работы с Google Calendar API"""

    def __init__(self):
        # Получаем путь к директории src
        src_dir = os.path.dirname(os.path.abspath(__file__))
        # Получаем путь к корневой директории проекта (на уровень выше src)
        root_dir = os.path.dirname(src_dir)

        # Устанавливаем пути к файлам
        self.credentials_file = os.path.join(root_dir, "credentials.json")
        self.token_file = os.path.join(root_dir, "token.pickle")

        self.creds = None
        self.service = None

    def authenticate(self):
        """Аутентификация в Google Calendar API"""
        creds = None

        # Проверяем наличие токена
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                creds = pickle.load(token)

        # Если нет действительных учетных данных, запрашиваем их
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Сохраняем учетные данные для следующего запуска
            with open(self.token_file, "wb") as token:
                pickle.dump(creds, token)

        # Создаем сервис
        self.service = build("calendar", "v3", credentials=creds)
        logger.info("Аутентификация в Google Calendar API успешно выполнена")

    def create_event(self, event: CalendarEvent, calendar_id="primary"):
        """Создает событие в Google Calendar"""

        custom_reminder = {
            "useDefault": False,
            "overrides": [
                # {"method": "email", "minutes": 30},  # Email за 30 минут до события
                {
                    "method": "popup",
                    "minutes": 10,
                },  # Всплывающее уведомление за 10 минут
            ],
        }

        if not self.service:
            self.authenticate()

        try:
            google_event = event.to_google_event()

            # Добавляем настройки напоминаний в тело события
            google_event["reminders"] = custom_reminder

            created_event = (
                self.service.events()
                .insert(
                    calendarId=calendar_id, body=google_event, sendNotifications=True
                )
                .execute()
            )
            logger.info(f"Событие создано: {created_event.get('htmlLink')}")
            return created_event
        except HttpError as error:
            logger.error(f"Ошибка при создании события: {error}")
            return None

    def get_events(self, max_results=10, calendar_id="primary"):
        """Получает список ближайших событий из календаря"""
        if not self.service:
            self.authenticate()

        try:
            now = datetime.now(UTC).isoformat()
            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            return events
        except HttpError as error:
            logger.error(f"Ошибка при получении событий: {error}")
            return []
