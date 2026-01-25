"""
Phase-27 Instruction Context.

This module defines frozen dataclasses for instruction synthesis.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass
from typing import Tuple, FrozenSet, Mapping, Any

from .instruction_types import InstructionType, InstructionStatus


@dataclass(frozen=True)
class ExecutionInstruction:
    """Immutable execution instruction.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        instruction_id: Unique instruction identifier
        plan_step_id: Corresponding plan step ID
        instruction_type: Type of instruction
        parameters: Instruction parameters (immutable mapping)
        evidence_required: Evidence requirements for this instruction
    """
    instruction_id: str
    plan_step_id: str
    instruction_type: InstructionType
    parameters: Mapping[str, Any]
    evidence_required: FrozenSet[str]


@dataclass(frozen=True)
class InstructionEnvelope:
    """Immutable instruction envelope.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        intent_id: Bound orchestration intent ID
        readiness_hash: Hash from readiness decision
        instructions: Tuple of ExecutionInstructions
        status: Envelope status (CREATED, SEALED, REJECTED)
        envelope_hash: Cryptographic hash once sealed
    """
    intent_id: str
    readiness_hash: str
    instructions: Tuple[ExecutionInstruction, ...]
    status: InstructionStatus
    envelope_hash: str
