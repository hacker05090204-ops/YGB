"""
Phase-27 Execution Instruction Synthesis & Immutable Command Envelope.

This module provides instruction synthesis governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Instructions describe execution
- They never authorize it
- One instruction per plan step
- No extra actions, no reordering, no mutation

Exports:
    Enums (CLOSED):
        InstructionType: NAVIGATE, CLICK, TYPE, WAIT, SCROLL, SCREENSHOT
        InstructionStatus: CREATED, SEALED, REJECTED
    
    Dataclasses (all frozen=True):
        ExecutionInstruction: Immutable execution instruction
        InstructionEnvelope: Immutable instruction envelope
    
    Functions (pure, deterministic):
        synthesize_instructions: Generate instructions from intent
        create_instruction_envelope: Create envelope
        seal_instruction_envelope: Seal envelope
        validate_instruction_envelope: Validate envelope
"""
from .instruction_types import (
    InstructionType,
    InstructionStatus
)
from .instruction_context import (
    ExecutionInstruction,
    InstructionEnvelope
)
from .instruction_engine import (
    synthesize_instructions,
    create_instruction_envelope,
    seal_instruction_envelope,
    validate_instruction_envelope
)

__all__ = [
    # Enums
    "InstructionType",
    "InstructionStatus",
    # Dataclasses
    "ExecutionInstruction",
    "InstructionEnvelope",
    # Functions
    "synthesize_instructions",
    "create_instruction_envelope",
    "seal_instruction_envelope",
    "validate_instruction_envelope",
]
