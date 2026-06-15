import logging
import logging.config
from logging.handlers import RotatingFileHandler

from stac_dedl_core.config import (
    APP_LOGGER_FILE_BACKUP_COUNT,
    APP_LOGGER_FILE_PATH,
    APP_LOGGER_FILE_TRUNCATE_SIZE,
    APP_LOGGER_LEVEL,
    APP_LOGGER_NAME,
)


def setup_logging(log_file_path: str = APP_LOGGER_FILE_PATH, level: int = logging.DEBUG) -> None:
    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(level)

    console_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=APP_LOGGER_FILE_TRUNCATE_SIZE,
        backupCount=APP_LOGGER_FILE_BACKUP_COUNT,
    )

    console_handler.setLevel(level)
    file_handler.setLevel(level)

    console_handler.setFormatter(logging.Formatter("%(message)s"))
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


# Logging is set up on import — import this module before all others in entry-point scripts
setup_logging(APP_LOGGER_FILE_PATH, APP_LOGGER_LEVEL)
