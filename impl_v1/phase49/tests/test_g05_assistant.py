# test_g05_assistant.py
"""Tests for G05: Assistant Mode"""

import pytest
from impl_v1.phase49.governors.g05_assistant_mode import (
    AssistantController,
    AssistantMode,
    AssistantSession,
    MethodDecision,
    MethodExplanation,
    AssistantExplanation,
    AssistantContext,
    SessionLog,
    create_method_explanation,
    requires_human_approval,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_assistant_mode_2_members(self):
        assert len(AssistantMode) == 2

    def test_assistant_mode_members(self):
        assert {mode.name for mode in AssistantMode} == {"PASSIVE", "INTERACTIVE"}
    
    def test_method_decision_3_members(self):
        assert len(MethodDecision) == 3


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def test_method_explanation_frozen(self):
        exp = create_method_explanation(
            method_id="M1",
            method_name="Test",
            decision=MethodDecision.SELECTED,
            reason="Best match",
        )
        with pytest.raises(AttributeError):
            exp.method_id = "M2"


class TestCreateMethodExplanation:
    """Test method explanation creation."""
    
    def test_basic_creation(self):
        exp = create_method_explanation(
            method_id="M1",
            method_name="SQL Injection",
            decision=MethodDecision.SELECTED,
            reason="High confidence match",
        )
        assert exp.method_id == "M1"
        assert exp.method_name == "SQL Injection"
        assert exp.decision == MethodDecision.SELECTED
    
    def test_default_confidence(self):
        exp = create_method_explanation("M1", "Test", MethodDecision.SELECTED, "reason")
        assert exp.confidence == 0.5
    
    def test_confidence_clamping_high(self):
        exp = create_method_explanation("M1", "Test", MethodDecision.SELECTED, "r", 1.5)
        assert exp.confidence == 1.0
    
    def test_confidence_clamping_low(self):
        exp = create_method_explanation("M1", "Test", MethodDecision.SELECTED, "r", -0.5)
        assert exp.confidence == 0.0
    
    def test_alternatives(self):
        exp = create_method_explanation(
            "M1", "Test", MethodDecision.SELECTED, "r",
            alternatives=["M2", "M3"]
        )
        assert exp.alternatives == ("M2", "M3")


class TestAssistantContext:
    """Test assistant context."""
    
    def test_default_mode_is_passive(self):
        ctx = AssistantContext()
        assert ctx.mode == AssistantMode.PASSIVE
    
    def test_custom_mode(self):
        ctx = AssistantContext(AssistantMode.INTERACTIVE)
        assert ctx.mode == AssistantMode.INTERACTIVE
    
    def test_explain_selection(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "Selected", MethodDecision.SELECTED, "Best")
        rejected = [create_method_explanation("M2", "Rejected", MethodDecision.REJECTED, "Low conf")]
        amse = [create_method_explanation("M3", "Proposed", MethodDecision.PROPOSED, "New idea")]
        
        explanation = ctx.explain_selection(selected, rejected, amse)
        
        assert explanation.selected_method == selected
        assert len(explanation.rejected_methods) == 1
        assert len(explanation.amse_proposals) == 1
    
    def test_explanation_has_id(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "T", MethodDecision.SELECTED, "r")
        explanation = ctx.explain_selection(selected, [], [])
        assert explanation.explanation_id.startswith("EXP-")
    
    def test_explanations_logged(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "T", MethodDecision.SELECTED, "r")
        ctx.explain_selection(selected, [], [])
        ctx.explain_selection(selected, [], [])
        assert len(ctx.get_explanations()) == 2


class TestRequiresHumanApproval:
    """Test human approval requirement detection."""
    
    def test_explicit_approval_required(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "T", MethodDecision.SELECTED, "r")
        explanation = ctx.explain_selection(
            selected, [], [],
            requires_approval=True,
            approval_reason="Risky action"
        )
        required, reason = requires_human_approval(explanation)
        assert required
        assert reason == "Risky action"
    
    def test_low_confidence_requires_approval(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "T", MethodDecision.SELECTED, "r", 0.3)
        explanation = ctx.explain_selection(selected, [], [])
        required, reason = requires_human_approval(explanation)
        assert required
        assert "Low confidence" in reason
    
    def test_many_amse_proposals_require_approval(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "T", MethodDecision.SELECTED, "r", 0.8)
        amse = [
            create_method_explanation("M2", "P1", MethodDecision.PROPOSED, "r"),
            create_method_explanation("M3", "P2", MethodDecision.PROPOSED, "r"),
            create_method_explanation("M4", "P3", MethodDecision.PROPOSED, "r"),
        ]
        explanation = ctx.explain_selection(selected, [], amse)
        required, reason = requires_human_approval(explanation)
        assert required
        assert "AMSE" in reason
    
    def test_no_approval_needed(self):
        ctx = AssistantContext()
        selected = create_method_explanation("M1", "T", MethodDecision.SELECTED, "r", 0.8)
        explanation = ctx.explain_selection(selected, [], [])
        required, reason = requires_human_approval(explanation)
        assert not required
        assert reason == ""


class TestAssistantController:
    """Test assistant controller real-state-only behavior."""

    def test_autonomous_mode_rejected(self):
        controller = AssistantController()

        with pytest.raises(ValueError, match="AUTONOMOUS mode is not allowed"):
            controller.start_session("AUTONOMOUS")

    def test_unavailable_data_returns_exact_format(self):
        controller = AssistantController(
            state_provider=lambda _query: (False, "system status is offline")
        )

        session = controller.start_session(AssistantMode.PASSIVE)
        response = controller.handle_query(session.session_id, "What is the current status?")

        assert response == "Data unavailable: system status is offline"

    def test_query_truncated_in_logs(self, caplog):
        suffix = "TRUNCATE_THIS_SUFFIX"
        query = ("Q" * 120) + suffix
        controller = AssistantController(state_provider=lambda _query: "live system status")
        session = controller.start_session(AssistantMode.INTERACTIVE)

        with caplog.at_level("INFO"):
            controller.handle_query(session.session_id, query)

        query_logs = [
            record.getMessage()
            for record in caplog.records
            if "Assistant query session_id=" in record.getMessage()
        ]
        assert query_logs
        assert any(query[:120] in message for message in query_logs)
        assert all(suffix not in message for message in query_logs)

    def test_start_session_returns_assistant_session(self):
        controller = AssistantController(state_provider=lambda _query: "runtime ok")

        session = controller.start_session(AssistantMode.PASSIVE)

        assert isinstance(session, AssistantSession)
        assert session.turn_count == 0
        assert session.last_query is None

    def test_session_log_is_bounded_to_1000_sessions(self):
        controller = AssistantController(state_provider=lambda _query: "runtime ok")

        for _ in range(1005):
            controller.start_session(AssistantMode.PASSIVE)

        assert isinstance(controller.session_log, SessionLog)
        assert len(controller.session_log) == 1000
