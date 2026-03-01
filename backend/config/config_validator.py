"""
Centralized Configuration Validator — Fail-Closed Secret Validation

Validates all required secrets at startup. Raises ConfigurationError with
a clear list of missing/invalid keys.  NEVER prints actual secret values.

Usage:
    from backend.config.config_validator import validate_config
    validate_config()  # Call at startup before accepting requests
"""

import os
import logging
from typing import List, Tuple

logger = logging.getLogger("ygb.config_validator")


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid.

    Attributes:
        violations: List of (key_name, reason) tuples
    """
    def __init__(self, violations: List[Tuple[str, str]]):
        self.violations = violations
        summary = "; ".join(f"{k}: {r}" for k, r in violations)
        super().__init__(f"Configuration validation failed — {summary}")


# =========================================================================
# PLACEHOLDER DETECTION
# =========================================================================

_PLACEHOLDER_PATTERNS = [
    "change-me", "change_me", "changeme", "replace-me", "replace_me",
    "your-secret", "your_secret", "example", "placeholder",
    "CHANGE_ME", "REPLACE_ME", "YOUR_SECRET",
]


def _is_placeholder(value: str) -> bool:
    """Check if a value looks like a placeholder rather than a real secret."""
    lower = value.lower()
    return any(p.lower() in lower for p in _PLACEHOLDER_PATTERNS)


# =========================================================================
# REQUIRED SECRETS
# =========================================================================

# (env_var_name, min_length, description)
REQUIRED_SECRETS = [
    ("JWT_SECRET", 32, "JWT signing secret"),
    ("YGB_HMAC_SECRET", 32, "HMAC telemetry secret"),
    ("YGB_VIDEO_JWT_SECRET", 32, "Video streamer JWT secret"),
]

# These are required only in CONNECTED profile
CONNECTED_ONLY_SECRETS = [
    ("GITHUB_CLIENT_SECRET", 8, "GitHub OAuth client secret"),
    ("SMTP_PASS", 4, "SMTP email password"),
]


def validate_required_secrets() -> List[Tuple[str, str]]:
    """
    Validate that all required secrets are present, long enough, and not
    placeholder values.

    Returns: list of (key, reason) violations.  Empty list = all OK.
    """
    violations = []
    profile = os.environ.get("YGB_PROFILE", "").upper()

    secrets_to_check = list(REQUIRED_SECRETS)
    if profile == "CONNECTED":
        secrets_to_check.extend(CONNECTED_ONLY_SECRETS)

    for env_name, min_len, desc in secrets_to_check:
        value = os.environ.get(env_name, "")
        if not value:
            violations.append((env_name, f"Missing — {desc} is required"))
        elif len(value) < min_len:
            violations.append((
                env_name,
                f"Too short ({len(value)} chars, need ≥{min_len}) — {desc}"
            ))
        elif _is_placeholder(value):
            violations.append((
                env_name,
                f"Contains placeholder pattern — generate a real secret"
            ))

    return violations


# =========================================================================
# BIND HOST VALIDATION
# =========================================================================

def validate_bind_host() -> List[Tuple[str, str]]:
    """
    Warn if API_HOST is set to 0.0.0.0 (binds to all interfaces).
    Returns list of warnings (not fatal).
    """
    warnings = []
    host = os.environ.get("API_HOST", "127.0.0.1")
    if host == "0.0.0.0":
        warnings.append((
            "API_HOST",
            "Bound to 0.0.0.0 — exposes service on all network interfaces. "
            "Use 127.0.0.1 for local-only access."
        ))
    return warnings


# =========================================================================
# UNIFIED VALIDATOR
# =========================================================================

def validate_config(strict: bool = True):
    """
    Run all configuration checks.

    Args:
        strict: If True, raise ConfigurationError on secret violations.
                If False, log warnings only.

    Raises:
        ConfigurationError: If strict=True and violations found.
    """
    secret_violations = validate_required_secrets()
    bind_warnings = validate_bind_host()

    # Log bind warnings (never fatal)
    for key, reason in bind_warnings:
        logger.warning("[CONFIG] %s: %s", key, reason)

    if secret_violations:
        for key, reason in secret_violations:
            logger.error("[CONFIG] %s: %s", key, reason)
        if strict:
            raise ConfigurationError(secret_violations)

    logger.info("[CONFIG] All required configuration validated OK")
