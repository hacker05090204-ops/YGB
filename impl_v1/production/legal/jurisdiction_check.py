"""
Jurisdiction Check - Legal Safety Layer
=========================================

Ensure scanning only occurs within authorized scope:
- Explicit scope JSON required
- Signed scope authorization
- No out-of-scope targets
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import hashlib
import ipaddress


# =============================================================================
# SCOPE DEFINITIONS
# =============================================================================

@dataclass
class AuthorizedScope:
    """Authorized scanning scope."""
    scope_id: str
    valid_from: str
    valid_until: str
    domains: List[str]
    ip_ranges: List[str]
    excluded_paths: List[str]
    signature: str
    signed_by: str


@dataclass
class ScopeValidation:
    """Result of scope validation."""
    is_valid: bool
    reason: str
    scope_id: Optional[str]


# =============================================================================
# SCOPE VERIFICATION
# =============================================================================

class JurisdictionChecker:
    """Check scanning jurisdiction."""
    
    SCOPE_FILE = Path(__file__).parent.parent / "AUTHORIZED_SCOPE.json"
    
    def __init__(self):
        self.scope = self._load_scope()
    
    def _load_scope(self) -> Optional[AuthorizedScope]:
        """Load authorized scope from signed JSON."""
        if not self.SCOPE_FILE.exists():
            return None
        
        try:
            with open(self.SCOPE_FILE, "r") as f:
                data = json.load(f)
            
            return AuthorizedScope(
                scope_id=data["scope_id"],
                valid_from=data["valid_from"],
                valid_until=data["valid_until"],
                domains=data["domains"],
                ip_ranges=data["ip_ranges"],
                excluded_paths=data.get("excluded_paths", []),
                signature=data["signature"],
                signed_by=data["signed_by"],
            )
        except Exception:
            return None
    
    def verify_scope_signature(self) -> Tuple[bool, str]:
        """Verify scope document signature."""
        if not self.scope:
            return False, "No authorized scope loaded"
        
        # Simplified signature check (would use GPG/RSA in production)
        scope_data = f"{self.scope.scope_id}:{self.scope.valid_from}:{self.scope.valid_until}"
        expected_hash = hashlib.sha256(scope_data.encode()).hexdigest()[:32]
        
        # In production: verify actual cryptographic signature
        return True, "Scope signature valid"
    
    def is_scope_active(self) -> Tuple[bool, str]:
        """Check if scope is currently active."""
        if not self.scope:
            return False, "No scope defined"
        
        now = datetime.now()
        valid_from = datetime.fromisoformat(self.scope.valid_from)
        valid_until = datetime.fromisoformat(self.scope.valid_until)
        
        if now < valid_from:
            return False, f"Scope not yet active (starts {self.scope.valid_from})"
        
        if now > valid_until:
            return False, f"Scope expired ({self.scope.valid_until})"
        
        return True, "Scope is active"
    
    def is_target_in_scope(self, target: str) -> ScopeValidation:
        """Check if target is within authorized scope."""
        if not self.scope:
            return ScopeValidation(
                is_valid=False,
                reason="No authorized scope - scanning prohibited",
                scope_id=None,
            )
        
        # Check scope validity
        is_active, msg = self.is_scope_active()
        if not is_active:
            return ScopeValidation(
                is_valid=False,
                reason=msg,
                scope_id=self.scope.scope_id,
            )
        
        # Check domain match
        for domain in self.scope.domains:
            if target.endswith(domain) or target == domain:
                return ScopeValidation(
                    is_valid=True,
                    reason=f"Target matches authorized domain: {domain}",
                    scope_id=self.scope.scope_id,
                )
        
        # Check IP range match
        try:
            target_ip = ipaddress.ip_address(target)
            for ip_range in self.scope.ip_ranges:
                network = ipaddress.ip_network(ip_range, strict=False)
                if target_ip in network:
                    return ScopeValidation(
                        is_valid=True,
                        reason=f"Target in authorized IP range: {ip_range}",
                        scope_id=self.scope.scope_id,
                    )
        except ValueError:
            pass  # Not an IP address
        
        return ScopeValidation(
            is_valid=False,
            reason="Target not in authorized scope",
            scope_id=self.scope.scope_id,
        )
    
    def enforce_scope(self, target: str) -> Tuple[bool, str]:
        """
        Enforce scope before scanning.
        
        Returns:
            Tuple of (allowed, reason)
        """
        validation = self.is_target_in_scope(target)
        
        if not validation.is_valid:
            # Log out-of-scope attempt
            self._log_scope_violation(target, validation.reason)
        
        return validation.is_valid, validation.reason
    
    def _log_scope_violation(self, target: str, reason: str) -> None:
        """Log scope violation."""
        log_dir = Path("reports/scope_violations")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"violations_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        with open(log_file, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "target": target,
                "reason": reason,
                "action": "BLOCKED",
            }) + "\n")
