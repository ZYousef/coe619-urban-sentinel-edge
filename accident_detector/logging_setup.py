"""
logging_setup.py

Configures the 'accident_detector' logger with rotating file and console handlers.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from .config import Config


def setup_logging(log_file: str = None) -> None:
    """
    Configures the 'accident_detector' logger.

    - RotatingFileHandler at `log_file` (default from config or 'logs/accident_detector.log')
    - Console StreamHandler
    """
    logger = logging.getLogger("accident_detector")
    logger.setLevel(logging.INFO)

    # Determine log file path (config override possible)
    cfg = Config()
    if log_file is None:
        try:
            log_file = cfg.get("Logging", "LogFile")
        except Exception:
            log_file = "logs/accident_detector.log"

    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Formatter with ISO 8601 timestamps
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z"
    )

    # File handler: rotates after 10 MB, keeps 5 backups
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
