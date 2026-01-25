"""
Phase-27 Instruction Engine.

This module provides instruction synthesis functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- One instruction per plan step
- No extra actions
- No reordering
- No mutation
- Instructions describe execution, never authorize it
"""
import hashlib
from typing import Tuple, Optional

from .instruction_types import InstructionType, InstructionStatus
from .instruction_context import ExecutionInstruction, InstructionEnvelope

# Import Phase-25 types
from HUMANOID_HUNTER.orchestration import OrchestrationIntent, OrchestrationIntentState

# Import Phase-24 types (for PlannedActionType mapping)
from HUMANOID_HUNTER.planning import PlannedActionType


# Map PlannedActionType to InstructionType
_ACTION_TO_INSTRUCTION = {
    PlannedActionType.NAVIGATE: InstructionType.NAVIGATE,
    PlannedActionType.CLICK: InstructionType.CLICK,
    PlannedActionType.TYPE: InstructionType.TYPE,
    PlannedActionType.WAIT: InstructionType.WAIT,
    PlannedActionType.SCROLL: InstructionType.SCROLL,
    PlannedActionType.SCREENSHOT: InstructionType.SCREENSHOT,
}


def synthesize_instructions(
    intent: Optional[OrchestrationIntent]
) -> Tuple[ExecutionInstruction, ...]:
    """Synthesize execution instructions from orchestration intent.
    
    Args:
        intent: Sealed OrchestrationIntent
        
    Returns:
        Tuple of ExecutionInstructions (one per plan step)
        
    Rules:
        - None intent → empty tuple
        - Unsealed intent → empty tuple
        - One instruction per plan step
        - No extra actions
        - No reordering
    """
    # None intent → empty tuple
    if intent is None:
        return ()
    
    # Unsealed intent → empty tuple (deny-by-default)
    if intent.state != OrchestrationIntentState.SEALED:
        return ()
    
    plan = intent.execution_plan
    instructions = []
    
    for idx, step in enumerate(plan.steps):
        instruction_type = _ACTION_TO_INSTRUCTION.get(step.action_type)
        
        # Unknown action type → skip (shouldn't happen with closed enums)
        if instruction_type is None:
            continue
        
        instruction = ExecutionInstruction(
            instruction_id=f"INSTR-{intent.intent_id}-{idx:03d}",
            plan_step_id=step.step_id,
            instruction_type=instruction_type,
            parameters=step.parameters,
            evidence_required=intent.evidence_requirements
        )
        instructions.append(instruction)
    
    return tuple(instructions)


def create_instruction_envelope(
    intent: OrchestrationIntent,
    instructions: Tuple[ExecutionInstruction, ...],
    readiness_hash: str
) -> InstructionEnvelope:
    """Create instruction envelope with CREATED status.
    
    Args:
        intent: OrchestrationIntent
        instructions: Tuple of ExecutionInstructions
        readiness_hash: Hash from readiness decision
        
    Returns:
        InstructionEnvelope with CREATED status
    """
    return InstructionEnvelope(
        intent_id=intent.intent_id,
        readiness_hash=readiness_hash,
        instructions=instructions,
        status=InstructionStatus.CREATED,
        envelope_hash=""
    )


def _compute_envelope_hash(envelope: InstructionEnvelope) -> str:
    """Compute cryptographic hash for envelope.
    
    Args:
        envelope: InstructionEnvelope
        
    Returns:
        SHA-256 hash string
    """
    content = f"{envelope.intent_id}:{envelope.readiness_hash}:{len(envelope.instructions)}"
    for instr in envelope.instructions:
        content += f":{instr.instruction_id}:{instr.plan_step_id}"
    
    return hashlib.sha256(content.encode()).hexdigest()


def seal_instruction_envelope(
    envelope: InstructionEnvelope
) -> InstructionEnvelope:
    """Seal instruction envelope.
    
    Args:
        envelope: InstructionEnvelope to seal
        
    Returns:
        New InstructionEnvelope with SEALED status and hash
        
    Rules:
        - Already SEALED → return same envelope
        - REJECTED → return same envelope
        - CREATED → seal with hash
    """
    # Already sealed or rejected
    if envelope.status != InstructionStatus.CREATED:
        return envelope
    
    # Compute hash and seal
    envelope_hash = _compute_envelope_hash(envelope)
    
    return InstructionEnvelope(
        intent_id=envelope.intent_id,
        readiness_hash=envelope.readiness_hash,
        instructions=envelope.instructions,
        status=InstructionStatus.SEALED,
        envelope_hash=envelope_hash
    )


def validate_instruction_envelope(
    envelope: InstructionEnvelope,
    intent: OrchestrationIntent
) -> bool:
    """Validate instruction envelope against intent.
    
    Args:
        envelope: InstructionEnvelope to validate
        intent: OrchestrationIntent to validate against
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - Must be SEALED
        - Intent ID must match
        - Instruction count must match plan step count
    """
    # Must be SEALED
    if envelope.status != InstructionStatus.SEALED:
        return False
    
    # Intent ID must match
    if envelope.intent_id != intent.intent_id:
        return False
    
    # Instruction count must match plan step count
    if len(envelope.instructions) != len(intent.execution_plan.steps):
        return False
    
    return True
