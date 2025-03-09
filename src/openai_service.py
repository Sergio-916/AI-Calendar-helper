import os
import json
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
from openai import OpenAI
from models import CalendarEvent, RecurrenceInfo, EventAttachment
from logger_config import setup_logger

# Получаем настроенный логгер
logger = setup_logger("openai_service")


class OpenAIService:
    """Сервис для работы с OpenAI API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning(
                "API ключ OpenAI не найден. Функции извлечения информации будут недоступны."
            )
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def extract_event_info(self, text: str) -> List[CalendarEvent]:
        """Извлекает информацию о событиях из текста с помощью OpenAI API"""
        if not self.client:
            logger.error("API ключ OpenAI не настроен")
            return []

        try:
            current_year = datetime.now().year
            current_date = datetime.now().date()
            current_weekday = datetime.now().strftime("%A")

            # Создаем системный промпт с инструкциями
            system_prompt = f"""
            Ты - помощник, который извлекает структурированную информацию о событиях из текста.
            Ты должен быть особенно внимателен к датам, времени и повторяющимся событиям.
            
            Правила обработки дат:
            1. Сегодняшний день недели: {current_weekday}
            2. Если указан день недели, например "вск", "пн" и т.д, считай, что это ближайший день недели на текущей неделе или на следующей
            3. Если год не указан явно, используй текущий год: {current_year}
            4. Все даты должны быть в формате YYYY-MM-DDTHH:MM:SS (строка ISO формата)
            5. Если указан только месяц и день, используй {current_year} как год
            6. Если указан день недели, рассчитай дату относительно {current_date}
          
            Правила обработки повторяющихся событий:
            1. Если событие повторяется каждую неделю, укажи frequency: "WEEKLY", interval: 1
            2. Если событие повторяется в определенные дни недели, укажи их в поле days
            3. Используй коды дней недели: MO, TU, WE, TH, FR, SA, SU
            4. Если указана дата окончания повторений, укажи ее в поле until в формате YYYY-MM-DD
            
            Верни результат в формате JSON с полями:
            - summary: название события (обязательно)
            - description: описание события (опционально)
            - start_time: время начала в формате ISO (обязательно)
            - end_time: время окончания в формате ISO (опционально)
            - location: место проведения (опционально)
            - recurrence: информация о повторении (опционально)
              - frequency: частота повторения (DAILY, WEEKLY, MONTHLY, YEARLY)
              - interval: интервал повторения (число)
              - days: дни недели для повторения (массив строк: MO, TU, WE, TH, FR, SA, SU)
              - until: дата окончания повторений в формате YYYY-MM-DD
              - count: количество повторений (число)
            """

            # Создаем пользовательский промпт с текстом для анализа
            user_prompt = f"Извлеки информацию о событиях из следующего текста: {text}"

            # Используем метод chat.completions.create с JSON форматом ответа
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            # Получаем результат в виде JSON строки
            result_json = response.choices[0].message.content
            logger.info(f"Получен ответ от OpenAI: {result_json}")

            # Парсим JSON
            try:
                event_data = json.loads(result_json)

                # Проверяем, что получен словарь
                if not isinstance(event_data, dict):
                    logger.error(f"Неверный формат ответа от OpenAI: {event_data}")
                    return []

                # Проверяем обязательные поля
                if "summary" not in event_data or "start_time" not in event_data:
                    logger.error(
                        f"В ответе отсутствуют обязательные поля: {event_data}"
                    )
                    return []

                # Создаем объект RecurrenceInfo, если есть данные о повторении
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

                # Создаем список вложений, если они есть
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

                # Создаем объект CalendarEvent
                event = CalendarEvent(
                    summary=event_data.get("summary", "Событие без названия"),
                    description=event_data.get("description"),
                    start_time=event_data.get("start_time"),
                    end_time=event_data.get("end_time"),
                    location=event_data.get("location"),
                    attachments=attachments if attachments else None,
                    recurrence=recurrence,
                )

                # Возвращаем список с одним событием
                return [event]
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка при парсинге JSON: {e}, ответ: {result_json}")
                return []
            except Exception as e:
                logger.error(f"Ошибка при создании объекта CalendarEvent: {e}")
                return []

        except Exception as e:
            logger.error(f"Ошибка при извлечении информации о событиях: {e}")
            return []

    def transcribe_audio(self, audio_file_path: str) -> str:
        """Преобразует аудио в текст с помощью OpenAI API"""
        if not self.client:
            logger.error("API ключ OpenAI не настроен")
            return ""

        try:
            with open(audio_file_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file
                )

            logger.info(
                f"Аудио успешно преобразовано в текст: {transcription.text[:50]}..."
            )
            return transcription.text

        except Exception as e:
            logger.error(f"Ошибка при преобразовании аудио в текст: {e}")
            return ""

    def generate_daily_summary(self, events: List[Any]) -> str:
        """Генерирует сводку событий за день"""
        if not self.client or not events:
            return "Нет событий для создания сводки."

        try:
            # Формируем текст с событиями, учитывая разные типы объектов
            events_text = []
            for event in events:
                if isinstance(event, dict):
                    # Если это словарь из Google Calendar API
                    title = event.get("summary", "Событие без названия")
                    description = event.get("description", "Без описания")
                    events_text.append(f"- {title}: {description}")
                else:
                    # Если это объект CalendarEvent
                    title = (
                        event.summary
                        if hasattr(event, "summary")
                        else "Событие без названия"
                    )
                    description = (
                        event.description
                        if hasattr(event, "description")
                        else "Без описания"
                    )
                    events_text.append(f"- {title}: {description or 'Без описания'}")

            events_text_str = "\n".join(events_text)

            prompt = f"""
            Создай краткую сводку следующих событий за день:
            
            {events_text_str}
            
            Сводка должна быть информативной и лаконичной.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты - помощник, который создает краткие и информативные сводки событий.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            summary = response.choices[0].message.content
            logger.info(f"Сгенерирована сводка событий: {summary[:50]}...")
            return summary

        except Exception as e:
            logger.error(f"Ошибка при генерации сводки: {e}")
            return "Не удалось создать сводку событий."
