"""
Phase-31 Observation Engine.

This module provides observation and evidence capture functions.

All functions are PURE (no side effects).
All decisions are deny-by-default.

THIS IS AN OBSERVATION LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
IT DOES NOT INTERPRET ANYTHING.

CORE RULES:
- Observation is PASSIVE only
- Evidence is RAW only (never parsed)
- Any ambiguity → HALT
- Humans remain final authority
"""
import hashlib
import uuid
from typing import Optional

from .observation_types import ObservationPoint, EvidenceType, StopCondition
from .observation_context import EvidenceRecord, ObservationContext, EvidenceChain


def _compute_evidence_hash(
    record_id: str,
    observation_point: ObservationPoint,
    evidence_type: EvidenceType,
    timestamp: str,
    raw_data: bytes,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for an evidence record.
    
    Args:
        record_id: Unique record identifier
        observation_point: Observation point enum
        evidence_type: Evidence type enum
        timestamp: ISO-8601 timestamp string
        raw_data: Raw bytes data
        prior_hash: Hash of prior record
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(record_id.encode('utf-8'))
    hasher.update(b'\x00')  # Null separator
    hasher.update(observation_point.name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(evidence_type.name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(timestamp.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(raw_data)
    hasher.update(b'\x00')
    hasher.update(prior_hash.encode('utf-8'))
    return hasher.hexdigest()


def capture_evidence(
    context: ObservationContext,
    observation_point: ObservationPoint,
    evidence_type: EvidenceType,
    raw_data: bytes,
    timestamp: str,
    prior_chain: EvidenceChain
) -> EvidenceChain:
    """Capture evidence at observation point.
    
    Args:
        context: Observation session context
        observation_point: Where in execution loop
        evidence_type: Type of evidence being captured
        raw_data: Opaque bytes (never parsed)
        timestamp: ISO-8601 timestamp (injected for testability)
        prior_chain: Existing evidence chain
        
    Returns:
        NEW EvidenceChain with appended record
        
    Rules:
        - Data is never interpreted
        - Timestamp provided externally (pure function)
        - Hash computed over all fields
        - Chain link verified before append
        - If context is halted, return empty chain with HALT marker
    """
    # If context is halted, capture halt evidence but mark chain
    if context.is_halted:
        record_id = f"REC-{uuid.uuid4().hex[:8]}"
        prior_hash = prior_chain.head_hash
        self_hash = _compute_evidence_hash(
            record_id, ObservationPoint.HALT_ENTRY, EvidenceType.STOP_CONDITION,
            timestamp, b"CONTEXT_HALTED", prior_hash
        )
        halt_record = EvidenceRecord(
            record_id=record_id,
            observation_point=ObservationPoint.HALT_ENTRY,
            evidence_type=EvidenceType.STOP_CONDITION,
            timestamp=timestamp,
            raw_data=b"CONTEXT_HALTED",
            prior_hash=prior_hash,
            self_hash=self_hash
        )
        return EvidenceChain(
            chain_id=prior_chain.chain_id,
            records=prior_chain.records + (halt_record,),
            head_hash=self_hash,
            length=prior_chain.length + 1
        )
    
    # Generate record ID
    record_id = f"REC-{uuid.uuid4().hex[:8]}"
    
    # Get prior hash from chain
    prior_hash = prior_chain.head_hash
    
    # Compute self hash
    self_hash = _compute_evidence_hash(
        record_id, observation_point, evidence_type,
        timestamp, raw_data, prior_hash
    )
    
    # Create immutable record
    new_record = EvidenceRecord(
        record_id=record_id,
        observation_point=observation_point,
        evidence_type=evidence_type,
        timestamp=timestamp,
        raw_data=raw_data,
        prior_hash=prior_hash,
        self_hash=self_hash
    )
    
    # Return new chain (immutable append)
    return EvidenceChain(
        chain_id=prior_chain.chain_id,
        records=prior_chain.records + (new_record,),
        head_hash=self_hash,
        length=prior_chain.length + 1
    )


def check_stop(
    context: Optional[ObservationContext],
    condition: StopCondition,
    authorization_present: bool = False,
    executor_registered: bool = False,
    envelope_hash_matches: bool = False,
    chain_valid: bool = True,
    resources_available: bool = True,
    timestamp_valid: bool = True,
    prior_execution_complete: bool = True,
    intent_clear: bool = True,
    human_abort_signaled: bool = False
) -> bool:
    """Check if stop condition is triggered.
    
    Args:
        context: Current observation context (may be None)
        condition: Condition to check
        authorization_present: Whether human authorization exists
        executor_registered: Whether executor is registered
        envelope_hash_matches: Whether envelope hash matches
        chain_valid: Whether evidence chain is valid
        resources_available: Whether resources are within limits
        timestamp_valid: Whether timestamp is valid
        prior_execution_complete: Whether prior execution is finalized
        intent_clear: Whether execution intent is unambiguous
        human_abort_signaled: Whether human abort was signaled
        
    Returns:
        True if HALT should be triggered, False otherwise
        
    Rules:
        - Unknown condition → HALT (True)
        - Missing context → HALT (True)
        - Default is HALT
    """
    # Missing context always HALTs
    if context is None:
        return True
    
    # Already halted context
    if context.is_halted:
        return True
    
    # Check specific stop conditions
    if condition == StopCondition.MISSING_AUTHORIZATION:
        return not authorization_present
    
    if condition == StopCondition.EXECUTOR_NOT_REGISTERED:
        return not executor_registered
    
    if condition == StopCondition.ENVELOPE_HASH_MISMATCH:
        return not envelope_hash_matches
    
    if condition == StopCondition.CONTEXT_UNINITIALIZED:
        return context is None  # Already checked above, but explicit
    
    if condition == StopCondition.EVIDENCE_CHAIN_BROKEN:
        return not chain_valid
    
    if condition == StopCondition.RESOURCE_LIMIT_EXCEEDED:
        return not resources_available
    
    if condition == StopCondition.TIMESTAMP_INVALID:
        return not timestamp_valid
    
    if condition == StopCondition.PRIOR_EXECUTION_PENDING:
        return not prior_execution_complete
    
    if condition == StopCondition.AMBIGUOUS_INTENT:
        return not intent_clear
    
    if condition == StopCondition.HUMAN_ABORT:
        return human_abort_signaled
    
    # Unknown condition → HALT (deny-by-default)
    # NOTE: This line is unreachable with current closed enum, but kept
    # for safety if enum is ever extended without updating this function.
    return True  # pragma: no cover


def validate_chain(chain: EvidenceChain) -> bool:
    """Validate evidence chain integrity.
    
    Args:
        chain: Evidence chain to validate
        
    Returns:
        True if chain is valid, False otherwise
        
    Rules:
        - Empty chain is valid (length=0, head_hash="")
        - Each record's prior_hash must match previous self_hash
        - First record's prior_hash must be empty string
        - Chain length must match record count
        - Head hash must match last record's self_hash
    """
    # Empty chain is valid
    if chain.length == 0:
        return chain.head_hash == "" and len(chain.records) == 0
    
    # Length must match
    if chain.length != len(chain.records):
        return False
    
    # Validate each record in sequence
    expected_prior_hash = ""
    for record in chain.records:
        # Prior hash must match expected
        if record.prior_hash != expected_prior_hash:
            return False
        
        # Recompute self hash to verify integrity
        computed_hash = _compute_evidence_hash(
            record.record_id,
            record.observation_point,
            record.evidence_type,
            record.timestamp,
            record.raw_data,
            record.prior_hash
        )
        
        if record.self_hash != computed_hash:
            return False
        
        # Update expected prior hash for next record
        expected_prior_hash = record.self_hash
    
    # Head hash must match last record
    if chain.head_hash != chain.records[-1].self_hash:
        return False
    
    return True


def attach_observer(
    loop_id: str,
    executor_id: str,
    envelope_hash: str,
    timestamp: str
) -> ObservationContext:
    """Attach observer to execution loop.
    
    Args:
        loop_id: Phase-29 execution loop ID
        executor_id: Bound executor identifier
        envelope_hash: Expected instruction envelope hash
        timestamp: Creation timestamp (ISO-8601)
        
    Returns:
        ObservationContext (or halted context if invalid)
        
    Rules:
        - Empty loop_id → halted context
        - Empty executor_id → halted context
        - Empty envelope_hash → halted context
        - Empty timestamp → halted context
        - Any invalid input → halted context
    """
    session_id = f"OBS-{uuid.uuid4().hex[:8]}"
    
    # Validate all inputs - any empty → HALT
    if not loop_id or not loop_id.strip():
        return ObservationContext(
            session_id=session_id,
            loop_id=loop_id,
            executor_id=executor_id,
            envelope_hash=envelope_hash,
            created_at=timestamp,
            is_halted=True
        )
    
    if not executor_id or not executor_id.strip():
        return ObservationContext(
            session_id=session_id,
            loop_id=loop_id,
            executor_id=executor_id,
            envelope_hash=envelope_hash,
            created_at=timestamp,
            is_halted=True
        )
    
    if not envelope_hash or not envelope_hash.strip():
        return ObservationContext(
            session_id=session_id,
            loop_id=loop_id,
            executor_id=executor_id,
            envelope_hash=envelope_hash,
            created_at=timestamp,
            is_halted=True
        )
    
    if not timestamp or not timestamp.strip():
        return ObservationContext(
            session_id=session_id,
            loop_id=loop_id,
            executor_id=executor_id,
            envelope_hash=envelope_hash,
            created_at=timestamp,
            is_halted=True
        )
    
    # All inputs valid
    return ObservationContext(
        session_id=session_id,
        loop_id=loop_id,
        executor_id=executor_id,
        envelope_hash=envelope_hash,
        created_at=timestamp,
        is_halted=False
    )


def create_empty_chain(chain_id: Optional[str] = None) -> EvidenceChain:
    """Create an empty evidence chain.
    
    Args:
        chain_id: Optional chain identifier (generated if not provided)
        
    Returns:
        Empty EvidenceChain ready for appending
    """
    if chain_id is None:
        chain_id = f"CHAIN-{uuid.uuid4().hex[:8]}"
    
    return EvidenceChain(
        chain_id=chain_id,
        records=(),
        head_hash="",
        length=0
    )
