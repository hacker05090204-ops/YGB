"""
YGB Activation Profiles — Startup Validation & Integration Configuration

Two explicit profiles:
  PRIVACY  — integrations intentionally disabled, local-only operation
  CONNECTED — integrations required, fail-fast on missing credentials

Enforces strong non-empty secrets at startup for BOTH profiles.
In CONNECTED mode, additionally requires all integration credentials.
"""

import os
import sys
import logging
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("ygb.activation")

# =============================================================================
# PROFILE ENUM
# =============================================================================

class ActivationProfile(Enum):
    PRIVACY = "PRIVACY"       # Integrations intentionally disabled
    CONNECTED = "CONNECTED"   # Integrations required


# =============================================================================
# INTEGRATION STATUS
# =============================================================================

class IntegrationState(Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"


@dataclass
class IntegrationStatus:
    name: str
    state: IntegrationState
    reason: str


# =============================================================================
# SMTP KEY UNIFICATION
# =============================================================================

def get_smtp_pass() -> str:
    """Read SMTP password with unified key resolution.

    Canonical key: SMTP_PASS
    Backward-compat fallback: SMTP_PASSWORD
    """
    val = os.environ.get("SMTP_PASS", "")
    if not val:
        val = os.environ.get("SMTP_PASSWORD", "")
    return val


# =============================================================================
# VALIDATION
# =============================================================================

def _check_secret(name: str, min_length: int = 32) -> Tuple[bool, str]:
    """Check a secret is present and strong enough."""
    val = os.environ.get(name, "")
    if not val:
        return False, f"{name} is not set"
    if len(val) < min_length:
        return False, f"{name} is too short ({len(val)} chars, min {min_length})"
    return True, f"{name} OK ({len(val)} chars)"


def _check_env(name: str) -> Tuple[bool, str]:
    """Check an env var is present and non-empty."""
    val = os.environ.get(name, "")
    if not val:
        return False, f"{name} is not set"
    return True, f"{name} configured"


def get_profile() -> ActivationProfile:
    """Get the activation profile from environment."""
    raw = os.environ.get("YGB_PROFILE", "PRIVACY").upper()
    try:
        return ActivationProfile(raw)
    except ValueError:
        logger.warning(f"Unknown YGB_PROFILE='{raw}', defaulting to PRIVACY")
        return ActivationProfile.PRIVACY


def validate_startup() -> Tuple[bool, List[str], List[IntegrationStatus]]:
    """Validate startup configuration.

    Returns:
        (ok, errors, integration_statuses)
        ok = False means server should NOT start (critical secrets missing)
    """
    profile = get_profile()
    errors: List[str] = []
    warnings: List[str] = []
    integrations: List[IntegrationStatus] = []

    # ----- MANDATORY SECRETS (both profiles) -----
    for secret_name in ["JWT_SECRET", "YGB_HMAC_SECRET", "YGB_VIDEO_JWT_SECRET"]:
        ok, msg = _check_secret(secret_name)
        if not ok:
            errors.append(msg)

    # ----- GITHUB AUTH -----
    gh_id_ok, _ = _check_env("GITHUB_CLIENT_ID")
    gh_secret_ok, _ = _check_env("GITHUB_CLIENT_SECRET")
    gh_redir_ok, _ = _check_env("GITHUB_REDIRECT_URI")
    if gh_id_ok and gh_secret_ok:
        integrations.append(IntegrationStatus(
            "github_auth", IntegrationState.ENABLED, "GitHub OAuth configured"
        ))
    elif profile == ActivationProfile.CONNECTED:
        missing = []
        if not gh_id_ok: missing.append("GITHUB_CLIENT_ID")
        if not gh_secret_ok: missing.append("GITHUB_CLIENT_SECRET")
        if not gh_redir_ok: missing.append("GITHUB_REDIRECT_URI")
        errors.append(f"CONNECTED mode requires GitHub OAuth: missing {', '.join(missing)}")
        integrations.append(IntegrationStatus(
            "github_auth", IntegrationState.BLOCKED,
            f"Missing: {', '.join(missing)}"
        ))
    else:
        integrations.append(IntegrationStatus(
            "github_auth", IntegrationState.DISABLED,
            "PRIVACY mode — GitHub auth disabled"
        ))

    # ----- SMTP / EMAIL ALERTS -----
    smtp_host_ok, _ = _check_env("SMTP_HOST")
    smtp_user_ok, _ = _check_env("SMTP_USER")
    smtp_pass_val = get_smtp_pass()
    smtp_pass_ok = bool(smtp_pass_val)
    email_to_ok, _ = _check_env("ALERT_EMAIL_TO")
    email_from_ok, _ = _check_env("ALERT_EMAIL_FROM")

    if smtp_host_ok and smtp_user_ok and smtp_pass_ok and email_to_ok:
        integrations.append(IntegrationStatus(
            "smtp_alerts", IntegrationState.ENABLED, "SMTP alerts configured"
        ))
    elif profile == ActivationProfile.CONNECTED:
        missing = []
        if not smtp_host_ok: missing.append("SMTP_HOST")
        if not smtp_user_ok: missing.append("SMTP_USER")
        if not smtp_pass_ok: missing.append("SMTP_PASS (or SMTP_PASSWORD)")
        if not email_to_ok: missing.append("ALERT_EMAIL_TO")
        if not email_from_ok: missing.append("ALERT_EMAIL_FROM")
        errors.append(f"CONNECTED mode requires SMTP: missing {', '.join(missing)}")
        integrations.append(IntegrationStatus(
            "smtp_alerts", IntegrationState.BLOCKED,
            f"Missing: {', '.join(missing)}"
        ))
    else:
        integrations.append(IntegrationStatus(
            "smtp_alerts", IntegrationState.DISABLED,
            "PRIVACY mode — SMTP not configured, alerts logged only"
        ))

    # ----- CVE API -----
    cve_ok, _ = _check_env("CVE_API_KEY")
    if cve_ok:
        integrations.append(IntegrationStatus(
            "cve_api", IntegrationState.ENABLED, "CVE API key configured"
        ))
    elif profile == ActivationProfile.CONNECTED:
        # CVE is optional even in connected mode (free feeds exist)
        integrations.append(IntegrationStatus(
            "cve_api", IntegrationState.DISABLED,
            "CVE_API_KEY not set — using free public feeds only"
        ))
    else:
        integrations.append(IntegrationStatus(
            "cve_api", IntegrationState.DISABLED,
            "CVE API not configured"
        ))

    # ----- ACCELERATOR -----
    accel_ok, _ = _check_env("ACCELERATOR_API_URL")
    if accel_ok:
        integrations.append(IntegrationStatus(
            "accelerator", IntegrationState.ENABLED, "Accelerator API configured"
        ))
    else:
        integrations.append(IntegrationStatus(
            "accelerator", IntegrationState.DISABLED,
            "ACCELERATOR_API_URL not set"
        ))

    # ----- GOOGLE DRIVE BACKUP -----
    gdrive_ok, _ = _check_env("GOOGLE_DRIVE_CREDENTIALS")
    if gdrive_ok:
        integrations.append(IntegrationStatus(
            "google_drive_backup", IntegrationState.ENABLED,
            "Google Drive credentials configured"
        ))
    else:
        integrations.append(IntegrationStatus(
            "google_drive_backup", IntegrationState.DISABLED,
            "GOOGLE_DRIVE_CREDENTIALS not set"
        ))

    ok = len(errors) == 0
    return ok, errors, integrations


def log_boot_summary(
    ok: bool,
    errors: List[str],
    integrations: List[IntegrationStatus],
) -> str:
    """Log and return boot summary string."""
    profile = get_profile()
    lines = [
        f"╔══════════════════════════════════════════╗",
        f"║  YGB Boot Summary — Profile: {profile.value:<11}║",
        f"╠══════════════════════════════════════════╣",
    ]

    if errors:
        lines.append(f"║  ❌ STARTUP BLOCKED — {len(errors)} error(s)         ║")
        for e in errors:
            lines.append(f"║  • {e[:38]:<38}║")
    else:
        lines.append(f"║  ✅ STARTUP OK                           ║")

    lines.append(f"╠══════════════════════════════════════════╣")
    lines.append(f"║  Integrations:                           ║")

    for i in integrations:
        icon = {"ENABLED": "🟢", "DISABLED": "⚪", "BLOCKED": "🔴"}[i.state.value]
        label = f"{icon} {i.name}: {i.state.value}"
        lines.append(f"║  {label:<40}║")

    lines.append(f"╚══════════════════════════════════════════╝")

    summary = "\n".join(lines)
    if ok:
        logger.info(f"\n{summary}")
    else:
        logger.error(f"\n{summary}")
    print(summary)
    return summary
