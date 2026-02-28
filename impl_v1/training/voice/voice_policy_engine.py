"""
Voice Policy Engine — Allowlists, denylists, and guardrails.

Evaluates whether an intent is permitted by policy before execution.
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Set, Dict

logger = logging.getLogger(__name__)


# =============================================================================
# POLICY DECISION
# =============================================================================

class PolicyVerdict(Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    REQUIRES_OVERRIDE = "REQUIRES_OVERRIDE"


@dataclass(frozen=True)
class PolicyDecision:
    """Result of a policy evaluation."""
    verdict: PolicyVerdict
    reason: str
    policy_name: str
    evaluated_at: str


# =============================================================================
# ALLOWLISTS / DENYLISTS
# =============================================================================

# Apps allowed to be launched by voice
ALLOWED_APPS: Set[str] = {
    "notepad", "notepad.exe",
    "code", "code.exe",               # VS Code
    "chrome", "chrome.exe",
    "firefox", "firefox.exe",
    "powershell", "pwsh",
    "cmd",
    "explorer", "explorer.exe",
    "calc", "calc.exe",
    "terminal", "wt", "wt.exe",       # Windows Terminal
}

# Domains allowed for download
ALLOWED_DOWNLOAD_DOMAINS: Set[str] = {
    "github.com",
    "raw.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
    "npmjs.com",
    "registry.npmjs.org",
    "crates.io",
    "static.crates.io",
    "dl.google.com",
    "releases.hashicorp.com",
}

# Filesystem paths that CANNOT be accessed
DENIED_PATHS: Set[str] = {
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "/etc",
    "/usr",
    "/sys",
    "/proc",
    "/boot",
}

# Command injection patterns
INJECTION_PATTERNS = [
    r"[;&|`$]",                 # Shell metacharacters
    r"\brm\s+-rf\b",           # Destructive commands
    r"\bdel\s+/[sfq]\b",      # Windows destructive
    r"\bformat\b",             # Format
    r"\bmkfs\b",               # Linux format
    r"\bdd\s+if=",             # dd
    r"\b(curl|wget)\s+.*\|",  # Pipe from download
    r"<script",                # XSS
]


# =============================================================================
# POLICY ENGINE
# =============================================================================

class VoicePolicyEngine:
    """Evaluates intents against security policies."""

    def __init__(self):
        self._evaluation_count = 0
        self._denied_count = 0

    def evaluate(self, command_type: str, args: Dict[str, str]) -> PolicyDecision:
        """Evaluate an intent against all policies.

        Returns PolicyDecision with verdict and reason.
        """
        self._evaluation_count += 1
        now = datetime.now(UTC).isoformat()

        # 1. Check for command injection
        full_text = " ".join([command_type] + list(args.values()))
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                self._denied_count += 1
                return PolicyDecision(
                    verdict=PolicyVerdict.DENIED,
                    reason=f"Command injection pattern detected: {pattern}",
                    policy_name="INJECTION_GUARD",
                    evaluated_at=now,
                )

        # 2. App launch policy
        if command_type in ("LAUNCH_APP", "OPEN_APP", "FOCUS_APP"):
            app_name = args.get("app", "").lower().strip()
            if app_name and app_name not in ALLOWED_APPS:
                self._denied_count += 1
                return PolicyDecision(
                    verdict=PolicyVerdict.DENIED,
                    reason=f"App '{app_name}' not in allowlist",
                    policy_name="APP_ALLOWLIST",
                    evaluated_at=now,
                )

        # 3. Download domain policy
        if command_type in ("DOWNLOAD", "DOWNLOAD_FILE"):
            url = args.get("url", "")
            if url:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if domain and domain not in ALLOWED_DOWNLOAD_DOMAINS:
                    self._denied_count += 1
                    return PolicyDecision(
                        verdict=PolicyVerdict.DENIED,
                        reason=f"Domain '{domain}' not in allowed download list",
                        policy_name="DOWNLOAD_DOMAIN_ALLOWLIST",
                        evaluated_at=now,
                    )

        # 4. Filesystem path policy
        path = args.get("path", "")
        if path:
            normalized = os.path.normpath(path)
            for denied in DENIED_PATHS:
                if normalized.lower().startswith(denied.lower()):
                    self._denied_count += 1
                    return PolicyDecision(
                        verdict=PolicyVerdict.DENIED,
                        reason=f"Path '{path}' is in denied filesystem zone",
                        policy_name="FILESYSTEM_DENYLIST",
                        evaluated_at=now,
                    )

        # 5. Critical commands always require override
        if command_type in ("SECURITY_CHANGE", "CONFIG_CHANGE"):
            return PolicyDecision(
                verdict=PolicyVerdict.REQUIRES_OVERRIDE,
                reason="Critical commands require explicit human override",
                policy_name="CRITICAL_GATE",
                evaluated_at=now,
            )

        # All checks passed
        return PolicyDecision(
            verdict=PolicyVerdict.ALLOWED,
            reason="All policy checks passed",
            policy_name="DEFAULT_ALLOW",
            evaluated_at=now,
        )

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_evaluations": self._evaluation_count,
            "total_denied": self._denied_count,
        }

    def reset(self):
        self._evaluation_count = 0
        self._denied_count = 0
