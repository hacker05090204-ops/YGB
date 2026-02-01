"""
Phase-20 Executor Adapter.

This module provides executor adapter functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS AN INTERFACE LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
THE EXECUTOR CANNOT DECIDE SUCCESS.
"""
import uuid

from .executor_types import ExecutorCommandType, ExecutorResponseType
from .executor_context import (
    ExecutorInstructionEnvelope,
    ExecutorResponseEnvelope,
    ExecutionSafetyResult
)


def generate_instruction_id() -> str:
    """Generate unique instruction ID.
    
    Returns:
        Unique instruction ID string
    """
    return f"INSTR-{uuid.uuid4().hex[:12]}"


def build_executor_instruction(
    execution_id: str,
    command_type: ExecutorCommandType,
    target_url: str,
    target_selector: str,
    timestamp: str,
    timeout_ms: int = 30000
) -> ExecutorInstructionEnvelope:
    """Build executor instruction envelope.
    
    Args:
        execution_id: Execution ID from Phase-18
        command_type: Command to execute
        target_url: Target URL
        target_selector: CSS selector
        timestamp: ISO timestamp
        timeout_ms: Timeout in milliseconds
        
    Returns:
        ExecutorInstructionEnvelope
    """
    return ExecutorInstructionEnvelope(
        instruction_id=generate_instruction_id(),
        execution_id=execution_id,
        command_type=command_type,
        target_url=target_url,
        target_selector=target_selector,
        timestamp=timestamp,
        timeout_ms=timeout_ms
    )


def validate_executor_response(
    response: ExecutorResponseEnvelope,
    expected_instruction_id: str
) -> ExecutionSafetyResult:
    """Validate executor response.
    
    Args:
        response: Executor response envelope
        expected_instruction_id: Expected instruction ID
        
    Returns:
        ExecutionSafetyResult
    """
    # Empty instruction_id → DENIED
    if not response.instruction_id:
        return ExecutionSafetyResult(
            is_safe=False,
            reason_code="EXE-003",
            reason_description="Missing instruction_id"
        )
    
    # instruction_id mismatch → DENIED
    if response.instruction_id != expected_instruction_id:
        return ExecutionSafetyResult(
            is_safe=False,
            reason_code="EXE-002",
            reason_description=f"instruction_id mismatch: {response.instruction_id} != {expected_instruction_id}"
        )
    
    # SUCCESS without evidence_hash → DENIED
    if response.response_type == ExecutorResponseType.SUCCESS:
        if not response.evidence_hash:
            return ExecutionSafetyResult(
                is_safe=False,
                reason_code="EXE-001",
                reason_description="SUCCESS without evidence_hash"
            )
    
    # All other responses are safe (executor reporting status)
    return ExecutionSafetyResult(
        is_safe=True,
        reason_code="EXE-OK",
        reason_description="Response validated"
    )


def enforce_executor_safety(
    instruction: ExecutorInstructionEnvelope,
    response: ExecutorResponseEnvelope
) -> bool:
    """Enforce executor safety.
    
    Args:
        instruction: Original instruction
        response: Executor response
        
    Returns:
        True if safe, False otherwise
    """
    result = validate_executor_response(response, instruction.instruction_id)
    return result.is_safe
