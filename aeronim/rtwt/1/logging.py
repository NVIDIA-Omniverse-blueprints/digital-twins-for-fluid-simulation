import sys

from loguru import logger


def setup_logger(process_id: int, model_name: str = "Model") -> None:
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> |"
        + " <level>{level:<8}</level> |"
        + f" <magenta>{model_name}:{process_id:02d}</magenta> | "
        + " <cyan>{name}</cyan>:<cyan>{line}</cyan> -"
        + " <level>{message}</level>"
    )
    logger.remove()
    logger.add(sys.stderr, format=log_format)
    logger.debug("Logger configured")


def get_logger():
    return logger
