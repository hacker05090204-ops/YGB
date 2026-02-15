"""
Phase 3: Governance Firewall for Representation Ingestion.

Enforces MODE-A only representation learning. Blocks all decision
tokens, severity fields, and exploit strings. Logs all ingestion.

GOVERNANCE:
  - MODE-A only
  - Block decision tokens
  - Block severity fields
  - Block exploit strings
  - Log all ingestion to audit_log.log
  - Reject non-sanitized input (fail-closed)
"""
import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

# ============================================================================
# LOGGING
# ============================================================================

_log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
os.makedirs(_log_dir, exist_ok=True)

_audit_logger = logging.getLogger("g38.representation_guard")
_audit_logger.setLevel(logging.INFO)
if not _audit_logger.handlers:
    _fh = logging.FileHandler(
        os.path.join(_log_dir, 'audit_log.log'), encoding='utf-8')
    _fh.setFormatter(logging.Formatter(
        '%(asctime)s [REPR-GUARD] %(message)s'))
    _audit_logger.addHandler(_fh)


# ============================================================================
# BLOCKED FIELDS AND PATTERNS
# ============================================================================

FORBIDDEN_FIELDS = frozenset([
    "valid", "accepted", "rejected", "severity", "impact",
    "cve_score", "exploit", "vulnerability", "exploit_code",
    "decision", "outcome", "verified", "platform_decision",
    "bug_label", "severity_rating", "acceptance_status",
    "critical", "high", "medium", "low", "informational",
])

DECISION_TOKENS = frozenset([
    "is_valid", "is_bug", "is_vulnerability", "severity_level",
    "accept", "reject", "verify", "confirm_bug", "mark_duplicate",
    "escalate", "triage", "classify", "score_severity",
])

EXPLOIT_PATTERNS = [
    re.compile(r"<script[^>]*>", re.IGNORECASE),
    re.compile(r"(?:union\s+select|drop\s+table|exec\s*\()", re.IGNORECASE),
    re.compile(r"(?:eval|exec|system|passthru)\s*\(", re.IGNORECASE),
    re.compile(r"\.\./\.\./", re.IGNORECASE),
    re.compile(r"(?:cmd|powershell|bash)\s+/c\s+", re.IGNORECASE),
]


# ============================================================================
# GUARD RESULT
# ============================================================================

@dataclass
class GuardResult:
    """Result of governance check on input data."""
    allowed: bool = True
    mode: str = "MODE-A"
    violations: List[str] = field(default_factory=list)
    stripped_fields: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self):
        return {
            "allowed": self.allowed,
            "mode": self.mode,
            "violations": self.violations,
            "stripped_fields": self.stripped_fields,
            "timestamp": self.timestamp,
        }


# ============================================================================
# REPRESENTATION GUARD
# ============================================================================

class RepresentationGuard:
    """Governance firewall for MODE-A representation ingestion."""

    def __init__(self, mode: str = "MODE-A"):
        if mode != "MODE-A":
            raise ValueError(
                f"RepresentationGuard: ONLY MODE-A allowed, got {mode}")
        self.mode = mode
        self._total_checked = 0
        self._total_blocked = 0
        self._total_stripped = 0

    def check_and_sanitize(self, data: dict) -> Tuple[Optional[dict], GuardResult]:
        """
        Check input data against governance rules.

        Returns:
            Tuple of (sanitized_data or None if blocked, GuardResult)
        """
        result = GuardResult(
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self._total_checked += 1

        # 1. Check for MODE-B tokens
        data_str = json.dumps(data, default=str).lower()
        if "mode-b" in data_str or "mode_b" in data_str:
            result.allowed = False
            result.violations.append("MODE-B token detected — blocked")
            self._total_blocked += 1
            _audit_logger.warning(
                f"BLOCKED: MODE-B token in input #{self._total_checked}")
            return None, result

        # 2. Check for decision tokens
        for key in _flatten_keys(data):
            key_lower = key.lower()
            if key_lower in DECISION_TOKENS:
                result.allowed = False
                result.violations.append(
                    f"Decision token '{key}' detected — blocked")
                self._total_blocked += 1
                _audit_logger.warning(
                    f"BLOCKED: Decision token '{key}' "
                    f"in input #{self._total_checked}")
                return None, result

        # 3. Check for exploit patterns in string values
        for val in _flatten_values(data):
            if isinstance(val, str):
                for pat in EXPLOIT_PATTERNS:
                    if pat.search(val):
                        result.allowed = False
                        result.violations.append(
                            f"Exploit pattern detected — blocked")
                        self._total_blocked += 1
                        _audit_logger.warning(
                            f"BLOCKED: Exploit pattern "
                            f"in input #{self._total_checked}")
                        return None, result

        # 4. Strip forbidden fields
        sanitized = _strip_forbidden(data, result)
        self._total_stripped += len(result.stripped_fields)

        # 5. Validate result is not empty
        if not sanitized:
            result.allowed = False
            result.violations.append("Empty after sanitization — blocked")
            self._total_blocked += 1
            _audit_logger.warning(
                f"BLOCKED: Empty after strip in input #{self._total_checked}")
            return None, result

        # Log successful ingestion
        _audit_logger.info(
            f"ALLOWED: input #{self._total_checked}, "
            f"stripped={len(result.stripped_fields)} fields")

        return sanitized, result

    def get_stats(self) -> dict:
        """Get guard statistics."""
        return {
            "total_checked": self._total_checked,
            "total_blocked": self._total_blocked,
            "total_stripped": self._total_stripped,
            "block_rate": (self._total_blocked / max(1, self._total_checked)),
        }


# ============================================================================
# HELPERS
# ============================================================================

def _flatten_keys(d: dict, prefix: str = "") -> List[str]:
    """Recursively extract all keys from nested dict."""
    keys = []
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        keys.append(full_key)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full_key))
    return keys


def _flatten_values(d: dict) -> list:
    """Recursively extract all values from nested dict."""
    vals = []
    for v in d.values():
        if isinstance(v, dict):
            vals.extend(_flatten_values(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    vals.extend(_flatten_values(item))
                else:
                    vals.append(item)
        else:
            vals.append(v)
    return vals


def _strip_forbidden(data: dict, result: GuardResult) -> dict:
    """Strip forbidden fields from data recursively."""
    sanitized = {}
    for k, v in data.items():
        if k.lower() in FORBIDDEN_FIELDS:
            result.stripped_fields.append(k)
            continue
        if isinstance(v, dict):
            sub = _strip_forbidden(v, result)
            if sub:
                sanitized[k] = sub
        else:
            sanitized[k] = v
    return sanitized


# ============================================================================
# SINGLETON
# ============================================================================

_guard_instance: Optional[RepresentationGuard] = None


def get_representation_guard() -> RepresentationGuard:
    """Get singleton RepresentationGuard instance."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = RepresentationGuard(mode="MODE-A")
    return _guard_instance
