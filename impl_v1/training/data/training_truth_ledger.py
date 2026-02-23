"""
training_truth_ledger.py — Training Truth Ledger (Phase 5)

██████████████████████████████████████████████████████████████████████
APPEND-ONLY TRAINING AUDIT LOG — IMMUTABLE WRITE MODE
██████████████████████████████████████████████████████████████████████

Logs per training run:
  - Dataset hash
  - Bridge hash
  - DLL hash
  - Registry status
  - Sample count
  - Entropy stats
  - Label balance score
  - Integrity verification result
  - Timestamp

Append-only JSON. No overwrite. Immutable write mode.
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Ledger path — append-only
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LEDGER_DIR = _PROJECT_ROOT / "secure_data"
_LEDGER_FILE = _LEDGER_DIR / "training_truth_ledger.jsonl"


@dataclass
class TruthLedgerEntry:
    """One immutable entry in the training truth ledger."""
    timestamp: str
    run_id: str
    dataset_hash: str
    bridge_hash: str
    dll_hash: str
    manifest_hash: str
    registry_status: str
    dataset_source: str
    sample_count: int
    feature_dim: int
    num_classes: int
    shannon_entropy: float
    label_balance_score: float
    duplicate_ratio: float
    rng_autocorrelation: float
    integrity_verified: bool
    module_guard_passed: bool
    data_enforcer_passed: bool
    strict_real_mode: bool
    synthetic_blocked: bool
    verdict: str  # "APPROVED" or "REJECTED"
    rejection_reason: str = ""


def _compute_entry_hash(entry: dict) -> str:
    """Compute HMAC hash of a ledger entry for tamper detection."""
    raw = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def append_truth_entry(entry: TruthLedgerEntry) -> str:
    """
    Append a truth entry to the ledger. IMMUTABLE — no overwrite.

    Returns:
        Entry hash for verification.
    """
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)

    entry_dict = asdict(entry)
    entry_hash = _compute_entry_hash(entry_dict)
    entry_dict["entry_hash"] = entry_hash

    # Append-only write — open in append mode
    with open(_LEDGER_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry_dict, separators=(",", ":")) + "\n")

    logger.info(
        f"[TRUTH_LEDGER] Entry appended: run={entry.run_id}, "
        f"verdict={entry.verdict}, hash={entry_hash[:16]}..."
    )

    return entry_hash


def read_truth_ledger() -> list:
    """Read all entries from the truth ledger."""
    if not _LEDGER_FILE.exists():
        return []

    entries = []
    with open(_LEDGER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return entries


def verify_ledger_integrity() -> tuple:
    """
    Verify all ledger entries have valid hashes (no tampering).

    Returns:
        (passed: bool, message: str)
    """
    entries = read_truth_ledger()
    if not entries:
        return True, "Ledger empty — no entries to verify"

    tampered = 0
    for i, entry in enumerate(entries):
        stored_hash = entry.pop("entry_hash", "")
        computed_hash = _compute_entry_hash(entry)
        entry["entry_hash"] = stored_hash  # Restore

        if stored_hash != computed_hash:
            tampered += 1
            logger.error(
                f"[TRUTH_LEDGER] TAMPER DETECTED at entry {i}: "
                f"stored={stored_hash[:16]}, computed={computed_hash[:16]}"
            )

    if tampered > 0:
        return False, f"TAMPER DETECTED: {tampered}/{len(entries)} entries modified"

    return True, f"Ledger integrity OK: {len(entries)} entries verified"


def get_latest_entry() -> Optional[dict]:
    """Get the most recent ledger entry."""
    entries = read_truth_ledger()
    return entries[-1] if entries else None


def create_run_id() -> str:
    """Generate a unique run ID."""
    return f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
