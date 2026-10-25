"""
OmniSight — Logging Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Structured JSON logging with configurable levels per module.
"""

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", json_format: bool = False) -> logging.Logger:
    """
    Configure application-wide logging.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, output logs as structured JSON (for production).

    Returns:
        Root logger configured with the specified settings.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    if json_format:
        try:
            from pythonjsonlogger import jsonlogger

            handler = logging.StreamHandler(sys.stdout)
            formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
            handler.setFormatter(formatter)
        except ImportError:
            handler = _create_console_handler()
    else:
        handler = _create_console_handler()

    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    return root_logger


def _create_console_handler() -> logging.StreamHandler:
    """Create a formatted console handler."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s │ %(levelname)-8s │ %(name)-25s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    return handler


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a named logger for a specific module.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name or "omnisight")
