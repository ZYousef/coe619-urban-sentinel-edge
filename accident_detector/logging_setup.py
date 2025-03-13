"""
logging_setup.py

This module defines setup_logging(), which configures logging to both
a rotating file handler and the console.
"""

import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Creates and returns a logger named "accident_detector" that writes
    to 'accident_detector.log' in a rotating fashion, as well as to
    the console.
    """
    logger = logging.getLogger("accident_detector")
    logger.setLevel(logging.INFO)

    # Clear existing handlers (in case setup is called multiple times)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    file_handler = RotatingFileHandler(
        "/var/log/accident_detector.log",
        maxBytes=10485760,  # 10 MB
        backupCount=5
    )
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)-20s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
