"""
Tests for Phase-27 Instruction Plan Binding.

Tests:
- Instructions match plan steps
- InstructionEnvelope binds to intent
"""
import pytest


class TestInstructionPlanBinding:
    """Test instruction plan binding."""

    def test_instruction_matches_plan_step(self):
        """Instruction matches plan step parameters."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions
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
        assert instructions[0].parameters == {"selector": "#submit"}

    def test_instruction_inherits_evidence_requirements(self):
        """Instruction inherits evidence requirements from intent."""
        from HUMANOID_HUNTER.instructions.instruction_engine import synthesize_instructions
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
            evidence_requirements=frozenset({"screenshot", "dom_hash"}),
            created_at="2026-01-25T18:01:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        instructions = synthesize_instructions(intent)
        assert instructions[0].evidence_required == frozenset({"screenshot", "dom_hash"})


class TestInstructionEnvelopeBinding:
    """Test InstructionEnvelope binding."""

    def test_envelope_binds_to_intent(self):
        """InstructionEnvelope binds to intent_id."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope
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

        assert envelope.intent_id == "INTENT-001"

    def test_envelope_contains_all_instructions(self):
        """InstructionEnvelope contains all instructions."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope
        )
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
        envelope = create_instruction_envelope(
            intent=intent,
            instructions=instructions,
            readiness_hash="READY-HASH-001"
        )

        assert len(envelope.instructions) == 2

    def test_envelope_frozen(self):
        """InstructionEnvelope is frozen."""
        from HUMANOID_HUNTER.instructions.instruction_engine import (
            synthesize_instructions, create_instruction_envelope
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

        with pytest.raises(Exception):
            envelope.intent_id = "MODIFIED"
