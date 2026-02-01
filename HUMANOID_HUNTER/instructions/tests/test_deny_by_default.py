"""
Tests for Phase-27 Deny-By-Default.

Tests:
- Intent mismatch → REJECT
- Unsealed intent → REJECT
- None input → REJECT
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_intent_mismatch_fails(self):
        """Intent ID mismatch fails validation."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope,
            seal_instruction_envelope, validate_instruction_envelope
        )
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlannedActionType, PlanRiskLevel
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step,))
        intent1 = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )
        intent2 = OrchestrationIntent(
            intent_id="INTENT-002",  # Different ID!
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent1)
        envelope = create_instruction_envelope(
            intent=intent1,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )
        sealed = seal_instruction_envelope(envelope)

        # Validate against different intent
        result = validate_instruction_envelope(sealed, intent2)
        assert result is False

    def test_unsealed_intent_fails(self):
        """Unsealed intent fails instruction synthesis."""
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
            state=OrchestrationIntentState.DRAFT  # NOT sealed!
        )

        # Should return empty tuple for safety
        instructions = synthesize_instructions(intent)
        assert len(instructions) == 0

    def test_none_intent_returns_empty(self):
        """None intent returns empty instructions."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions

        instructions = synthesize_instructions(None)
        assert len(instructions) == 0

    def test_rejected_envelope_fails_validation(self):
        """REJECTED envelope fails validation."""
        from HUMANOID_HUNTER.instructions.instruction_context import InstructionEnvelope
        from HUMANOID_HUNTER.instructions.instruction_types import InstructionStatus
        from HUMANOID_HUNTER.instructions.instruction_engine import validate_instruction_envelope
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

        # Create a rejected envelope directly
        envelope = InstructionEnvelope(
            intent_id="INTENT-001",
            readiness_hash="READY-HASH-001",
            instructions=(),
            status=InstructionStatus.REJECTED,
            envelope_hash=""
        )

        result = validate_instruction_envelope(envelope, intent)
        assert result is False


class TestInstructionCountMismatch:
    """Test instruction count mismatch detection."""

    def test_instruction_count_mismatch_fails(self):
        """Instruction count mismatch fails validation."""
        from HUMANOID_HUNTER.instructions.instruction_context import (
            InstructionEnvelope, ExecutionInstruction
        )
        from HUMANOID_HUNTER.instructions.instruction_types import (
            InstructionStatus, InstructionType
        )
        from HUMANOID_HUNTER.instructions.instruction_engine import validate_instruction_envelope
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlannedActionType, PlanRiskLevel
        )

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step1, step2))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK, PlannedActionType.NAVIGATE}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        # Create envelope with only 1 instruction when plan has 2 steps
        instruction = ExecutionInstruction(
            instruction_id="INSTR-001",
            plan_step_id="STEP-001",
            instruction_type=InstructionType.CLICK,
            parameters={"selector": "#submit"},
            evidence_required=frozenset({"screenshot"})
        )

        envelope = InstructionEnvelope(
            intent_id="INTENT-001",
            readiness_hash="READY-HASH-001",
            instructions=(instruction,),  # Only 1!
            status=InstructionStatus.SEALED,
            envelope_hash="SOME-HASH"
        )

        result = validate_instruction_envelope(envelope, intent)
        assert result is False
