"""
log_config.py — Structured logging configuration

Provides JSON-structured logging with correlation IDs, redacted secrets,
and consistent format across all YGB modules.

Addresses:
  - Risk 15 (Observability): no structured log format
  - Risk 4 (Security): secrets could leak into log output
"""

import logging
import json
import re
import os
from datetime import datetime, timezone
from typing import Optional


# Patterns that should NEVER appear in logs
_SECRET_PATTERNS = re.compile(
    r'(password|secret|token|api_key|private_key|authorization|cookie)'
    r'\s*[=:]\s*\S+',
    re.IGNORECASE,
)

_REDACTION_MARKER = "[REDACTED]"


def _redact(message: str) -> str:
    """Strip secret values from log messages."""
    return _SECRET_PATTERNS.sub(
        lambda m: m.group(0).split("=")[0] + "=" + _REDACTION_MARKER
        if "=" in m.group(0)
        else m.group(0).split(":")[0] + ": " + _REDACTION_MARKER,
        message,
    )


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter with secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        message = _redact(message)

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": message,
            "file": f"{record.filename}:{record.lineno}",
        }

        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            entry["cid"] = record.correlation_id

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
            entry["error_type"] = type(record.exc_info[1]).__name__

        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO", structured: bool = True):
    """Configure application-wide logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        structured: If True, use JSON format. If False, use human-readable.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler()

    if structured and os.getenv("YGB_LOG_FORMAT", "structured") == "structured":
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
