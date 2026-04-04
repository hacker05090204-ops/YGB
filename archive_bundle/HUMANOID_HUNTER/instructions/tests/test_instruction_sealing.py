"""
Tests for Phase-27 Instruction Sealing.

Tests:
- seal_instruction_envelope seals envelope
- Sealed envelope has hash
- validate_instruction_envelope validates
"""
import pytest


class TestSealInstructionEnvelope:
    """Test seal_instruction_envelope function."""

    def test_seal_sets_sealed_status(self):
        """Sealing envelope sets SEALED status."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope,
            seal_instruction_envelope
        )
        from HUMANOID_HUNTER.instructions.instruction_types import InstructionStatus
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
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        envelope = create_instruction_envelope(
            intent=intent,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )
        sealed = seal_instruction_envelope(envelope)

        assert sealed.status == InstructionStatus.SEALED

    def test_sealed_envelope_has_hash(self):
        """Sealed envelope has non-empty hash."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope,
            seal_instruction_envelope
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
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        envelope = create_instruction_envelope(
            intent=intent,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )
        sealed = seal_instruction_envelope(envelope)

        assert len(sealed.envelope_hash) > 0

    def test_already_sealed_returns_same(self):
        """Already sealed envelope returns same."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope,
            seal_instruction_envelope
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
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        envelope = create_instruction_envelope(
            intent=intent,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )
        sealed1 = seal_instruction_envelope(envelope)
        sealed2 = seal_instruction_envelope(sealed1)

        assert sealed1.envelope_hash == sealed2.envelope_hash


class TestValidateInstructionEnvelope:
    """Test validate_instruction_envelope function."""

    def test_valid_sealed_envelope_passes(self):
        """Valid sealed envelope passes validation."""
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
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        envelope = create_instruction_envelope(
            intent=intent,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )
        sealed = seal_instruction_envelope(envelope)

        result = validate_instruction_envelope(sealed, intent)
        assert result is True

    def test_unsealed_envelope_fails(self):
        """Unsealed envelope fails validation."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope,
            validate_instruction_envelope
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
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        envelope = create_instruction_envelope(
            intent=intent,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )

        # NOT sealed
        result = validate_instruction_envelope(envelope, intent)
        assert result is False
