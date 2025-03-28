import os
import logging
import shutil
import re
import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def archive_old_logs():
    """
    Archives old logs into separate files with date in the filename.
    Looks for entries with dates in the logs and creates separate files for each day.
    """
    # Create directory for archived logs if it doesn't exist
    archive_dir = Path("./data/logs_archive")
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Path to the main log file
    log_file = Path("./data/bot.log")

    # Check if the log file exists
    if not log_file.exists():
        logging.warning(f"Log file {log_file} not found.")
        return

    # Dictionary to store logs by date
    logs_by_date = {}

    # Regular expression to extract date from log line
    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}")

    # Read the log file and group entries by date
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
        logging.error(f"Error reading log file: {e}")
        return

    # Current date
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # Write logs to separate files by date (except today's logs)
    for date_str, logs in logs_by_date.items():
        # Skip today's logs
        if date_str == today:
            continue

        # Create filename with date
        archive_file = archive_dir / f"bot_log_{date_str}.log"

        # Write logs to file
        try:
            with open(archive_file, "w", encoding="utf-8", errors="replace") as f:
                f.writelines(logs)
            logging.info(f"Archived logs for {date_str} to file {archive_file}")
        except Exception as e:
            logging.error(f"Error archiving logs for {date_str}: {e}")

    # Create new log file with only today's logs
    try:
        if today in logs_by_date:
            with open(log_file, "w", encoding="utf-8", errors="replace") as f:
                f.writelines(logs_by_date[today])
            logging.info(f"Log file updated, kept only entries for {today}")
        else:
            # If there are no today's logs, create empty file
            with open(log_file, "w", encoding="utf-8") as f:
                pass
            logging.info("Created empty log file (no today's logs found)")
    except Exception as e:
        logging.error(f"Error updating log file: {e}")


def setup_logger(name=None):
    """
    Sets up and returns a logger with specified parameters.
    If no name is provided, configures the root logger.
    """
    # Create directory for logs if it doesn't exist
    os.makedirs("./data", exist_ok=True)
    log_file = "./data/bot.log"

    # Create handler for file writing with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024 * 5,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )

    # Configure log formatting
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # If no name is provided, configure the root logger
    if name is None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[file_handler],
        )
        logger = logging.getLogger()
    else:
        # Otherwise create and configure a named logger
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)

        # Check if the logger already has handlers
        if not logger.handlers:
            logger.addHandler(file_handler)

        # Disable propagation of messages to parent logger
        logger.propagate = False

    return logger
