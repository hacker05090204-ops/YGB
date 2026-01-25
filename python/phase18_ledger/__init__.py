"""
Phase-18 Execution State & Provenance Ledger.

This module provides execution lifecycle tracking.

THIS IS A LEDGER LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

Exports:
    Enums:
        ExecutionState: REQUESTED, ALLOWED, ATTEMPTED, FAILED, COMPLETED, ESCALATED
        EvidenceStatus: MISSING, LINKED, INVALID, VERIFIED
        RetryDecision: ALLOWED, DENIED, HUMAN_REQUIRED
    
    Dataclasses (all frozen=True):
        ExecutionRecord: Execution tracking
        EvidenceRecord: Evidence tracking
        ExecutionLedgerEntry: Ledger entries
        LedgerValidationResult: Validation results
    
    Functions:
        create_execution_record: Create new record
        record_attempt: Record attempt
        transition_state: Transition state
        attach_evidence: Attach evidence
        validate_evidence_linkage: Validate evidence
        decide_retry: Decide retry
        is_valid_transition: Check transition validity
"""
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
from .ledger_engine import (
    create_execution_record,
    record_attempt,
    transition_state,
    attach_evidence,
    validate_evidence_linkage,
    decide_retry,
    is_valid_transition
)

__all__ = [
    # Enums
    "ExecutionState",
    "EvidenceStatus",
    "RetryDecision",
    # Constants
    "VALID_TRANSITIONS",
    "TERMINAL_STATES",
    # Dataclasses
    "ExecutionRecord",
    "EvidenceRecord",
    "ExecutionLedgerEntry",
    "LedgerValidationResult",
    # Functions
    "create_execution_record",
    "record_attempt",
    "transition_state",
    "attach_evidence",
    "validate_evidence_linkage",
    "decide_retry",
    "is_valid_transition",
]
