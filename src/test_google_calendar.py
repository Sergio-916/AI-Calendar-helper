import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta, UTC

# Если изменить эти области, удалите файл token.pickle
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def test_google_calendar():
    print("Testing Google Calendar API connection...")

    creds = None
    # Проверяем наличие токена
    if os.path.exists("token.pickle"):
        print("Found existing token.pickle")
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # Если нет действительных учетных данных, запрашиваем их
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("Getting new credentials...")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(
                port=0, access_type="offline", prompt="consent"
            )

        # Сохраняем учетные данные для следующего запуска
        print("Saving credentials to token.pickle...")
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    try:
        # Создаем сервис
        service = build("calendar", "v3", credentials=creds)

        # Получаем текущее время
        now = datetime.now(UTC)

        # Создаем тестовое событие
        event = {
            "summary": "Тестовое событие",
            "description": "Это тестовое событие для проверки API",
            "start": {
                "dateTime": now.isoformat() + "Z",
                "timeZone": "Europe/Moscow",
            },
            "end": {
                "dateTime": (now + timedelta(hours=1)).isoformat() + "Z",
                "timeZone": "Europe/Moscow",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    # {"method": "email", "minutes": 30},  # Email за 30 минут до события
                    {
                        "method": "popup",
                        "minutes": 10,
                    },  # Всплывающее уведомление за 10 минут
                ],
            },
        }

        # Добавляем событие
        print("Creating test event...")
        created_event = (
            service.events().insert(calendarId="primary", body=event).execute()
        )
        print(f"Тестовое событие создано: {created_event.get('htmlLink')}")

        # Получаем список ближайших событий
        print("\nПолучаем список событий...")
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            print("Предстоящих событий не найдено.")
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            print(f"- {start}: {event['summary']}")

    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    test_google_calendar()
