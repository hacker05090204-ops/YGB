"""
impl_v1 Phase-31 Observation Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-31.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CAPTURE EVIDENCE.
THIS MODULE DOES NOT MODIFY EXECUTION.
THIS MODULE DOES NOT ATTACH OBSERVERS.

VALIDATION FUNCTIONS ONLY:
- validate_evidence_record
- validate_observation_context
- validate_chain_integrity
- is_stop_condition_met
- get_observation_state

DENY-BY-DEFAULT:
- None → DENY / False / HALT
- Empty → DENY / False / HALT
- Invalid → DENY / False / HALT
"""
import hashlib
import re
from typing import Optional

from .phase31_types import (
    ObservationPoint,
    EvidenceType,
    StopCondition,
)
from .phase31_context import (
    EvidenceRecord,
    ObservationContext,
    EvidenceChain,
)


# Regex pattern for valid record ID: EVIDENCE-{8+ hex chars}
_RECORD_ID_PATTERN = re.compile(r'^EVIDENCE-[a-fA-F0-9]{8,}$')

# Regex pattern for valid session ID: SESSION-{8+ hex chars}
_SESSION_ID_PATTERN = re.compile(r'^SESSION-[a-fA-F0-9]{8,}$')

# Regex pattern for valid chain ID: CHAIN-{8+ hex chars}
_CHAIN_ID_PATTERN = re.compile(r'^CHAIN-[a-fA-F0-9]{8,}$')


def validate_evidence_record(record: Optional[EvidenceRecord]) -> bool:
    """Validate an evidence record.
    
    Args:
        record: EvidenceRecord to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid record_id format → False
        - Invalid observation_point type → False
        - Invalid evidence_type type → False
        - Empty timestamp → False
        - Empty self_hash → False
    """
    # DENY-BY-DEFAULT: None
    if record is None:
        return False
    
    # Validate record_id format
    if not record.record_id or not isinstance(record.record_id, str):
        return False
    if not _RECORD_ID_PATTERN.match(record.record_id):
        return False
    
    # Validate observation_point is ObservationPoint
    if not isinstance(record.observation_point, ObservationPoint):
        return False
    
    # Validate evidence_type is EvidenceType
    if not isinstance(record.evidence_type, EvidenceType):
        return False
    
    # Validate timestamp
    if not record.timestamp or not isinstance(record.timestamp, str):
        return False
    if not record.timestamp.strip():
        return False
    
    # Validate raw_data is bytes
    if not isinstance(record.raw_data, bytes):
        return False
    
    # Validate self_hash
    if not record.self_hash or not isinstance(record.self_hash, str):
        return False
    if not record.self_hash.strip():
        return False
    
    # prior_hash can be empty for first record but must be string
    if not isinstance(record.prior_hash, str):
        return False
    
    return True


def validate_observation_context(context: Optional[ObservationContext]) -> bool:
    """Validate an observation context.
    
    Args:
        context: ObservationContext to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid session_id format → False
        - Empty fields → False
    """
    # DENY-BY-DEFAULT: None
    if context is None:
        return False
    
    # Validate session_id format
    if not context.session_id or not isinstance(context.session_id, str):
        return False
    if not _SESSION_ID_PATTERN.match(context.session_id):
        return False
    
    # Validate loop_id
    if not context.loop_id or not isinstance(context.loop_id, str):
        return False
    if not context.loop_id.strip():
        return False
    
    # Validate executor_id
    if not context.executor_id or not isinstance(context.executor_id, str):
        return False
    if not context.executor_id.strip():
        return False
    
    # Validate envelope_hash
    if not context.envelope_hash or not isinstance(context.envelope_hash, str):
        return False
    if not context.envelope_hash.strip():
        return False
    
    # Validate created_at
    if not context.created_at or not isinstance(context.created_at, str):
        return False
    if not context.created_at.strip():
        return False
    
    return True


def validate_chain_integrity(chain: Optional[EvidenceChain]) -> bool:
    """Validate evidence chain integrity.
    
    Args:
        chain: Evidence chain to validate
        
    Returns:
        True if chain is valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty chain: head_hash must be empty, length must be 0
        - Length must match records count
        - Hash chain must be valid (each record's prior_hash = previous self_hash)
    """
    # DENY-BY-DEFAULT: None
    if chain is None:
        return False
    
    # Validate chain_id format
    if not chain.chain_id or not isinstance(chain.chain_id, str):
        return False
    if not _CHAIN_ID_PATTERN.match(chain.chain_id):
        return False
    
    # Empty chain validation
    if len(chain.records) == 0:
        return chain.head_hash == "" and chain.length == 0
    
    # Length must match
    if chain.length != len(chain.records):
        return False
    
    # Validate each record and hash chain
    expected_prior_hash = ""
    last_self_hash = ""
    
    for record in chain.records:
        # Validate individual record
        if not validate_evidence_record(record):
            return False
        
        # Validate hash chain linkage
        if record.prior_hash != expected_prior_hash:
            return False
        
        # Verify self_hash is correctly computed
        computed_hash = _compute_evidence_hash(
            record.record_id,
            record.observation_point.name,
            record.evidence_type.name,
            record.timestamp,
            record.raw_data,
            record.prior_hash
        )
        
        if record.self_hash != computed_hash:
            return False
        
        expected_prior_hash = record.self_hash
        last_self_hash = record.self_hash
    
    # Head hash must match last record's self_hash
    if chain.head_hash != last_self_hash:
        return False
    
    return True


def _compute_evidence_hash(
    record_id: str,
    observation_point_name: str,
    evidence_type_name: str,
    timestamp: str,
    raw_data: bytes,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for evidence record validation.
    
    This is a PURE internal function.
    
    Args:
        record_id: Record ID
        observation_point_name: ObservationPoint name
        evidence_type_name: EvidenceType name
        timestamp: Record timestamp
        raw_data: Raw data bytes
        prior_hash: Prior record hash
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(record_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(observation_point_name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(evidence_type_name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(timestamp.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(raw_data)
    hasher.update(b'\x00')
    hasher.update(prior_hash.encode('utf-8'))
    return hasher.hexdigest()


def is_stop_condition_met(
    context: Optional[ObservationContext],
    condition: Optional[StopCondition]
) -> bool:
    """Check if stop condition is triggered.
    
    Args:
        context: Current observation context
        condition: Condition to check
        
    Returns:
        True if HALT should be triggered, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT (means HALT by default)
        - None context → True (HALT)
        - Invalid context → True (HALT)
        - None condition → True (HALT)
        - Non-StopCondition → True (HALT)
        - Valid condition → True (condition is met, must halt)
    """
    # DENY-BY-DEFAULT: None context → HALT
    if context is None:
        return True
    
    # Invalid context → HALT
    if not validate_observation_context(context):
        return True
    
    # DENY-BY-DEFAULT: None condition → HALT
    if condition is None:
        return True
    
    # Non-StopCondition → HALT
    if not isinstance(condition, StopCondition):
        return True
    
    # Valid condition means stop condition IS met → HALT
    return True


def get_observation_state(
    chain: Optional[EvidenceChain],
    context: Optional[ObservationContext]
) -> Optional[ObservationPoint]:
    """Get current observation state from chain.
    
    Args:
        chain: Evidence chain to examine
        context: Current observation context
        
    Returns:
        Most recent ObservationPoint, or None if invalid
        
    Rules:
        - DENY-BY-DEFAULT
        - None chain → None
        - Invalid chain → None
        - None context → None
        - Empty chain → None
        - Valid chain → last record's observation_point
    """
    # DENY-BY-DEFAULT: None chain
    if chain is None:
        return None
    
    # DENY-BY-DEFAULT: Invalid chain
    if not chain.chain_id or not isinstance(chain.chain_id, str):
        return None
    if not _CHAIN_ID_PATTERN.match(chain.chain_id):
        return None
    
    # DENY-BY-DEFAULT: None context
    if context is None:
        return None
    
    # Empty chain → None
    if len(chain.records) == 0:
        return None
    
    # Get last record's observation point
    last_record = chain.records[-1]
    if not isinstance(last_record.observation_point, ObservationPoint):
        return None
    
    return last_record.observation_point
