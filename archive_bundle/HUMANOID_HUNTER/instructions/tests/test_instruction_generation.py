"""
Tests for Phase-27 Instruction Generation.

Tests:
- synthesize_instructions generates one per step
- No extra actions added
- No reordering
"""
import pytest


class TestSynthesizeInstructions:
    """Test synthesize_instructions function."""

    def test_generates_one_instruction_per_step(self):
        """One instruction per plan step."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlannedActionType, PlanRiskLevel
        )

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step1, step2))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.NAVIGATE, PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        assert len(instructions) == 2

    def test_preserves_step_order(self):
        """Instructions preserve step order."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlannedActionType, PlanRiskLevel
        )

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step1, step2))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.NAVIGATE, PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        assert instructions[0].plan_step_id == "STEP-001"
        assert instructions[1].plan_step_id == "STEP-002"

    def test_empty_plan_returns_empty_tuple(self):
        """Empty plan returns empty tuple."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        assert len(instructions) == 0

    def test_unknown_action_type_skipped(self):
        """Unknown action type (UPLOAD) is skipped."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlannedActionType, PlanRiskLevel
        )

        # UPLOAD is in Phase-24 but not in Phase-27 InstructionType
        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.UPLOAD,
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step,))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.UPLOAD}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        # UPLOAD is skipped - no instruction generated
        assert len(instructions) == 0


class TestInstructionStructure:
    """Test ExecutionInstruction structure."""

    def test_instruction_creation(self):
        """ExecutionInstruction can be created."""
        from HUMANOID_HUNTER.instructions.instruction_context import ExecutionInstruction
        from HUMANOID_HUNTER.instructions.instruction_types import InstructionType

        instruction = ExecutionInstruction(
            instruction_id="INSTR-001",
            plan_step_id="STEP-001",
            instruction_type=InstructionType.CLICK,
            parameters={"selector": "#submit"},
            evidence_required=frozenset({"screenshot"})
        )

        assert instruction.instruction_id == "INSTR-001"
        assert instruction.instruction_type == InstructionType.CLICK

    def test_instruction_frozen(self):
        """ExecutionInstruction is frozen."""
        from HUMANOID_HUNTER.instructions.instruction_context import ExecutionInstruction
        from HUMANOID_HUNTER.instructions.instruction_types import InstructionType

        instruction = ExecutionInstruction(
            instruction_id="INSTR-001",
            plan_step_id="STEP-001",
            instruction_type=InstructionType.CLICK,
            parameters={"selector": "#submit"},
            evidence_required=frozenset({"screenshot"})
        )

        with pytest.raises(Exception):
            instruction.instruction_id = "MODIFIED"


class TestEnumClosure:
    """Test enum closure."""

    def test_instruction_type_has_six_members(self):
        """InstructionType has exactly 6 members."""
        from HUMANOID_HUNTER.instructions.instruction_types import InstructionType
        assert len(InstructionType) == 6

    def test_instruction_status_has_three_members(self):
        """InstructionStatus has exactly 3 members."""
        from HUMANOID_HUNTER.instructions.instruction_types import InstructionStatus
        assert len(InstructionStatus) == 3
