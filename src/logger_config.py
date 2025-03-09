import os
import logging
import shutil
import re
import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def archive_old_logs():
    """
    Архивирует старые логи в отдельные файлы с датой в имени файла.
    Ищет записи с датами в логах и создает отдельные файлы для каждого дня.
    """
    # Создаем директорию для архивных логов, если она не существует
    archive_dir = Path("./data/logs_archive")
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Путь к основному лог-файлу
    log_file = Path("./data/bot.log")

    # Проверяем, существует ли лог-файл
    if not log_file.exists():
        logging.warning(f"Лог-файл {log_file} не найден.")
        return

    # Словарь для хранения логов по датам
    logs_by_date = {}

    # Регулярное выражение для извлечения даты из строки лога
    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}")

    # Читаем лог-файл и группируем записи по датам
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                match = date_pattern.search(line)
                if match:
                    date_str = match.group(1)
                    if date_str not in logs_by_date:
                        logs_by_date[date_str] = []
                    logs_by_date[date_str].append(line)
    except Exception as e:
        logging.error(f"Ошибка при чтении лог-файла: {e}")
        return

    # Текущая дата
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # Записываем логи в отдельные файлы по датам (кроме сегодняшних)
    for date_str, logs in logs_by_date.items():
        # Пропускаем сегодняшние логи
        if date_str == today:
            continue

        # Создаем имя файла с датой
        archive_file = archive_dir / f"bot_log_{date_str}.log"

        # Записываем логи в файл
        try:
            with open(archive_file, "w", encoding="utf-8", errors="replace") as f:
                f.writelines(logs)
            logging.info(f"Архивированы логи за {date_str} в файл {archive_file}")
        except Exception as e:
            logging.error(f"Ошибка при архивировании логов за {date_str}: {e}")

    # Создаем новый лог-файл только с сегодняшними логами
    try:
        if today in logs_by_date:
            with open(log_file, "w", encoding="utf-8", errors="replace") as f:
                f.writelines(logs_by_date[today])
            logging.info(f"Лог-файл обновлен, оставлены только записи за {today}")
        else:
            # Если сегодняшних логов нет, создаем пустой файл
            with open(log_file, "w", encoding="utf-8") as f:
                pass
            logging.info("Создан пустой лог-файл (сегодняшних логов не найдено)")
    except Exception as e:
        logging.error(f"Ошибка при обновлении лог-файла: {e}")


def setup_logger(name=None):
    """
    Настраивает и возвращает логгер с заданными параметрами.
    Если имя не указано, настраивает корневой логгер.
    """
    # Создаем директорию для логов, если она не существует
    os.makedirs("./data", exist_ok=True)
    log_file = "./data/bot.log"

    # Создаем обработчик для записи в файл с ротацией
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024 * 5,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )

    # Настраиваем форматирование логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # Если имя не указано, настраиваем корневой логгер
    if name is None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[file_handler],
        )
        logger = logging.getLogger()
    else:
        # Иначе создаем и настраиваем именованный логгер
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)

        # Проверяем, есть ли уже обработчики у логгера
        if not logger.handlers:
            logger.addHandler(file_handler)

        # Отключаем передачу сообщений родительскому логгеру
        logger.propagate = False

    return logger
