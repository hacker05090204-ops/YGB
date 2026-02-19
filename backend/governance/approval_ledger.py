"""
APPROVAL LEDGER — Append-Only Immutable Certification Log
=========================================================
Rules:
  - Certification requires signed approval token (not boolean)
  - Token stored in append-only ledger
  - Ledger hash verified before field freeze
  - All approval events logged immutably
  - No boolean flags allowed for human approval
=========================================================
"""

import hmac
import hashlib
import json
import os
import time
from typing import Optional


class ApprovalToken:
    """Signed, non-boolean approval token."""

    def __init__(self, field_id: int, approver_id: str, reason: str,
                 timestamp: float, signature: str):
        self.field_id = field_id
        self.approver_id = approver_id
        self.reason = reason
        self.timestamp = timestamp
        self.signature = signature

    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "approver_id": self.approver_id,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "signature": self.signature
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ApprovalToken":
        return cls(
            field_id=d["field_id"],
            approver_id=d["approver_id"],
            reason=d["reason"],
            timestamp=d["timestamp"],
            signature=d["signature"]
        )


class ApprovalLedger:
    """Append-only, hash-chained approval ledger."""

    # Secret for HMAC signing (should come from env in production)
    _SECRET = os.environ.get("YGB_APPROVAL_SECRET", "ygb-approval-key-v1").encode()

    def __init__(self, ledger_path: str = "data/approval_ledger.jsonl"):
        self._path = ledger_path
        self._entries: list[dict] = []
        self._chain_hash = "0" * 64  # genesis hash

    # ---------------------------------------------------------
    # SIGN — create HMAC signature for approval
    # ---------------------------------------------------------
    def sign_approval(self, field_id: int, approver_id: str,
                      reason: str) -> ApprovalToken:
        """Create a signed approval token. NOT a boolean flag."""
        if not approver_id or not reason:
            raise ValueError("APPROVAL_REJECTED: approver_id and reason required")

        timestamp = time.time()
        payload = f"{field_id}:{approver_id}:{reason}:{timestamp}"
        signature = hmac.new(
            self._SECRET, payload.encode(), hashlib.sha256
        ).hexdigest()

        return ApprovalToken(field_id, approver_id, reason, timestamp, signature)

    # ---------------------------------------------------------
    # VERIFY — check token signature
    # ---------------------------------------------------------
    def verify_token(self, token: ApprovalToken) -> bool:
        """Verify HMAC signature on approval token."""
        payload = f"{token.field_id}:{token.approver_id}:{token.reason}:{token.timestamp}"
        expected = hmac.new(
            self._SECRET, payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, token.signature)

    # ---------------------------------------------------------
    # APPEND — add entry to ledger (append-only)
    # ---------------------------------------------------------
    def append(self, token: ApprovalToken) -> dict:
        """Append approval to ledger. Immutable — entries never modified."""
        if not self.verify_token(token):
            raise ValueError("INVALID_SIGNATURE: token verification failed")

        entry = {
            "sequence": len(self._entries),
            "token": token.to_dict(),
            "prev_hash": self._chain_hash,
            "entry_hash": "",
            "appended_at": time.time()
        }

        # Compute chain hash
        entry_data = json.dumps(
            {k: v for k, v in entry.items() if k != "entry_hash"},
            sort_keys=True
        )
        entry["entry_hash"] = hashlib.sha256(entry_data.encode()).hexdigest()
        self._chain_hash = entry["entry_hash"]

        self._entries.append(entry)

        # Persist atomically
        self._persist(entry)

        return entry

    # ---------------------------------------------------------
    # VERIFY CHAIN — validate entire ledger integrity
    # ---------------------------------------------------------
    def verify_chain(self) -> bool:
        """Verify hash chain integrity. Returns False if tampered."""
        prev_hash = "0" * 64

        for entry in self._entries:
            if entry["prev_hash"] != prev_hash:
                return False

            entry_data = json.dumps(
                {k: v for k, v in entry.items() if k != "entry_hash"},
                sort_keys=True
            )
            computed = hashlib.sha256(entry_data.encode()).hexdigest()
            if computed != entry["entry_hash"]:
                return False

            prev_hash = entry["entry_hash"]

        return True

    # ---------------------------------------------------------
    # QUERY — find approval for field
    # ---------------------------------------------------------
    def get_approval(self, field_id: int) -> Optional[dict]:
        """Get latest approval entry for field. Returns None if not found."""
        for entry in reversed(self._entries):
            if entry["token"]["field_id"] == field_id:
                return entry
        return None

    def has_approval(self, field_id: int) -> bool:
        """Check if field has been approved."""
        return self.get_approval(field_id) is not None

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def chain_hash(self) -> str:
        return self._chain_hash

    # ---------------------------------------------------------
    # PERSISTENCE — append-only file
    # ---------------------------------------------------------
    def _persist(self, entry: dict) -> None:
        """Append entry to file. Creates directory if needed."""
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def load(self) -> None:
        """Load existing ledger from file."""
        self._entries = []
        self._chain_hash = "0" * 64

        if not os.path.exists(self._path):
            return

        with open(self._path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    self._entries.append(entry)
                    self._chain_hash = entry["entry_hash"]
