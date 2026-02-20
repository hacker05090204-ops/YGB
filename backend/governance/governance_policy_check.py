"""
governance_policy_check.py — Policy Compliance Guard (Phase 10)

Before any report export, ALL 4 gates must pass:
1. Confirm target is in scope
2. Confirm policy accepted
3. Confirm no automated submission
4. Confirm human approval

If ANY gate fails → export is BLOCKED.
"""

import time
from typing import Dict, Any, Optional


class PolicyCheckResult:
    """Result of a policy compliance check."""

    def __init__(self):
        self.target_in_scope: bool = False
        self.policy_accepted: bool = False
        self.no_automated_submission: bool = True  # Default: no automation
        self.human_approved: bool = False
        self.checked_at: float = time.time()
        self.checked_by: Optional[str] = None

    @property
    def all_passed(self) -> bool:
        return (
            self.target_in_scope
            and self.policy_accepted
            and self.no_automated_submission
            and self.human_approved
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_in_scope": self.target_in_scope,
            "policy_accepted": self.policy_accepted,
            "no_automated_submission": self.no_automated_submission,
            "human_approved": self.human_approved,
            "all_passed": self.all_passed,
            "checked_at": self.checked_at,
            "checked_by": self.checked_by,
        }


def run_policy_check(
    target_in_scope: bool,
    policy_accepted: bool,
    no_automated_submission: bool,
    human_approved: bool,
    checked_by: str,
) -> PolicyCheckResult:
    """
    Execute the 4-gate policy compliance check.

    All parameters must be explicitly set by a human operator.
    If any gate is False, export will be blocked.
    """
    result = PolicyCheckResult()
    result.target_in_scope = target_in_scope
    result.policy_accepted = policy_accepted
    result.no_automated_submission = no_automated_submission
    result.human_approved = human_approved
    result.checked_by = checked_by
    return result


def enforce_export_policy(check: PolicyCheckResult) -> Dict[str, Any]:
    """
    Final enforcement gate before export.
    Raises PermissionError if any gate fails.
    """
    if not check.all_passed:
        failures = []
        if not check.target_in_scope:
            failures.append("target_not_in_scope")
        if not check.policy_accepted:
            failures.append("policy_not_accepted")
        if not check.no_automated_submission:
            failures.append("automated_submission_detected")
        if not check.human_approved:
            failures.append("human_approval_missing")

        raise PermissionError(
            f"EXPORT BLOCKED: Policy compliance check failed. "
            f"Failed gates: {', '.join(failures)}"
        )

    return {
        "status": "approved",
        "message": "All 4 policy gates passed. Export allowed.",
        "checked_by": check.checked_by,
        "checked_at": check.checked_at,
    }
