"""
Phase-31 Observation Context.

This module defines frozen dataclasses for observation and evidence capture.

ALL DATACLASSES ARE FROZEN - No mutation permitted after creation.

THIS IS AN OBSERVATION LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
IT DOES NOT INTERPRET ANYTHING.

CORE RULES:
- All evidence is immutable
- Evidence chain is append-only (new chain on append)
- Raw data is never parsed
"""
from dataclasses import dataclass
from typing import Tuple

from .observation_types import ObservationPoint, EvidenceType


@dataclass(frozen=True)
class EvidenceRecord:
    """Single immutable evidence entry.
    
    All fields captured at observation time.
    Hash chain links to prior evidence.
    
    Attributes:
        record_id: Unique identifier for this record
        observation_point: Where in execution loop this was captured
        evidence_type: Type of evidence captured
        timestamp: ISO-8601 format timestamp (captured at observation)
        raw_data: Opaque bytes (NEVER parsed)
        prior_hash: Hash of the previous record (empty string for first)
        self_hash: SHA-256 hash of this record
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
        executor_id: Bound executor identifier
        envelope_hash: Expected instruction envelope hash
        created_at: Session creation timestamp (ISO-8601)
        is_halted: Whether observation session is halted
    """
    session_id: str
    loop_id: str
    executor_id: str
    envelope_hash: str
    created_at: str
    is_halted: bool = False


@dataclass(frozen=True)
class EvidenceChain:
    """Append-only chain of evidence records.
    
    Immutable structure - new records create new chain.
    
    Attributes:
        chain_id: Unique chain identifier
        records: Immutable tuple of EvidenceRecord
        head_hash: Hash of most recent record (empty string if empty)
        length: Number of records in chain
    """
    chain_id: str
    records: Tuple[EvidenceRecord, ...]
    head_hash: str
    length: int
