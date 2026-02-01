"""
impl_v1 Phase-31 Observation Context.

NON-AUTHORITATIVE MIRROR of governance Phase-31.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- EvidenceRecord: 7 fields
- ObservationContext: 5 fields
- EvidenceChain: 4 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Tuple

from .phase31_types import ObservationPoint, EvidenceType


@dataclass(frozen=True)
class EvidenceRecord:
    """Single immutable evidence entry.
    
    All fields captured at observation time.
    HashChain links to prior evidence.
    
    Attributes:
        record_id: Unique identifier
        observation_point: Where in execution loop
        evidence_type: Type of evidence captured
        timestamp: ISO-8601 format
        raw_data: Opaque bytes (never parsed)
        prior_hash: Link to previous record (empty if first)
        self_hash: SHA-256 of this record
    """
    record_id: str
    observation_point: ObservationPoint
    evidence_type: EvidenceType
    timestamp: str
    raw_data: bytes
    prior_hash: str
    self_hash: str


@dataclass(frozen=True)
class ObservationContext:
    """Context for a single observation session.
    
    Immutable once created.
    
    Attributes:
        session_id: Unique session identifier
        loop_id: From Phase-29 ExecutionLoopContext
        executor_id: Executor being observed
        envelope_hash: Expected instruction hash
        created_at: Session start time (ISO-8601)
    """
    session_id: str
    loop_id: str
    executor_id: str
    envelope_hash: str
    created_at: str


@dataclass(frozen=True)
class EvidenceChain:
    """Append-only chain of evidence records.
    
    Immutable structure - new records create new chain.
    
    Attributes:
        chain_id: Unique chain identifier
        records: Immutable tuple of EvidenceRecord
        head_hash: Hash of most recent record (empty if empty)
        length: Number of records
    """
    chain_id: str
    records: Tuple[EvidenceRecord, ...]
    head_hash: str
    length: int
