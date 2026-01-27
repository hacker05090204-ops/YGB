# Phase-45: Hunter Identity & Role Ledger
"""Immutable audit trail: who, when, what target."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import uuid
import hashlib
from datetime import datetime


class HunterRole(Enum):
    """CLOSED ENUM - 5 members"""
    RESEARCHER = "RESEARCHER"
    TRIAGER = "TRIAGER"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"
    OBSERVER = "OBSERVER"


class ActionType(Enum):
    """CLOSED ENUM - 8 members"""
    SCAN = "SCAN"
    DISCOVER = "DISCOVER"
    REPORT = "REPORT"
    REVIEW = "REVIEW"
    ESCALATE = "ESCALATE"
    CLOSE = "CLOSE"
    ASSIGN = "ASSIGN"
    VIEW = "VIEW"


class LedgerEntryType(Enum):
    """CLOSED ENUM - 4 members"""
    ACTION = "ACTION"
    ROLE_CHANGE = "ROLE_CHANGE"
    TARGET_CHANGE = "TARGET_CHANGE"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class HunterIdentity:
    """Frozen dataclass for hunter identity."""
    hunter_id: str
    role: HunterRole
    registered_at: str
    identity_hash: str


@dataclass(frozen=True)
class LedgerEntry:
    """Frozen dataclass for audit ledger entry."""
    entry_id: str
    entry_type: LedgerEntryType
    hunter_id: str
    action: ActionType
    target_id: str
    timestamp: str
    previous_hash: str
    entry_hash: str


def create_identity_hash(hunter_id: str, role: HunterRole, timestamp: str) -> str:
    """Create a deterministic identity hash."""
    content = f"{hunter_id}:{role.value}:{timestamp}"
    return hashlib.sha256(content.encode()).hexdigest()


def create_hunter_identity(hunter_id: str, role: HunterRole) -> HunterIdentity:
    """Create a new hunter identity."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    return HunterIdentity(
        hunter_id=hunter_id,
        role=role,
        registered_at=timestamp,
        identity_hash=create_identity_hash(hunter_id, role, timestamp),
    )


def create_entry_hash(entry_id: str, hunter_id: str, action: str, target_id: str, prev_hash: str) -> str:
    """Create a hash for ledger entry (chain integrity)."""
    content = f"{entry_id}:{hunter_id}:{action}:{target_id}:{prev_hash}"
    return hashlib.sha256(content.encode()).hexdigest()


def append_ledger_entry(
    ledger: List[LedgerEntry],
    hunter_id: str,
    action: ActionType,
    target_id: str,
) -> LedgerEntry:
    """Append an entry to the ledger (immutable)."""
    entry_id = f"LED-{uuid.uuid4().hex[:16].upper()}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    prev_hash = ledger[-1].entry_hash if ledger else "GENESIS"
    entry_hash = create_entry_hash(entry_id, hunter_id, action.value, target_id, prev_hash)
    
    return LedgerEntry(
        entry_id=entry_id,
        entry_type=LedgerEntryType.ACTION,
        hunter_id=hunter_id,
        action=action,
        target_id=target_id,
        timestamp=timestamp,
        previous_hash=prev_hash,
        entry_hash=entry_hash,
    )


def verify_ledger_integrity(ledger: List[LedgerEntry]) -> bool:
    """Verify the ledger chain has not been tampered with."""
    if not ledger:
        return True
    
    for i, entry in enumerate(ledger):
        if i == 0:
            if entry.previous_hash != "GENESIS":
                return False
        else:
            if entry.previous_hash != ledger[i-1].entry_hash:
                return False
        
        # Verify entry hash
        expected = create_entry_hash(
            entry.entry_id, entry.hunter_id, entry.action.value, entry.target_id, entry.previous_hash
        )
        if entry.entry_hash != expected:
            return False
    
    return True
