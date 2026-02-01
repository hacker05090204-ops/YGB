# Phase-47: Shared Truth Store
"""Append-only JSON, signed entries, tamper detection."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Any
import json
import hashlib
import uuid
from datetime import datetime


class EntryType(Enum):
    """CLOSED ENUM - 5 members"""
    FACT = "FACT"
    CLAIM = "CLAIM"
    ATTESTATION = "ATTESTATION"
    RETRACTION = "RETRACTION"
    SYSTEM = "SYSTEM"


class TruthStatus(Enum):
    """CLOSED ENUM - 4 members"""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    DISPUTED = "DISPUTED"
    RETRACTED = "RETRACTED"


@dataclass(frozen=True)
class TruthEntry:
    """Frozen dataclass for a truth store entry."""
    entry_id: str
    entry_type: EntryType
    content: str  # JSON string
    author_id: str
    timestamp: str
    signature: str
    previous_hash: str
    status: TruthStatus


def compute_entry_hash(entry_id: str, content: str, author_id: str, prev_hash: str) -> str:
    """Compute hash for entry signing."""
    data = f"{entry_id}:{content}:{author_id}:{prev_hash}"
    return hashlib.sha256(data.encode()).hexdigest()


def create_truth_entry(
    entry_type: EntryType,
    content: dict,
    author_id: str,
    store: List[TruthEntry],
) -> TruthEntry:
    """Create and append a truth entry (append-only)."""
    entry_id = f"TRU-{uuid.uuid4().hex[:16].upper()}"
    content_json = json.dumps(content, sort_keys=True)
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    prev_hash = store[-1].signature if store else "GENESIS"
    signature = compute_entry_hash(entry_id, content_json, author_id, prev_hash)
    
    return TruthEntry(
        entry_id=entry_id,
        entry_type=entry_type,
        content=content_json,
        author_id=author_id,
        timestamp=timestamp,
        signature=signature,
        previous_hash=prev_hash,
        status=TruthStatus.UNVERIFIED,
    )


def verify_truth_chain(store: List[TruthEntry]) -> bool:
    """Verify the truth store chain integrity (tamper detection)."""
    if not store:
        return True
    
    for i, entry in enumerate(store):
        if i == 0:
            if entry.previous_hash != "GENESIS":
                return False
        else:
            if entry.previous_hash != store[i-1].signature:
                return False
        
        # Verify signature
        expected = compute_entry_hash(
            entry.entry_id, entry.content, entry.author_id, entry.previous_hash
        )
        if entry.signature != expected:
            return False
    
    return True


def query_truth(store: List[TruthEntry], entry_id: str) -> Optional[TruthEntry]:
    """Query a specific entry from the truth store."""
    for entry in store:
        if entry.entry_id == entry_id:
            return entry
    return None


def count_by_author(store: List[TruthEntry], author_id: str) -> int:
    """Count entries by author."""
    return sum(1 for e in store if e.author_id == author_id)
