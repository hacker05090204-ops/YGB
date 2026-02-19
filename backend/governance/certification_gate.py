"""
certification_gate.py — Report Certification & Manual Approval Gate

All reports require manual human approval before any action.
No auto-submission. No automated negotiation. No authority unlock.
"""

import json
import os
from typing import Optional

class CertificationGate:
    """All findings must pass certification and human approval."""
    
    ALLOW_AUTO_SUBMIT = False
    ALLOW_AUTO_NEGOTIATE = False
    ALLOW_AUTHORITY_UNLOCK = False
    
    def __init__(self, state_path: str = "reports/certification_log.json"):
        self._state_path = state_path
        self._total_submitted = 0
        self._total_approved = 0
        self._total_rejected = 0
        self._pending = []
    
    def submit_for_review(self, finding_id: str, field: str,
                          confidence: float, duplicate_risk: float,
                          severity: str) -> dict:
        """Submit a finding for human review. NEVER auto-approves."""
        # Confidence gate
        if confidence < 0.93:
            self._total_rejected += 1
            return {
                "accepted": False,
                "reason": f"LOW_CONFIDENCE: {confidence:.3f} < 0.93"
            }
        
        # Duplicate risk gate
        if duplicate_risk > 0.75:
            self._total_rejected += 1
            return {
                "accepted": False,
                "reason": f"HIGH_DUPLICATE_RISK: {duplicate_risk:.3f} > 0.75"
            }
        
        entry = {
            "finding_id": finding_id,
            "field": field,
            "confidence": confidence,
            "duplicate_risk": duplicate_risk,
            "severity": severity,
            "status": "PENDING_HUMAN_REVIEW",
            "human_approved": False,
            "auto_submitted": False
        }
        
        self._pending.append(entry)
        self._total_submitted += 1
        self._persist()
        
        return {
            "accepted": True,
            "reason": "QUEUED_FOR_HUMAN_REVIEW",
            "status": "PENDING_HUMAN_REVIEW"
        }
    
    def human_approve(self, finding_id: str) -> dict:
        """Human approves a finding. This is the ONLY way to approve."""
        for entry in self._pending:
            if entry["finding_id"] == finding_id:
                entry["status"] = "HUMAN_APPROVED"
                entry["human_approved"] = True
                self._total_approved += 1
                self._persist()
                return {"approved": True, "reason": "HUMAN_APPROVED"}
        
        return {"approved": False, "reason": f"FINDING_NOT_FOUND: {finding_id}"}
    
    def human_reject(self, finding_id: str) -> dict:
        """Human rejects a finding."""
        for entry in self._pending:
            if entry["finding_id"] == finding_id:
                entry["status"] = "HUMAN_REJECTED"
                self._total_rejected += 1
                self._persist()
                return {"rejected": True, "reason": "HUMAN_REJECTED"}
        
        return {"rejected": False, "reason": f"FINDING_NOT_FOUND: {finding_id}"}
    
    @property
    def pending_count(self) -> int:
        return sum(1 for e in self._pending if e["status"] == "PENDING_HUMAN_REVIEW")
    
    @property
    def stats(self) -> dict:
        return {
            "total_submitted": self._total_submitted,
            "total_approved": self._total_approved,
            "total_rejected": self._total_rejected,
            "pending": self.pending_count
        }
    
    def _persist(self):
        """Atomic persistence of certification log."""
        tmp = self._state_path + ".tmp"
        data = {
            "stats": self.stats,
            "entries": self._pending[-50:],  # keep last 50
            "auto_submit": self.ALLOW_AUTO_SUBMIT,
            "auto_negotiate": self.ALLOW_AUTO_NEGOTIATE
        }
        os.makedirs(os.path.dirname(self._state_path) or ".", exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._state_path)
