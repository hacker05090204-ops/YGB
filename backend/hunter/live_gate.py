"""Live Action Governance Gate.
Every payload sent to a real target must pass through this gate.
Auto-approves LOW risk. Requires human approval for HIGH risk.
Integrates with kill switch and authority lock.
All actions logged to audit trail."""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ygb.hunter.gate")


@dataclass
class ActionRequest:
    request_id: str
    action_type: str  # payload_test, endpoint_scan, exploit_attempt
    target_url: str
    payload_value: str
    vuln_type: str
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    requester: str
    timestamp: str
    context: dict


@dataclass
class ActionDecision:
    request_id: str
    approved: bool
    risk_level: str
    auto_approved: bool
    approver: Optional[str]
    reason: str
    timestamp: str


class LiveActionGate:
    """Governance gate for all live hunting actions.
    Prevents unauthorized or dangerous operations."""

    RISK_LEVELS = {
        # LOW risk: Auto-approve (safe probes)
        "xss": "LOW",
        "idor": "LOW",
        "open_redirect": "LOW",
        "crlf": "LOW",
        # MEDIUM risk: Auto-approve with logging
        "sqli": "MEDIUM",  # error-based only
        "path_traversal": "MEDIUM",
        # HIGH risk: Require human approval
        "ssrf": "HIGH",
        "rce": "HIGH",
        "ssti": "HIGH",
        "auth_bypass": "HIGH",
    }

    def __init__(self, audit_dir: Path = None):
        self._audit_dir = audit_dir or Path("data/ssd/evidence/gate_audit")
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._pending_approvals: dict[str, ActionRequest] = {}
        self._decisions: list[ActionDecision] = []

    def _generate_request_id(self, action: ActionRequest) -> str:
        """Generate unique request ID."""
        data = f"{action.target_url}{action.payload_value}{time.time()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _assess_risk(self, action: ActionRequest) -> str:
        """Assess risk level of an action."""
        base_risk = self.RISK_LEVELS.get(action.vuln_type, "MEDIUM")

        # Escalate risk based on payload content
        payload_lower = action.payload_value.lower()

        # Time-based attacks are higher risk
        if "sleep" in payload_lower or "waitfor" in payload_lower:
            if base_risk == "MEDIUM":
                base_risk = "HIGH"

        # SSRF to cloud metadata is CRITICAL
        if "169.254.169.254" in payload_lower or "metadata" in payload_lower:
            base_risk = "CRITICAL"

        # RCE attempts are always HIGH
        if any(
            cmd in payload_lower
            for cmd in ["exec", "eval", "system", "shell", "cmd", "bash"]
        ):
            base_risk = "HIGH"

        return base_risk

    def request_approval(
        self, action: ActionRequest, requester: str = "hunter_agent"
    ) -> ActionDecision:
        """Request approval for a live action.
        Returns decision immediately for auto-approved actions.
        For HIGH risk, creates pending approval and returns denied."""

        # Kill switch check
        from backend.governance.kill_switch import check_or_raise

        try:
            check_or_raise()
        except Exception as e:
            logger.critical("Kill switch engaged — blocking action: %s", e)
            return ActionDecision(
                request_id=action.request_id,
                approved=False,
                risk_level="BLOCKED",
                auto_approved=False,
                approver=None,
                reason="Kill switch engaged",
                timestamp=datetime.now(UTC).isoformat(),
            )

        # Authority lock check
        from backend.governance.authority_lock import AuthorityLock

        if action.action_type == "exploit_attempt":
            if not AuthorityLock.AUTO_SUBMIT:
                return ActionDecision(
                    request_id=action.request_id,
                    approved=False,
                    risk_level="BLOCKED",
                    auto_approved=False,
                    approver=None,
                    reason="Authority lock: AUTO_SUBMIT disabled",
                    timestamp=datetime.now(UTC).isoformat(),
                )

        # Assess risk
        risk = self._assess_risk(action)
        action.risk_level = risk

        # Auto-approve LOW risk
        if risk == "LOW":
            decision = ActionDecision(
                request_id=action.request_id,
                approved=True,
                risk_level=risk,
                auto_approved=True,
                approver="auto",
                reason="Low risk action auto-approved",
                timestamp=datetime.now(UTC).isoformat(),
            )
            self._log_decision(action, decision)
            return decision

        # Auto-approve MEDIUM risk with logging
        if risk == "MEDIUM":
            decision = ActionDecision(
                request_id=action.request_id,
                approved=True,
                risk_level=risk,
                auto_approved=True,
                approver="auto",
                reason="Medium risk action auto-approved with audit",
                timestamp=datetime.now(UTC).isoformat(),
            )
            self._log_decision(action, decision)
            logger.warning(
                "MEDIUM risk action auto-approved: %s → %s",
                action.vuln_type,
                action.target_url,
            )
            return decision

        # HIGH/CRITICAL risk: Require human approval
        self._pending_approvals[action.request_id] = action
        self._save_pending_approval(action)

        logger.warning(
            "HIGH risk action requires approval: %s (request_id=%s)",
            action.vuln_type,
            action.request_id,
        )

        return ActionDecision(
            request_id=action.request_id,
            approved=False,
            risk_level=risk,
            auto_approved=False,
            approver=None,
            reason=f"{risk} risk action requires human approval",
            timestamp=datetime.now(UTC).isoformat(),
        )

    def approve_pending(self, request_id: str, approver: str) -> ActionDecision:
        """Human approves a pending high-risk action."""
        if request_id not in self._pending_approvals:
            raise ValueError(f"No pending approval for request_id: {request_id}")

        action = self._pending_approvals.pop(request_id)

        decision = ActionDecision(
            request_id=request_id,
            approved=True,
            risk_level=action.risk_level,
            auto_approved=False,
            approver=approver,
            reason=f"Manually approved by {approver}",
            timestamp=datetime.now(UTC).isoformat(),
        )

        self._log_decision(action, decision)
        logger.info("Action approved by %s: %s", approver, request_id)

        return decision

    def deny_pending(self, request_id: str, approver: str, reason: str) -> ActionDecision:
        """Human denies a pending high-risk action."""
        if request_id not in self._pending_approvals:
            raise ValueError(f"No pending approval for request_id: {request_id}")

        action = self._pending_approvals.pop(request_id)

        decision = ActionDecision(
            request_id=request_id,
            approved=False,
            risk_level=action.risk_level,
            auto_approved=False,
            approver=approver,
            reason=f"Denied by {approver}: {reason}",
            timestamp=datetime.now(UTC).isoformat(),
        )

        self._log_decision(action, decision)
        logger.info("Action denied by %s: %s", approver, request_id)

        return decision

    def get_pending_approvals(self) -> list[ActionRequest]:
        """Get all pending approval requests."""
        return list(self._pending_approvals.values())

    def _save_pending_approval(self, action: ActionRequest):
        """Save pending approval to disk for human review."""
        path = self._audit_dir / f"pending_{action.request_id}.json"
        data = {
            "request_id": action.request_id,
            "action_type": action.action_type,
            "target_url": action.target_url,
            "payload_value": action.payload_value,
            "vuln_type": action.vuln_type,
            "risk_level": action.risk_level,
            "requester": action.requester,
            "timestamp": action.timestamp,
            "context": action.context,
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info("Pending approval saved: %s", path)

    def _log_decision(self, action: ActionRequest, decision: ActionDecision):
        """Log decision to audit trail."""
        self._decisions.append(decision)

        audit_entry = {
            "request_id": action.request_id,
            "action": {
                "type": action.action_type,
                "target": action.target_url,
                "vuln_type": action.vuln_type,
                "payload": action.payload_value[:100],
            },
            "decision": {
                "approved": decision.approved,
                "risk_level": decision.risk_level,
                "auto_approved": decision.auto_approved,
                "approver": decision.approver,
                "reason": decision.reason,
                "timestamp": decision.timestamp,
            },
        }

        audit_path = self._audit_dir / f"decision_{action.request_id}.json"
        audit_path.write_text(json.dumps(audit_entry, indent=2))

    def get_audit_summary(self) -> dict:
        """Get summary of all decisions."""
        total = len(self._decisions)
        approved = sum(1 for d in self._decisions if d.approved)
        auto = sum(1 for d in self._decisions if d.auto_approved)
        manual = approved - auto

        by_risk = {}
        for d in self._decisions:
            by_risk[d.risk_level] = by_risk.get(d.risk_level, 0) + 1

        return {
            "total_decisions": total,
            "approved": approved,
            "denied": total - approved,
            "auto_approved": auto,
            "manual_approved": manual,
            "by_risk_level": by_risk,
            "pending": len(self._pending_approvals),
        }
