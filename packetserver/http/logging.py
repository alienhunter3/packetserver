from .config import Settings
import logging


def init_logging():
    settings = Settings()

    desired_level = settings.log_level.upper().strip()

    if desired_level not in logging.getLevelNamesMapping():
        raise ValueError(f"Invalid log level '{desired_level}'")

    logging.basicConfig(level=logging.getLevelName(desired_level))
