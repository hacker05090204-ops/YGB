"""
Standardized Error Taxonomy for YGB API

Provides:
- Public-safe error types (returned to clients)
- Internal error logging helpers (stay server-side)
- Correlation ID generation for debugging
- Standard error response format

Usage:
    from backend.errors import api_error, ErrorCode
    raise api_error(ErrorCode.VALIDATION, "Title is required")
"""

import secrets
import logging
from enum import Enum
from typing import Optional, Dict, Any

from fastapi import HTTPException

logger = logging.getLogger("ygb.errors")


class ErrorCode(str, Enum):
    """Public-safe error codes returned to API clients."""
    VALIDATION = "VALIDATION_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID = "AUTH_INVALID"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL = "INTERNAL_SERVER_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# Maps ErrorCode to HTTP status codes
_STATUS_MAP = {
    ErrorCode.VALIDATION: 400,
    ErrorCode.AUTH_REQUIRED: 401,
    ErrorCode.AUTH_INVALID: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL: 500,
    ErrorCode.NOT_IMPLEMENTED: 501,
}


def api_error(
    code: ErrorCode,
    detail: str,
    *,
    status_code: Optional[int] = None,
    correlation_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> HTTPException:
    """
    Create a standardized HTTPException with consistent error format.

    Returns a structure safe for API clients:
    {
        "error": "VALIDATION_ERROR",
        "detail": "Title is required",
        "correlation_id": "abc123..."
    }

    Internal details are NEVER included in the response.
    """
    cid = correlation_id or secrets.token_hex(8)
    http_status = status_code or _STATUS_MAP.get(code, 500)

    body: Dict[str, Any] = {
        "error": code.value,
        "detail": detail,
        "correlation_id": cid,
    }

    if extra:
        body.update(extra)

    return HTTPException(status_code=http_status, detail=body)


def log_internal_error(
    exc: Exception,
    *,
    context: str = "",
    correlation_id: Optional[str] = None,
) -> str:
    """
    Log full exception details server-side and return a correlation ID.
    The correlation ID is safe to return to the client for debugging.
    """
    import traceback

    cid = correlation_id or secrets.token_hex(8)
    logger.error(
        "Internal error [%s] %s: %s\n%s",
        cid,
        context,
        str(exc),
        traceback.format_exc(),
    )
    return cid


def internal_error(
    exc: Exception,
    *,
    context: str = "",
) -> HTTPException:
    """
    Log the full exception server-side and return a sanitized 500 to the client.
    Combines log_internal_error + api_error.
    """
    cid = log_internal_error(exc, context=context)
    return api_error(
        ErrorCode.INTERNAL,
        "An unexpected error occurred. Contact support with the correlation ID.",
        correlation_id=cid,
    )
