"""
test_auto_mode.py — Auto Mode Controller Tests

Tests for Phase 6: Shadow-only enforcement, condition evaluation, export approval
"""

import pytest
from backend.governance.auto_mode_controller import (
    AutoModeController, AutoModeCondition, AutoModeState
)


class TestAutoModeShadowOnly:
    """Tests that auto-mode is ALWAYS shadow-only."""

    def test_shadow_only_default(self):
        ctrl = AutoModeController()
        assert ctrl.is_shadow_only is True

    def test_shadow_only_after_activation(self):
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(
            integrity_score=98.0,
            has_containment_24h=False,
            drift_stable=True,
            dataset_balanced=True,
            storage_healthy=True,
        )
        ctrl.request_activation()
        assert ctrl.is_shadow_only is True

    def test_cannot_disable_shadow(self):
        assert AutoModeController.CAN_DISABLE_SHADOW is False

    def test_cannot_auto_export(self):
        assert AutoModeController.CAN_AUTO_EXPORT is False

    def test_cannot_auto_submit(self):
        assert AutoModeController.CAN_AUTO_SUBMIT is False


class TestConditionEvaluation:
    """Tests that all 5 conditions are evaluated correctly."""

    def test_all_conditions_met(self):
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=98.0,
            has_containment_24h=False,
            drift_stable=True,
            dataset_balanced=True,
            storage_healthy=True,
        )
        assert cond.all_conditions_met is True

    def test_integrity_below_95_blocks(self):
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=90.0,
            has_containment_24h=False,
            drift_stable=True,
            dataset_balanced=True,
            storage_healthy=True,
        )
        assert cond.all_conditions_met is False
        assert "Integrity score below 95" in cond.blocked_reasons

    def test_containment_blocks(self):
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=98.0,
            has_containment_24h=True,
            drift_stable=True,
            dataset_balanced=True,
            storage_healthy=True,
        )
        assert cond.all_conditions_met is False
        assert "Containment event in last 24h" in cond.blocked_reasons

    def test_drift_unstable_blocks(self):
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=98.0,
            has_containment_24h=False,
            drift_stable=False,
            dataset_balanced=True,
            storage_healthy=True,
        )
        assert cond.all_conditions_met is False

    def test_multiple_blocks(self):
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=80.0,
            has_containment_24h=True,
            drift_stable=False,
            dataset_balanced=False,
            storage_healthy=False,
        )
        assert len(cond.blocked_reasons) == 5


class TestActivation:
    """Tests activation/deactivation flow."""

    def test_activation_with_all_conditions(self):
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(98.0, False, True, True, True)
        state = ctrl.request_activation()
        assert state.enabled is True
        assert state.shadow_only is True

    def test_activation_blocked_without_conditions(self):
        ctrl = AutoModeController()
        state = ctrl.request_activation()
        assert state.enabled is False

    def test_deactivation(self):
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(98.0, False, True, True, True)
        ctrl.request_activation()
        state = ctrl.deactivate()
        assert state.enabled is False

    def test_activation_log_populated(self):
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(98.0, False, True, True, True)
        ctrl.request_activation()
        assert len(ctrl.activation_log) > 0


class TestExportApproval:
    """Tests that export always requires manual approval."""

    def test_export_blocked_without_approval(self):
        ctrl = AutoModeController()
        result = ctrl.request_export_approval("RPT-001", user_approved=False)
        assert result is False

    def test_export_allowed_with_approval(self):
        ctrl = AutoModeController()
        result = ctrl.request_export_approval("RPT-001", user_approved=True)
        assert result is True

    def test_export_requires_approval_always(self):
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(98.0, False, True, True, True)
        ctrl.request_activation()
        assert ctrl.state.export_requires_approval is True
