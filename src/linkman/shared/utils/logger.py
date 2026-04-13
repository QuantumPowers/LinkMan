"""
Logging utilities for LinkMan.

Provides structured logging with:
- Console and file output
- Rotation support
- JSON format option
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from loguru import logger


def setup_logger(
    level: str = "INFO",
    log_file: str | None = None,
    max_size_mb: int = 10,
    backup_count: int = 5,
    format_str: str = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    json_format: bool = False,
) -> None:
    """
    Configure the application logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        max_size_mb: Maximum log file size in MB
        backup_count: Number of backup files to keep
        format_str: Log format string
        json_format: Use JSON format for structured logging
    """
    logger.remove()

    console_format = format_str
    if json_format:
        console_format = "{{\"time\": \"{time:YYYY-MM-DD HH:mm:ss}\", \"level\": \"{level}\", \"message\": \"{message}\"}}"

    logger.add(
        sys.stderr,
        format=console_format,
        level=level,
        colorize=True,
    )

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_format = format_str
        if json_format:
            file_format = "{{\"time\": \"{time:YYYY-MM-DD HH:mm:ss}\", \"level\": \"{level}\", \"message\": \"{message}\"}}"

        logger.add(
            log_file,
            format=file_format,
            level=level,
            rotation=f"{max_size_mb} MB",
            retention=backup_count,
            compression="gz",
        )


def get_logger(name: str | None = None) -> "Logger":
    """
    Get a logger instance.

    Args:
        name: Optional logger name for context

    Returns:
        Logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger


class LoggerAdapter:
    """Adapter for compatibility with standard logging interface."""

    def __init__(self, name: str):
        self._logger = logger.bind(name=name)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        self._logger.exception(msg, *args, **kwargs)
