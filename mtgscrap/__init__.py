"""

    mtgscrap
    ~~~~~~~~
    MTG hate-card reports per archetype, sourced from the Videre API.

    @author: mazz3rr

"""
import logging
import os
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Union

__appname__ = __name__
__version__ = "1.0"
__description__ = "Scrape MTG decklists from MTGGoldfish."
__author__ = "z33k"
__license__ = "MIT License"

# type aliases
type Json = Union[str, int, float, bool, datetime, date, None, Dict[str, "Json"], List["Json"]]
type PathLike = str | Path


FILENAME_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
READABLE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
VAR_DIR = Path(os.getcwd()) / "var"
OUTPUT_DIR = Path(os.getcwd()) / "_output"
LOG_DIR = VAR_DIR / "logs" if (VAR_DIR / "logs").exists() else Path(os.getcwd())
LOG_SIZE = 1024*1024*20  # 20MB


_logging_initialized = False


def init_log() -> None:
    """Initialize logging.
    """
    global _logging_initialized

    if not _logging_initialized:
        logfile = LOG_DIR / "mtgscrap.log"
        log_format = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
        log_level = logging.INFO

        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        formatter = logging.Formatter(log_format)
        handler = RotatingFileHandler(logfile, maxBytes=LOG_SIZE, backupCount=10)
        handler.setFormatter(formatter)
        handler.setLevel(log_level)
        root_logger.addHandler(handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(log_level)
        root_logger.addHandler(stream_handler)

        _logging_initialized = True


init_log()


