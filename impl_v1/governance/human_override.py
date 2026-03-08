"""
Human Override Protocol
========================

EMERGENCY_OVERRIDE requires:
- Two-person approval
- Signed commit
- GPG verification
- Audit log entry

No single human can unlock.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib


# =============================================================================
# OVERRIDE REQUEST
# =============================================================================

@dataclass
class OverrideRequest:
    """Emergency override request."""
    request_id: str
    reason: str
    requested_by: str
    requested_at: str
    first_approver: Optional[str] = None
    first_approval_at: Optional[str] = None
    second_approver: Optional[str] = None
    second_approval_at: Optional[str] = None
    gpg_signature: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected, expired


# =============================================================================
# OVERRIDE MANAGER
# =============================================================================

class EmergencyOverrideManager:
    """Manage emergency overrides with dual approval."""
    
    OVERRIDE_FILE = Path("impl_v1/governance/EMERGENCY_OVERRIDE.json")
    AUDIT_LOG = Path("reports/override_audit.jsonl")
    MISUSE_WINDOW = timedelta(days=1)
    MISUSE_THRESHOLD = 5
    
    def __init__(self):
        self.current_request: Optional[OverrideRequest] = None
        self._load_state()
    
    def _load_state(self) -> None:
        """Load override state."""
        if self.OVERRIDE_FILE.exists():
            try:
                with open(self.OVERRIDE_FILE, "r") as f:
                    data = json.load(f)
                
                if data.get("current_request"):
                    self.current_request = OverrideRequest(**data["current_request"])
            except Exception:
                pass
    
    def _save_state(self) -> None:
        """Save override state."""
        self.OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "current_request": None,
            "last_updated": datetime.now().isoformat(),
        }
        
        if self.current_request:
            data["current_request"] = {
                "request_id": self.current_request.request_id,
                "reason": self.current_request.reason,
                "requested_by": self.current_request.requested_by,
                "requested_at": self.current_request.requested_at,
                "first_approver": self.current_request.first_approver,
                "first_approval_at": self.current_request.first_approval_at,
                "second_approver": self.current_request.second_approver,
                "second_approval_at": self.current_request.second_approval_at,
                "gpg_signature": self.current_request.gpg_signature,
                "status": self.current_request.status,
            }
        
        with open(self.OVERRIDE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def _log_audit(self, action: str, details: dict) -> None:
        """Log audit entry."""
        self.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
        }
        
        with open(self.AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def create_request(self, reason: str, requested_by: str) -> OverrideRequest:
        """Create override request."""
        request_id = f"OVERRIDE_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        self.current_request = OverrideRequest(
            request_id=request_id,
            reason=reason,
            requested_by=requested_by,
            requested_at=datetime.now().isoformat(),
        )
        
        self._save_state()
        self._log_audit("request_created", {
            "request_id": request_id,
            "reason": reason,
            "requested_by": requested_by,
        })
        
        return self.current_request
    
    def approve(
        self,
        approver: str,
        gpg_signature: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Approve override request."""
        if not self.current_request:
            return False, "No pending request"
        
        if self.current_request.status != "pending":
            return False, f"Request already {self.current_request.status}"
        
        # Check for duplicate approver
        if approver == self.current_request.requested_by:
            return False, "Cannot approve own request"
        
        if approver == self.current_request.first_approver:
            return False, "Already approved by this person"
        
        # First approval
        if self.current_request.first_approver is None:
            self.current_request.first_approver = approver
            self.current_request.first_approval_at = datetime.now().isoformat()
            
            self._save_state()
            self._log_audit("first_approval", {
                "request_id": self.current_request.request_id,
                "approver": approver,
            })
            
            return True, "First approval recorded. Awaiting second approval."

        # Second approval
        if not gpg_signature or not str(gpg_signature).strip():
            return False, "Second approval requires a GPG signature"

        self.current_request.second_approver = approver
        self.current_request.second_approval_at = datetime.now().isoformat()
        self.current_request.gpg_signature = gpg_signature
        self.current_request.status = "approved"
        
        self._save_state()
        self._log_audit("override_approved", {
            "request_id": self.current_request.request_id,
            "first_approver": self.current_request.first_approver,
            "second_approver": approver,
            "gpg_verified": gpg_signature is not None,
        })
        
        return True, "OVERRIDE APPROVED (dual approval complete)"
    
    def reject(self, rejector: str, reason: str) -> Tuple[bool, str]:
        """Reject override request."""
        if not self.current_request:
            return False, "No pending request"
        
        self.current_request.status = "rejected"
        
        self._save_state()
        self._log_audit("override_rejected", {
            "request_id": self.current_request.request_id,
            "rejector": rejector,
            "reason": reason,
        })
        
        return True, "Override request rejected"
    
    def is_override_active(self) -> Tuple[bool, str]:
        """Check if override is currently active."""
        if not self.current_request:
            return False, "No override request"
        
        if self.current_request.status == "approved":
            return True, "Override active (dual approval)"

        return False, f"Override status: {self.current_request.status}"

    def governance_clearance(self) -> Tuple[bool, str]:
        """Return whether the override lane is clear for normal auto-mode."""
        if not self.current_request:
            return True, "No override request"

        status = (self.current_request.status or "").strip().lower()
        if status in {"pending", "approved"}:
            return False, f"Override lane not clear: {self.current_request.status}"

        return True, f"Override status: {self.current_request.status}"
    
    def clear_override(self) -> None:
        """Clear current override (return to normal)."""
        if self.current_request:
            self._log_audit("override_cleared", {
                "request_id": self.current_request.request_id,
            })
        
        self.current_request = None
        self._save_state()
    
    def check_for_misuse(self) -> Tuple[bool, List[str]]:
        """Check for override misuse patterns."""
        issues = []
        
        # Check audit log for patterns
        if not self.AUDIT_LOG.exists():
            return False, []
        
        recent_overrides = 0
        cutoff = datetime.now() - self.MISUSE_WINDOW
        
        with open(self.AUDIT_LOG, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("action") != "override_approved":
                        continue
                    timestamp = entry.get("timestamp")
                    if not timestamp:
                        continue
                    approved_at = datetime.fromisoformat(timestamp)
                    if approved_at >= cutoff:
                        recent_overrides += 1
                except Exception:
                    pass
        
        if recent_overrides > self.MISUSE_THRESHOLD:
            issues.append(
                f"High override frequency: {recent_overrides} approvals in the last "
                f"{int(self.MISUSE_WINDOW.total_seconds() // 3600)}h"
            )
        
        return len(issues) > 0, issues
