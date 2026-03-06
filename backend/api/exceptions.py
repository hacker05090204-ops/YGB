"""
exceptions.py — Typed exceptions for critical API paths

Replaces broad `except Exception` swallowing with structured,
actionable error types. Each exception carries:
  - error_code: machine-readable code for frontend consumption
  - status_code: HTTP status code
  - detail: human-readable message
  - correlation_id: auto-generated UUID for log correlation

Usage:
    try:
        result = dangerous_operation()
    except StorageError as e:
        raise  # Propagated to global handler
    except ValidationError as e:
        raise  # Propagated to global handler
"""

import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger("ygb.exceptions")


class YGBError(Exception):
    """Base exception for all YGB typed errors."""

    error_code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, detail: str = "", cause: Exception = None):
        self.detail = detail or self.__class__.__doc__ or "An error occurred"
        self.correlation_id = uuid.uuid4().hex[:12]
        self.cause = cause
        self.timestamp = datetime.now(timezone.utc).isoformat()
        super().__init__(self.detail)

    def to_response(self) -> dict:
        """Structured error response for API consumers."""
        return {
            "error": self.error_code,
            "detail": self.detail,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }

    def log(self):
        """Log with correlation ID for traceability."""
        logger.error(
            "[%s] %s: %s (cause=%s)",
            self.correlation_id,
            self.error_code,
            self.detail,
            type(self.cause).__name__ if self.cause else "none",
            exc_info=self.cause,
        )


class StorageError(YGBError):
    """Storage engine is unavailable or returned an error."""
    error_code = "STORAGE_ERROR"
    status_code = 503


class TrainingError(YGBError):
    """Training subsystem error."""
    error_code = "TRAINING_ERROR"
    status_code = 503


class TelemetryError(YGBError):
    """Telemetry data unavailable or corrupted."""
    error_code = "TELEMETRY_ERROR"
    status_code = 503


class ValidationError(YGBError):
    """Request validation failed."""
    error_code = "VALIDATION_ERROR"
    status_code = 400


class WorkflowError(YGBError):
    """Workflow execution failed."""
    error_code = "WORKFLOW_ERROR"
    status_code = 500


class ConfigurationError(YGBError):
    """Required configuration is missing or invalid."""
    error_code = "CONFIG_ERROR"
    status_code = 500


class ExternalServiceError(YGBError):
    """An external service (GitHub, GeoIP, etc.) is unavailable."""
    error_code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502
