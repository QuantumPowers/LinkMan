"""
Logging utilities for LinkMan.

Provides structured logging with:
- Console and file output
- Rotation support
- JSON format option
- GUI integration
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO, Callable, List, Optional

from loguru import logger


# GUI log handlers
_gui_log_handlers: List[Callable[[str, str], None]] = []


def add_gui_log_handler(handler: Callable[[str, str], None]) -> None:
    """
    Add a GUI log handler that will receive log messages.

    Args:
        handler: A function that takes (message, level) as arguments
    """
    _gui_log_handlers.append(handler)


def remove_gui_log_handler(handler: Callable[[str, str], None]) -> None:
    """
    Remove a GUI log handler.

    Args:
        handler: The handler to remove
    """
    if handler in _gui_log_handlers:
        _gui_log_handlers.remove(handler)


def sanitize_log_message(message: str) -> str:
    """
    Sanitize log message to remove sensitive information.

    Args:
        message: Original log message

    Returns:
        Sanitized log message
    """
    import re
    
    # Sanitize IP addresses (partial masking)
    message = re.sub(r'(\d+\.\d+\.\d+)\.\d+', r'\1.xxx', message)
    
    # Sanitize domain names (partial masking)
    message = re.sub(r'([a-zA-Z0-9-]+)\.([a-zA-Z]{2,})', r'xxx.\2', message)
    
    # Sanitize keys and tokens
    message = re.sub(r'(key|token|secret|password)[:=]\s*[\"\']?([a-zA-Z0-9+/=]+)[\"\']?', r'\1=***', message)
    
    # Sanitize ports (mask non-standard ports)
    message = re.sub(r':(\d{4,})', r':xxxx', message)
    
    return message


def setup_logger(
    level: str = "INFO",
    log_dir: str | None = None,
    max_size_mb: int = 10,
    backup_count: int = 5,
    format_str: str = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
    json_format: bool = False,
) -> None:
    """
    Configure the application logger with categorized logs.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Optional log directory path (default: ./logs)
        max_size_mb: Maximum log file size in MB
        backup_count: Number of backup files to keep
        format_str: Log format string
        json_format: Use JSON format for structured logging
    """
    logger.remove()

    console_format = format_str
    if json_format:
        console_format = "{{\"time\": \"{time:YYYY-MM-DD HH:mm:ss}\", \"level\": \"{level}\", \"name\": \"{name}\", \"message\": \"{message}\"}}"

    # Console output with sanitization
    def console_sink(message):
        sanitized = sanitize_log_message(message)
        sys.stderr.write(sanitized)
        sys.stderr.flush()

    logger.add(
        console_sink,
        format=console_format,
        level=level,
        colorize=True,
    )

    # GUI log handler
    def gui_log_handler(message):
        """Handler for GUI log messages."""
        # Sanitize message
        sanitized_message = sanitize_log_message(message)
        # Extract level from the message
        import re
        match = re.search(r'\|\s*(\w+)\s*\|', sanitized_message)
        level = match.group(1) if match else "INFO"
        for handler in _gui_log_handlers:
            try:
                handler(sanitized_message, level)
            except Exception:
                pass

    logger.add(
        gui_log_handler,
        format=console_format,
        level=level,
    )

    if log_dir:
        log_path = Path(log_dir)
    else:
        log_path = Path("./logs")
    
    # Create log directory structure
    log_path.mkdir(parents=True, exist_ok=True)
    (log_path / "app").mkdir(exist_ok=True)
    (log_path / "traffic").mkdir(exist_ok=True)
    (log_path / "debug").mkdir(exist_ok=True)

    file_format = format_str
    if json_format:
        file_format = "{{\"time\": \"{time:YYYY-MM-DD HH:mm:ss}\", \"level\": \"{level}\", \"name\": \"{name}\", \"message\": \"{message}\"}}"

    # File log sink with sanitization
    def file_sink(log_path):
        def sink(message):
            sanitized = sanitize_log_message(message)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(sanitized)
        return sink

    # Main application log
    app_log_path = str(log_path / "app" / "app.log")
    logger.add(
        file_sink(app_log_path),
        format=file_format,
        level=level,
        rotation=f"{max_size_mb} MB",
        retention=backup_count,
        compression="gz",
    )

    # Traffic log (for network requests/responses)
    traffic_log_path = str(log_path / "traffic" / "traffic.log")
    logger.add(
        file_sink(traffic_log_path),
        format=file_format,
        level="INFO",
        rotation=f"{max_size_mb * 2} MB",
        retention=backup_count,
        compression="gz",
        filter=lambda record: "traffic" in record["extra"] or "request" in record["extra"]
    )

    # Debug log (for detailed debugging)
    debug_log_path = str(log_path / "debug" / "debug.log")
    logger.add(
        file_sink(debug_log_path),
        format=file_format,
        level="DEBUG",
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
