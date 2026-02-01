"""
Phase-14 Connector Context.

This module defines frozen dataclasses for connector data structures.

All dataclasses are frozen=True for immutability.
All values are READ-ONLY pass-through - NO modification allowed.
"""
from dataclasses import dataclass
from typing import Optional

from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
from python.phase13_handoff.handoff_types import ReadinessState, HumanPresence
from python.phase13_handoff.readiness_engine import HandoffDecision
from .connector_types import ConnectorRequestType


@dataclass(frozen=True)
class ConnectorInput:
    """Immutable input for connector.
    
    Attributes:
        bug_id: Unique bug identifier
        target_id: Target being evaluated
        request_type: Type of request
        timestamp: ISO timestamp of request
        handoff_decision: From Phase-13 (optional)
    """
    bug_id: str
    target_id: str
    request_type: ConnectorRequestType
    timestamp: str
    handoff_decision: Optional[HandoffDecision] = None


@dataclass(frozen=True)
class ConnectorOutput:
    """Immutable output from connector.
    
    All fields are READ-ONLY pass-through from backend phases.
    
    Attributes:
        bug_id: Bug identifier (pass-through)
        target_id: Target identifier (pass-through)
        confidence: From Phase-12 (read-only)
        evidence_state: From Phase-12 (read-only)
        readiness: From Phase-13 (read-only)
        human_presence: From Phase-13 (read-only)
        can_proceed: From Phase-13 (pass-through)
        is_blocked: From Phase-13 (pass-through)
        blockers: Active blockers list
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
    """
    bug_id: str
    target_id: str
    confidence: ConfidenceLevel
    evidence_state: EvidenceState
    readiness: ReadinessState
    human_presence: HumanPresence
    can_proceed: bool
    is_blocked: bool
    blockers: tuple
    reason_code: str
    reason_description: str


@dataclass(frozen=True)
class ConnectorResult:
    """Immutable result container.
    
    Attributes:
        input: Original input (read-only)
        output: Connector output (read-only)
        success: Whether pipeline succeeded
        error_code: Error code if failed
        error_description: Error description if failed
    """
    input: ConnectorInput
    output: ConnectorOutput
    success: bool
    error_code: Optional[str] = None
    error_description: Optional[str] = None
