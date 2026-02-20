"""
report_draft_assistant.py — Report Drafting Assistant (Phase 5)

Generates structured report drafts for human review.
Does NOT auto-submit. Does NOT negotiate automatically.
Requires manual approval before any export.
"""

import time
from typing import Optional, Dict, Any

# Global enforcement flag — NEVER set to False
REQUIRES_MANUAL_SUBMIT = True


class ReportDraft:
    """Structured vulnerability report draft."""

    def __init__(self):
        self.summary: str = ""
        self.impact: str = ""
        self.reproduction_steps: str = ""
        self.evidence: str = ""
        self.suggested_fix: str = ""
        self.target_id: str = ""
        self.severity: str = ""
        self.created_at: float = time.time()
        self.approved_by: Optional[str] = None
        self.approved_at: Optional[float] = None
        self.requires_manual_submit: bool = REQUIRES_MANUAL_SUBMIT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "impact": self.impact,
            "reproduction_steps": self.reproduction_steps,
            "evidence": self.evidence,
            "suggested_fix": self.suggested_fix,
            "target_id": self.target_id,
            "severity": self.severity,
            "created_at": self.created_at,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "requires_manual_submit": self.requires_manual_submit,
            "export_allowed": self.is_export_allowed(),
        }

    def is_export_allowed(self) -> bool:
        """Export is ONLY allowed if manually approved by a human."""
        if not REQUIRES_MANUAL_SUBMIT:
            return False  # Fail-safe: if flag was somehow disabled, block export
        return self.approved_by is not None and self.approved_at is not None

    def approve(self, approver_name: str):
        """Human manually approves the report for export."""
        self.approved_by = approver_name
        self.approved_at = time.time()


def create_draft(
    target_id: str,
    summary: str,
    impact: str,
    reproduction_steps: str,
    evidence: str,
    suggested_fix: str,
    severity: str = "medium",
) -> ReportDraft:
    """Create a new report draft. Does NOT submit anything."""
    draft = ReportDraft()
    draft.target_id = target_id
    draft.summary = summary
    draft.impact = impact
    draft.reproduction_steps = reproduction_steps
    draft.evidence = evidence
    draft.suggested_fix = suggested_fix
    draft.severity = severity
    return draft


def export_draft(draft: ReportDraft) -> Dict[str, Any]:
    """
    Export a draft for review.
    Raises if not manually approved.
    Does NOT auto-submit to any external platform.
    """
    if not draft.is_export_allowed():
        raise PermissionError(
            "EXPORT BLOCKED: Report requires manual human approval before export. "
            "Call draft.approve(approver_name) first."
        )
    return draft.to_dict()
