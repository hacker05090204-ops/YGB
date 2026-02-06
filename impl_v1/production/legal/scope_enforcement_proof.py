"""
Scope Enforcement Proof - Legal Safety Layer
==============================================

Prove scope enforcement with immutable evidence chain.
"""

from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime
from pathlib import Path
import json
import hashlib


# =============================================================================
# EVIDENCE CHAIN
# =============================================================================

@dataclass
class EvidenceRecord:
    """An immutable evidence record."""
    record_id: str
    timestamp: str
    action: str
    target: str
    scope_id: str
    decision: str  # "ALLOWED" or "BLOCKED"
    reason: str
    hash: str  # Hash of this record
    prev_hash: str  # Hash of previous record


class EvidenceChain:
    """Immutable evidence chain for audit trail."""
    
    CHAIN_FILE = Path("reports/evidence_chain.jsonl")
    
    def __init__(self):
        self.records: List[EvidenceRecord] = []
        self._load_chain()
    
    def _load_chain(self) -> None:
        """Load existing chain."""
        if not self.CHAIN_FILE.exists():
            return
        
        try:
            with open(self.CHAIN_FILE, "r") as f:
                for line in f:
                    data = json.loads(line)
                    self.records.append(EvidenceRecord(**data))
        except Exception:
            pass
    
    def _compute_hash(self, record_data: str) -> str:
        """Compute SHA256 hash of record."""
        return hashlib.sha256(record_data.encode()).hexdigest()
    
    def add_record(
        self,
        action: str,
        target: str,
        scope_id: str,
        decision: str,
        reason: str,
    ) -> EvidenceRecord:
        """Add record to chain."""
        prev_hash = self.records[-1].hash if self.records else "GENESIS"
        
        timestamp = datetime.now().isoformat()
        record_id = f"EVD_{len(self.records):06d}"
        
        # Create record data for hashing
        record_data = f"{record_id}:{timestamp}:{action}:{target}:{scope_id}:{decision}:{reason}:{prev_hash}"
        record_hash = self._compute_hash(record_data)
        
        record = EvidenceRecord(
            record_id=record_id,
            timestamp=timestamp,
            action=action,
            target=target,
            scope_id=scope_id,
            decision=decision,
            reason=reason,
            hash=record_hash,
            prev_hash=prev_hash,
        )
        
        self.records.append(record)
        self._persist_record(record)
        
        return record
    
    def _persist_record(self, record: EvidenceRecord) -> None:
        """Persist record to chain file."""
        self.CHAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.CHAIN_FILE, "a") as f:
            f.write(json.dumps({
                "record_id": record.record_id,
                "timestamp": record.timestamp,
                "action": record.action,
                "target": record.target,
                "scope_id": record.scope_id,
                "decision": record.decision,
                "reason": record.reason,
                "hash": record.hash,
                "prev_hash": record.prev_hash,
            }) + "\n")
    
    def verify_chain_integrity(self) -> tuple:
        """Verify chain has not been tampered."""
        if len(self.records) == 0:
            return True, "Chain empty"
        
        for i, record in enumerate(self.records):
            # Verify hash linkage
            if i == 0:
                if record.prev_hash != "GENESIS":
                    return False, f"Record {record.record_id}: Invalid genesis"
            else:
                if record.prev_hash != self.records[i-1].hash:
                    return False, f"Record {record.record_id}: Chain broken"
            
            # Verify record hash
            record_data = f"{record.record_id}:{record.timestamp}:{record.action}:{record.target}:{record.scope_id}:{record.decision}:{record.reason}:{record.prev_hash}"
            expected_hash = self._compute_hash(record_data)
            
            if record.hash != expected_hash:
                return False, f"Record {record.record_id}: Hash mismatch"
        
        return True, "Chain integrity verified"


# =============================================================================
# SCOPE ENFORCEMENT PROOF
# =============================================================================

class ScopeEnforcementProof:
    """Generate scope enforcement proofs."""
    
    def __init__(self):
        self.chain = EvidenceChain()
    
    def record_scan_attempt(
        self,
        target: str,
        scope_id: str,
        allowed: bool,
        reason: str,
    ) -> EvidenceRecord:
        """Record a scan attempt with evidence."""
        return self.chain.add_record(
            action="SCAN_ATTEMPT",
            target=target,
            scope_id=scope_id or "NONE",
            decision="ALLOWED" if allowed else "BLOCKED",
            reason=reason,
        )
    
    def generate_proof_report(self) -> dict:
        """Generate scope enforcement proof report."""
        is_valid, msg = self.chain.verify_chain_integrity()
        
        total = len(self.chain.records)
        allowed = sum(1 for r in self.chain.records if r.decision == "ALLOWED")
        blocked = sum(1 for r in self.chain.records if r.decision == "BLOCKED")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "chain_integrity": is_valid,
            "integrity_message": msg,
            "total_records": total,
            "allowed": allowed,
            "blocked": blocked,
            "enforcement_rate": blocked / total if total > 0 else 1.0,
        }
