import logging
import os
from pathlib import Path
from datetime import datetime

def setup_logger(log_dir=None, log_file=None):
    """Sets up and returns a logger instance with a rotating file handler."""

    project_dir = Path(__file__).parent.parent.resolve()
    log_dir = Path(log_dir) if log_dir else (project_dir / "logs")
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_file or datetime.now().strftime("%Y-%m-%d-%H-%M-%S.log")
    log_path = log_dir / log_file
    
    logger = logging.getLogger(__name__)

    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger

logger = setup_logger()