"""
Phase-18 Ledger Context.

This module defines frozen dataclasses for execution ledger.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional

from .ledger_types import ExecutionState, EvidenceStatus


@dataclass(frozen=True)
class ExecutionRecord:
    """Immutable execution record.
    
    Attributes:
        execution_id: Unique execution ID
        request_id: From Phase-17 request
        bug_id: Bug identifier
        target_id: Target identifier
        created_at: ISO timestamp
        current_state: Current execution state
        attempt_count: Number of attempts
        max_attempts: Maximum allowed attempts
        finalized: Whether record is finalized
    """
    execution_id: str
    request_id: str
    bug_id: str
    target_id: str
    created_at: str
    current_state: ExecutionState
    attempt_count: int = 0
    max_attempts: int = 3
    finalized: bool = False


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable evidence record.
    
    Attributes:
        evidence_id: Unique evidence ID
        execution_id: Linked execution
        evidence_hash: Immutable hash
        evidence_status: Current status
        linked_at: ISO timestamp
    """
    evidence_id: str
    execution_id: str
    evidence_hash: str
    evidence_status: EvidenceStatus
    linked_at: str


@dataclass(frozen=True)
class ExecutionLedgerEntry:
    """Immutable ledger entry.
    
    Attributes:
        entry_id: Unique entry ID
        execution_id: Related execution
        timestamp: Entry timestamp
        from_state: Previous state
        to_state: New state
        reason: Transition reason
    """
    entry_id: str
    execution_id: str
    timestamp: str
    from_state: ExecutionState
    to_state: ExecutionState
    reason: str


@dataclass(frozen=True)
class LedgerValidationResult:
    """Ledger validation result.
    
    Attributes:
        is_valid: Whether valid
        reason_code: Machine-readable code
        reason_description: Human-readable description
    """
    is_valid: bool
    reason_code: str
    reason_description: str
