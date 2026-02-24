"""
Quarantine Store — Low-Quality Data Isolation with Audit Trail
==============================================================

No silent data deletion. Quarantined records are:
  - Moved to quarantine directory
  - Logged with reason, timestamp, provenance
  - Preserved for audit review

Chain-of-custody: every quarantine action is logged with
original hash, quarantine reason, quarantine timestamp, and
operator/system identity.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# QUARANTINE RECORD
# =============================================================================

@dataclass
class QuarantineRecord:
    """Record of a quarantined data sample."""
    sample_id: str
    reason_code: str           # SCHEMA_VIOLATION, LOW_QUALITY, DUPLICATE, etc.
    reason_detail: str
    original_hash: str         # SHA-256 of original data
    quarantined_at: str = ""
    source_provenance: str = ""  # Where the data came from
    operator: str = "SYSTEM"

    def __post_init__(self):
        if not self.quarantined_at:
            self.quarantined_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# QUARANTINE STORE
# =============================================================================

class QuarantineStore:
    """
    Persistent quarantine store for rejected samples.

    Directory structure:
        quarantine_dir/
            ledger.jsonl      — Append-only quarantine log
            samples/          — Quarantined sample data
    """

    def __init__(self, quarantine_dir: str = "secure_data/quarantine"):
        self._dir = Path(quarantine_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / "samples").mkdir(exist_ok=True)
        self._ledger_path = self._dir / "ledger.jsonl"
        self._count = 0

    def quarantine(
        self,
        sample_id: str,
        sample_data: dict,
        reason_code: str,
        reason_detail: str,
        source_provenance: str = "unknown",
    ) -> QuarantineRecord:
        """
        Quarantine a sample with full audit trail.

        No silent deletion — data is preserved.
        """
        # Hash original data
        data_json = json.dumps(sample_data, sort_keys=True)
        original_hash = hashlib.sha256(data_json.encode()).hexdigest()

        record = QuarantineRecord(
            sample_id=sample_id,
            reason_code=reason_code,
            reason_detail=reason_detail,
            original_hash=original_hash,
            source_provenance=source_provenance,
        )

        # Store sample data
        sample_path = self._dir / "samples" / f"{sample_id}_{original_hash[:8]}.json"
        with open(sample_path, "w") as f:
            json.dump({
                "sample_data": sample_data,
                "quarantine_record": record.to_dict(),
            }, f, indent=2)

        # Append to ledger (append-only)
        with open(self._ledger_path, "a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

        self._count += 1
        logger.info(
            f"[QUARANTINE] {sample_id}: {reason_code} — {reason_detail} "
            f"(hash: {original_hash[:16]}...)"
        )
        return record

    @property
    def count(self) -> int:
        return self._count

    def get_ledger(self) -> List[QuarantineRecord]:
        """Read all quarantine records from ledger."""
        records = []
        if not self._ledger_path.exists():
            return records
        with open(self._ledger_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    records.append(QuarantineRecord(**data))
        return records

    def get_summary(self) -> dict:
        """Get quarantine summary statistics."""
        records = self.get_ledger()
        by_reason = {}
        for r in records:
            by_reason[r.reason_code] = by_reason.get(r.reason_code, 0) + 1
        return {
            "total_quarantined": len(records),
            "by_reason": by_reason,
            "quarantine_dir": str(self._dir),
        }
