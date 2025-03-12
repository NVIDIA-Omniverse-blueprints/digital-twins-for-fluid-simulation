import logging
from typing import Optional


class _Formatter(logging.Formatter):
    """Logging color formatter"""

    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;1m"
    clear = "\x1b[0m"

    fmt = "{color}[%(asctime)s %(name)s (%(levelname)s)] %(message)s\x1b[0m"

    formats = {
        logging.DEBUG: fmt.format(color=grey),
        logging.INFO: fmt.format(color=green),
        logging.WARNING: fmt.format(color=yellow),
        logging.ERROR: fmt.format(color=red),
        logging.CRITICAL: fmt.format(color=red),
    }

    def format(self, record):
        fmt = _Formatter.formats.get(record.levelno, _Formatter.fmt.format(color=_Formatter.clear))  # default no color
        formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


class _LogFileFormatter(logging.Formatter):
    """File Logging formatter (no color)"""

    fmt = "[%(asctime)s %(name)s (%(levelname)s)] %(message)s"

    def format(self, record):
        formatter = logging.Formatter(fmt=_LogFileFormatter.fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def get_logger(name: str, level: Optional[int] = logging.DEBUG):
    """Get logger"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        formatter = _Formatter()
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        formatter = _LogFileFormatter()
        handler = logging.FileHandler("pyLogging.log")
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
