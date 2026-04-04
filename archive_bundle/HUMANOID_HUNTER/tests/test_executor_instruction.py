"""
Tests for Phase-20 Executor Instruction.

Tests:
- Build executor instruction
- Instruction envelope immutability
"""
import pytest


class TestBuildExecutorInstruction:
    """Test executor instruction building."""

    def test_build_instruction_creates_envelope(self):
        """Build instruction creates valid envelope."""
        from HUMANOID_HUNTER.interface.executor_adapter import build_executor_instruction
        from HUMANOID_HUNTER.interface.executor_types import ExecutorCommandType

        envelope = build_executor_instruction(
            execution_id="EXEC-001",
            command_type=ExecutorCommandType.NAVIGATE,
            target_url="https://example.com",
            target_selector="",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        assert envelope.execution_id == "EXEC-001"
        assert envelope.command_type == ExecutorCommandType.NAVIGATE
        assert envelope.instruction_id is not None

    def test_instruction_id_is_unique(self):
        """Each instruction has unique ID."""
        from HUMANOID_HUNTER.interface.executor_adapter import build_executor_instruction
        from HUMANOID_HUNTER.interface.executor_types import ExecutorCommandType

        env1 = build_executor_instruction(
            execution_id="EXEC-001",
            command_type=ExecutorCommandType.CLICK,
            target_url="",
            target_selector="#button",
            timestamp="2026-01-25T15:30:00-05:00"
        )
        env2 = build_executor_instruction(
            execution_id="EXEC-002",
            command_type=ExecutorCommandType.CLICK,
            target_url="",
            target_selector="#button2",
            timestamp="2026-01-25T15:31:00-05:00"
        )

        assert env1.instruction_id != env2.instruction_id


class TestInstructionEnvelopeFrozen:
    """Test instruction envelope immutability."""

    def test_envelope_is_frozen(self):
        """ExecutorInstructionEnvelope is frozen."""
        from HUMANOID_HUNTER.interface.executor_adapter import build_executor_instruction
        from HUMANOID_HUNTER.interface.executor_types import ExecutorCommandType

        envelope = build_executor_instruction(
            execution_id="EXEC-001",
            command_type=ExecutorCommandType.READ,
            target_url="",
            target_selector="",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        with pytest.raises(Exception):
            envelope.execution_id = "MODIFIED"
