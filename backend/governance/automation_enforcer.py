"""
automation_enforcer.py — Python Governance Bridge for Hunting System

IMMUTABLE RULES:
    - No auto-submission to any platform
    - No authority unlock
    - No scope expansion without user approval
    - All actions audit-logged
    - Severity labeling locked (user-assigned only)
"""

import time
import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


# =========================================================================
# TYPES
# =========================================================================

class ActionType(Enum):
    SCOPE_CHECK = "SCOPE_CHECK"
    TARGET_SELECT = "TARGET_SELECT"
    HUNT_START = "HUNT_START"
    HUNT_STEP = "HUNT_STEP"
    EVIDENCE_CAPTURE = "EVIDENCE_CAPTURE"
    REPORT_BUILD = "REPORT_BUILD"
    REPORT_EXPORT = "REPORT_EXPORT"
    SUBMISSION_ATTEMPT = "SUBMISSION_ATTEMPT"
    AUTHORITY_REQUEST = "AUTHORITY_REQUEST"
    MODE_CHANGE = "MODE_CHANGE"
    VOICE_COMMAND = "VOICE_COMMAND"


class ActionResult(Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    LOGGED_ONLY = "LOGGED_ONLY"


@dataclass
class AuditEntry:
    sequence: int
    timestamp: str
    action: ActionType
    result: ActionResult
    actor: str
    description: str
    governance_approved: bool
    hash: str = ""


# =========================================================================
# AUTOMATION ENFORCER
# =========================================================================

class AutomationEnforcer:
    """Python bridge for governance enforcement. Mirrors C++ AutomationGuard."""

    # IMMUTABLE CONSTANTS
    CAN_AUTO_SUBMIT: bool = False
    CAN_UNLOCK_AUTHORITY: bool = False
    CAN_MODIFY_SEVERITY: bool = False
    CAN_BYPASS_APPROVAL: bool = False
    CAN_SCRAPE_BEYOND_SCOPE: bool = False

    def __init__(self) -> None:
        self._audit_log: List[AuditEntry] = []
        self._blocked_count: int = 0

    # =======================================================================
    # AUDIT LOGGING
    # =======================================================================

    def _log(self, action: ActionType, result: ActionResult,
             actor: str, description: str,
             approved: bool) -> ActionResult:
        entry = AuditEntry(
            sequence=len(self._audit_log),
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            result=result,
            actor=actor,
            description=description,
            governance_approved=approved,
        )
        # Hash the entry for integrity
        raw = f"{entry.sequence}|{entry.timestamp}|{entry.action.value}|{entry.description}"
        entry.hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._audit_log.append(entry)
        if result == ActionResult.BLOCKED:
            self._blocked_count += 1
        return result

    # =======================================================================
    # SUBMISSION BLOCKING
    # =======================================================================

    def block_submission(self, platform: str, report_id: str) -> ActionResult:
        """ALWAYS blocks. No auto-submission to any platform."""
        desc = f"BLOCKED: Auto-submission to '{platform}' for report '{report_id}'"
        return self._log(ActionType.SUBMISSION_ATTEMPT, ActionResult.BLOCKED,
                         "system", desc, False)

    def block_authority_unlock(self, authority_type: str) -> ActionResult:
        """ALWAYS blocks. Authority cannot be unlocked."""
        desc = f"BLOCKED: Authority unlock '{authority_type}'"
        return self._log(ActionType.AUTHORITY_REQUEST, ActionResult.BLOCKED,
                         "system", desc, False)

    # =======================================================================
    # PRE-ACTION VALIDATION
    # =======================================================================

    def validate_target_selection(self, domain: str,
                                  user_approved: bool) -> ActionResult:
        if not user_approved:
            return self._log(ActionType.TARGET_SELECT, ActionResult.BLOCKED,
                             "system",
                             f"BLOCKED: Target '{domain}' not user-approved",
                             False)
        return self._log(ActionType.TARGET_SELECT, ActionResult.ALLOWED,
                         "user", f"Target '{domain}' approved by user", True)

    def validate_report_export(self, report_id: str,
                               user_approved: bool) -> ActionResult:
        if not user_approved:
            return self._log(ActionType.REPORT_EXPORT, ActionResult.BLOCKED,
                             "system",
                             f"BLOCKED: Export '{report_id}' requires approval",
                             False)
        return self._log(ActionType.REPORT_EXPORT, ActionResult.ALLOWED,
                         "user",
                         f"Report '{report_id}' export approved", True)

    def validate_hunt_start(self, target: str, scope_set: bool,
                            user_approved: bool) -> ActionResult:
        if not scope_set:
            return self._log(ActionType.HUNT_START, ActionResult.BLOCKED,
                             "system",
                             f"BLOCKED: No scope set for target '{target}'",
                             False)
        if not user_approved:
            return self._log(ActionType.HUNT_START, ActionResult.BLOCKED,
                             "system",
                             f"BLOCKED: Hunt not user-approved for '{target}'",
                             False)
        return self._log(ActionType.HUNT_START, ActionResult.ALLOWED,
                         "user",
                         f"Hunt started for '{target}' with approved scope",
                         True)

    def log_hunt_step(self, step_desc: str) -> ActionResult:
        return self._log(ActionType.HUNT_STEP, ActionResult.LOGGED_ONLY,
                         "system", step_desc, True)

    def log_evidence(self, evidence_type: str, hash_val: str) -> ActionResult:
        desc = f"Evidence: {evidence_type} (hash: {hash_val[:16]})"
        return self._log(ActionType.EVIDENCE_CAPTURE, ActionResult.ALLOWED,
                         "system", desc, True)

    def log_voice_command(self, command: str) -> ActionResult:
        return self._log(ActionType.VOICE_COMMAND, ActionResult.LOGGED_ONLY,
                         "user", f"Voice: {command}", True)

    # =======================================================================
    # QUERY
    # =======================================================================

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return [asdict(e) for e in self._audit_log]

    @property
    def total_actions(self) -> int:
        return len(self._audit_log)

    @property
    def blocked_count(self) -> int:
        return self._blocked_count

    @property
    def allowed_count(self) -> int:
        return sum(1 for e in self._audit_log
                   if e.result == ActionResult.ALLOWED)
