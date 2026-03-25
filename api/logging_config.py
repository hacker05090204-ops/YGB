"""Logging configuration for YGB API.

This module provides structured logging with configurable levels,
formats, and handlers for different environments.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import json


class StructuredFormatter(logging.Formatter):
    """JSON-formatted log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter."""

    # Color codes for different log levels
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for console."""
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        # Format message
        message = f"{color}[{timestamp}] {record.levelname:8s}{reset} {record.name}: {record.getMessage()}"

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            message += f"\n{self.formatException(record.exc_info)}"

        return message


def setup_logging(
    level: str = "INFO",
    json_logs: bool = False,
    log_file: Path = None,
    enable_file_logging: bool = True,
) -> None:
    """Configure logging for the YGB API application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to use JSON format (for production)
        log_file: Path to log file (default: data/logs/ygb_api.log)
        enable_file_logging: Whether to enable file logging
    """
    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if json_logs:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(console_handler)

    # File handler
    if enable_file_logging:
        if log_file is None:
            # Default log file location
            project_root = Path(__file__).parent.parent
            log_dir = project_root / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "ygb_api.log"

        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create file handler with rotation
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

    # Set level for specific loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Silence noisy loggers
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured: level={level}, json_logs={json_logs}, file_logging={enable_file_logging}"
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding extra fields to logs within a block."""

    def __init__(self, logger: logging.Logger, **extra):
        """Initialize log context.

        Args:
            logger: Logger instance
            **extra: Extra fields to add to all logs in this context
        """
        self.logger = logger
        self.extra = extra
        self.old_factory = None

    def __enter__(self):
        """Enter context and set up log factory."""
        old_factory = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.extra.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(factory)
        self.old_factory = old_factory
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original factory."""
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)


# Exception logging utilities
def log_exception(logger: logging.Logger, message: str, exc_info=True, **extra):
    """Log an exception with traceback.

    Args:
        logger: Logger instance
        message: Log message
        exc_info: Whether to include exception info
        **extra: Additional log fields
    """
    if extra:
        # Use LogContext to add extra fields
        with LogContext(logger, **extra):
            logger.error(message, exc_info=exc_info)
    else:
        logger.error(message, exc_info=exc_info)


def log_performance(
    logger: logging.Logger, operation: str, duration_ms: float, **extra
):
    """Log a performance metric.

    Args:
        logger: Logger instance
        operation: Name of the operation
        duration_ms: Duration in milliseconds
        **extra: Additional log fields
    """
    extra_fields = {
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "performance_metric": True,
        **extra,
    }

    with LogContext(logger, **extra_fields):
        if duration_ms > 1000:
            logger.warning(f"Slow operation: {operation} took {duration_ms:.2f}ms")
        elif duration_ms > 100:
            logger.info(f"Operation: {operation} took {duration_ms:.2f}ms")
        else:
            logger.debug(f"Operation: {operation} took {duration_ms:.2f}ms")


# HTTP request logging middleware
def create_request_logger():
    """Create a request logger for HTTP middleware."""
    logger = get_logger("ygb.http")

    async def log_request(request, response, duration_ms: float):
        """Log an HTTP request."""
        extra = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code
            if hasattr(response, "status_code")
            else 200,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
        }

        log_performance(
            logger, f"{request.method} {request.url.path}", duration_ms, **extra
        )

    return log_request


# Database query logging
def log_db_query(
    logger: logging.Logger, query: str, duration_ms: float, rows_affected: int = None
):
    """Log a database query.

    Args:
        logger: Logger instance
        query: SQL query string
        duration_ms: Query duration in milliseconds
        rows_affected: Number of rows affected (optional)
    """
    extra = {
        "query": query[:200] + "..." if len(query) > 200 else query,
        "duration_ms": round(duration_ms, 2),
        "db_query": True,
    }

    if rows_affected is not None:
        extra["rows_affected"] = rows_affected

    log_performance(logger, "database_query", duration_ms, **extra)
