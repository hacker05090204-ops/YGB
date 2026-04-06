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
import hashlib
import json
from typing import List, Optional, Tuple

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


class ConfigValidationError(ValueError):
    """Raised when an explicit config mapping is missing required fields."""


class ConfigDriftDetector:
    """Detect configuration drift using a stable JSON hash."""

    _baseline_hash: Optional[str] = None

    def snapshot(self, config: dict) -> str:
        """Return a deterministic SHA-256 hash for the provided config mapping."""
        payload = json.dumps(config, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def check_drift(self, config: dict) -> bool:
        """Return True when config differs from the captured baseline hash."""
        current_hash = self.snapshot(config)
        if self._baseline_hash is None:
            self._baseline_hash = current_hash
            return False
        if current_hash != self._baseline_hash:
            logger.critical(
                "[CONFIG] Configuration drift detected: baseline=%s current=%s",
                self._baseline_hash,
                current_hash,
            )
            return True
        return False


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

REQUIRED_FIELDS: list[str] = []

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

REQUIRED_FIELDS.extend([env_name for env_name, _, _ in REQUIRED_SECRETS])


def _expected_required_fields(config: Optional[dict] = None) -> list[str]:
    """Return required fields for the provided config mapping."""
    required_fields = list(REQUIRED_FIELDS)
    profile = ""
    if isinstance(config, dict):
        profile = str(config.get("YGB_PROFILE", "")).upper()
    if profile == "CONNECTED":
        required_fields.extend([env_name for env_name, _, _ in CONNECTED_ONLY_SECRETS])
    return required_fields


def validate_required_fields(config: dict) -> None:
    """Validate that an explicit config mapping contains all required fields."""
    for field in _expected_required_fields(config):
        value = config.get(field) if isinstance(config, dict) else None
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ConfigValidationError(f"Missing required config field: {field}")


def validate_required_secrets_from_config(config: dict) -> List[Tuple[str, str]]:
    """Validate required secrets from a supplied config mapping."""
    violations = []
    profile = str(config.get("YGB_PROFILE", "")).upper()

    secrets_to_check = list(REQUIRED_SECRETS)
    if profile == "CONNECTED":
        secrets_to_check.extend(CONNECTED_ONLY_SECRETS)

    for env_name, min_len, desc in secrets_to_check:
        raw_value = config.get(env_name, "")
        value = "" if raw_value is None else str(raw_value)
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


def validate_bind_host_from_config(config: dict) -> List[Tuple[str, str]]:
    """Warn if API_HOST from an explicit config mapping exposes all interfaces."""
    warnings = []
    host = str(config.get("API_HOST", "127.0.0.1"))
    if host == "0.0.0.0":
        warnings.append((
            "API_HOST",
            "Bound to 0.0.0.0 — exposes service on all network interfaces. "
            "Use 127.0.0.1 for local-only access."
        ))
    return warnings


_drift_detector = ConfigDriftDetector()


# =========================================================================
# UNIFIED VALIDATOR
# =========================================================================

def validate_config(strict: bool = True, config: Optional[dict] = None):
    """
    Run all configuration checks.

    Args:
        strict: If True, raise ConfigurationError on secret violations.
                If False, log warnings only.
        config: Optional config mapping to validate instead of environment values.

    Raises:
        ConfigurationError: If strict=True and violations found.
        ConfigValidationError: If explicit config mapping is missing required fields.
    """
    if config is not None:
        validate_required_fields(config)
        _drift_detector.check_drift(config)
        secret_violations = validate_required_secrets_from_config(config)
        bind_warnings = validate_bind_host_from_config(config)
    else:
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
