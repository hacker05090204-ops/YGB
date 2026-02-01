"""
Phase-18 Ledger Engine.

This module provides execution ledger functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A LEDGER LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
import uuid
from typing import Tuple

from .ledger_types import (
    ExecutionState,
    EvidenceStatus,
    RetryDecision,
    VALID_TRANSITIONS,
    TERMINAL_STATES
)
from .ledger_context import (
    ExecutionRecord,
    EvidenceRecord,
    ExecutionLedgerEntry,
    LedgerValidationResult
)


def generate_id(prefix: str) -> str:
    """Generate unique ID with prefix.
    
    Args:
        prefix: ID prefix
        
    Returns:
        Unique ID string
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def create_execution_record(
    request_id: str,
    bug_id: str,
    target_id: str,
    timestamp: str
) -> ExecutionRecord:
    """Create new execution record.
    
    Args:
        request_id: From Phase-17 request
        bug_id: Bug identifier
        target_id: Target identifier
        timestamp: ISO timestamp
        
    Returns:
        New ExecutionRecord
    """
    return ExecutionRecord(
        execution_id=generate_id("EXEC"),
        request_id=request_id,
        bug_id=bug_id,
        target_id=target_id,
        created_at=timestamp,
        current_state=ExecutionState.REQUESTED,
        attempt_count=0,
        max_attempts=3,
        finalized=False
    )


def record_attempt(record: ExecutionRecord) -> ExecutionRecord:
    """Record execution attempt.
    
    Creates new record with incremented attempt_count.
    
    Args:
        record: Current record
        
    Returns:
        New ExecutionRecord with incremented count
    """
    return ExecutionRecord(
        execution_id=record.execution_id,
        request_id=record.request_id,
        bug_id=record.bug_id,
        target_id=record.target_id,
        created_at=record.created_at,
        current_state=record.current_state,
        attempt_count=record.attempt_count + 1,
        max_attempts=record.max_attempts,
        finalized=record.finalized
    )


def is_valid_transition(
    from_state: ExecutionState,
    to_state: ExecutionState
) -> bool:
    """Check if state transition is valid.
    
    Args:
        from_state: Current state
        to_state: Target state
        
    Returns:
        True if valid transition
    """
    # Cannot transition from terminal states (except ESCALATED for audit)
    if from_state == ExecutionState.COMPLETED:
        return False
    
    # Cannot transition TO REQUESTED
    if to_state == ExecutionState.REQUESTED:
        return False
    
    return (from_state, to_state) in VALID_TRANSITIONS


def transition_state(
    record: ExecutionRecord,
    to_state: ExecutionState,
    timestamp: str
) -> ExecutionLedgerEntry:
    """Transition execution state.
    
    Args:
        record: Current record
        to_state: Target state
        timestamp: Transition timestamp
        
    Returns:
        ExecutionLedgerEntry documenting transition
    """
    from_state = record.current_state
    
    # Check if transition is valid
    if not is_valid_transition(from_state, to_state):
        reason = f"DENIED: Cannot transition from {from_state.name}"
        if record.finalized:
            reason = "DENIED: Record is finalized"
    else:
        reason = f"Transition {from_state.name} -> {to_state.name}"
    
    return ExecutionLedgerEntry(
        entry_id=generate_id("ENT"),
        execution_id=record.execution_id,
        timestamp=timestamp,
        from_state=from_state,
        to_state=to_state,
        reason=reason
    )


def attach_evidence(
    execution_id: str,
    evidence_hash: str,
    timestamp: str,
    used_hashes: frozenset
) -> Tuple[EvidenceRecord, LedgerValidationResult]:
    """Attach evidence to execution.
    
    Args:
        execution_id: Execution ID
        evidence_hash: Evidence hash
        timestamp: Attachment timestamp
        used_hashes: Set of already used hashes
        
    Returns:
        Tuple of (EvidenceRecord, LedgerValidationResult)
    """
    # Empty hash is invalid
    if not evidence_hash:
        return (
            EvidenceRecord(
                evidence_id=generate_id("EVD"),
                execution_id=execution_id,
                evidence_hash="",
                evidence_status=EvidenceStatus.INVALID,
                linked_at=timestamp
            ),
            LedgerValidationResult(
                is_valid=False,
                reason_code="EV-001",
                reason_description="Evidence hash is empty"
            )
        )
    
    # Replayed hash is denied
    if evidence_hash in used_hashes:
        return (
            EvidenceRecord(
                evidence_id=generate_id("EVD"),
                execution_id=execution_id,
                evidence_hash=evidence_hash,
                evidence_status=EvidenceStatus.INVALID,
                linked_at=timestamp
            ),
            LedgerValidationResult(
                is_valid=False,
                reason_code="EV-002",
                reason_description="Evidence hash already used (replay)"
            )
        )
    
    # Valid evidence
    return (
        EvidenceRecord(
            evidence_id=generate_id("EVD"),
            execution_id=execution_id,
            evidence_hash=evidence_hash,
            evidence_status=EvidenceStatus.LINKED,
            linked_at=timestamp
        ),
        LedgerValidationResult(
            is_valid=True,
            reason_code="EV-OK",
            reason_description="Evidence linked successfully"
        )
    )


def validate_evidence_linkage(evidence: EvidenceRecord) -> LedgerValidationResult:
    """Validate evidence is properly linked.
    
    Args:
        evidence: EvidenceRecord
        
    Returns:
        LedgerValidationResult
    """
    # MISSING is invalid
    if evidence.evidence_status == EvidenceStatus.MISSING:
        return LedgerValidationResult(
            is_valid=False,
            reason_code="EV-003",
            reason_description="Evidence is missing"
        )
    
    # INVALID is invalid
    if evidence.evidence_status == EvidenceStatus.INVALID:
        return LedgerValidationResult(
            is_valid=False,
            reason_code="EV-004",
            reason_description="Evidence is invalid"
        )
    
    # Empty hash with LINKED status is invalid
    if evidence.evidence_status == EvidenceStatus.LINKED and not evidence.evidence_hash:
        return LedgerValidationResult(
            is_valid=False,
            reason_code="EV-005",
            reason_description="LINKED but no hash"
        )
    
    # LINKED or VERIFIED is valid
    return LedgerValidationResult(
        is_valid=True,
        reason_code="EV-OK",
        reason_description="Evidence is valid"
    )


def decide_retry(record: ExecutionRecord) -> RetryDecision:
    """Decide if retry is allowed.
    
    Args:
        record: ExecutionRecord
        
    Returns:
        RetryDecision
    """
    state = record.current_state
    
    # COMPLETED → no retry
    if state == ExecutionState.COMPLETED:
        return RetryDecision.DENIED
    
    # ESCALATED → human required
    if state == ExecutionState.ESCALATED:
        return RetryDecision.HUMAN_REQUIRED
    
    # FAILED with attempts remaining → allowed
    if state == ExecutionState.FAILED:
        if record.attempt_count >= record.max_attempts:
            return RetryDecision.DENIED
        return RetryDecision.ALLOWED
    
    # Default → denied
    return RetryDecision.DENIED
