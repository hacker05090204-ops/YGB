"""
Tests for Real-Data Rollout Governor.

Covers:
  - Staged rollout through all 4 stages
  - Regression block (FPR regression)
  - Drift block (JS divergence)
  - Determinism block
  - Backtest block
  - Mode promotion block (class imbalance / label quality)
  - State persistence and recovery
  - Reset behavior
"""

import pytest
import json
import os
import tempfile
from unittest.mock import patch
from pathlib import Path

from governance.real_data_rollout_governor import (
    RolloutStage,
    BlockReason,
    CycleMetrics,
    RolloutState,
    evaluate_blocking_conditions,
    evaluate_cycle,
    load_state,
    save_state,
    get_current_status,
    reset_state,
    ROLLOUT_STAGES,
    REQUIRED_STABLE_CYCLES,
    LABEL_QUALITY_FLOOR,
    CLASS_IMBALANCE_MAX,
    DISTRIBUTION_SHIFT_THRESHOLD,
    UNKNOWN_TOKEN_THRESHOLD,
    FPR_REGRESSION_DELTA_THRESHOLD,
)


def _make_stable_metrics(cycle_id: str = "CYC-001") -> CycleMetrics:
    """Create metrics that pass all blocking checks."""
    return CycleMetrics(
        cycle_id=cycle_id,
        timestamp="2026-01-01T00:00:00Z",
        label_quality=0.95,
        class_imbalance_ratio=2.0,
        js_divergence=0.05,
        unknown_token_ratio=0.01,
        feature_mismatch_ratio=0.01,
        fpr_current=0.03,
        fpr_baseline=0.03,
        drift_guard_pass=True,
        regression_gate_pass=True,
        determinism_gate_pass=True,
        backtest_gate_pass=True,
    )


@pytest.fixture(autouse=True)
def _clean_state(tmp_path):
    """Ensure each test has a clean state file."""
    state_file = tmp_path / "rollout_governor_state.json"
    with patch("governance.real_data_rollout_governor._state_path", return_value=state_file):
        yield state_file


class TestBlockingConditions:
    """Test individual blocking checks."""

    def test_stable_metrics_no_blocks(self):
        metrics = _make_stable_metrics()
        reasons = evaluate_blocking_conditions(metrics)
        assert reasons == []

    def test_label_quality_low_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "label_quality": 0.85})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.LABEL_QUALITY_LOW in reasons

    def test_class_imbalance_high_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "class_imbalance_ratio": 15.0})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.CLASS_IMBALANCE_HIGH in reasons

    def test_distribution_shift_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "js_divergence": 0.20})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.DISTRIBUTION_SHIFT in reasons

    def test_feature_mismatch_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "feature_mismatch_ratio": 0.10})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.FEATURE_MISMATCH in reasons

    def test_unknown_token_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "unknown_token_ratio": 0.10})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.UNKNOWN_TOKEN_HIGH in reasons

    def test_fpr_regression_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "fpr_current": 0.10, "fpr_baseline": 0.03})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.FPR_REGRESSION in reasons

    def test_drift_guard_fail_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "drift_guard_pass": False})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.DRIFT_GUARD_FAIL in reasons

    def test_regression_gate_fail_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "regression_gate_pass": False})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.REGRESSION_GATE_FAIL in reasons

    def test_determinism_gate_fail_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "determinism_gate_pass": False})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.DETERMINISM_GATE_FAIL in reasons

    def test_backtest_gate_fail_blocks(self):
        metrics = _make_stable_metrics()
        metrics = CycleMetrics(**{**metrics.__dict__, "backtest_gate_pass": False})
        reasons = evaluate_blocking_conditions(metrics)
        assert BlockReason.BACKTEST_GATE_FAIL in reasons


class TestStagedRollout:
    """Test staged rollout through all 4 stages."""

    def test_starts_at_stage_0(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = load_state()
            assert state.current_stage == 0

    def test_promotion_after_stable_cycles(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState()
            # Run 3 stable cycles to trigger promotion from Stage 0 -> 1
            for i in range(REQUIRED_STABLE_CYCLES):
                result = evaluate_cycle(
                    _make_stable_metrics(f"CYC-{i:03d}"),
                    state=state,
                )
            assert result["promoted"] is True
            assert result["stage"] == 1
            assert result["real_data_pct"] == 0.40

    def test_full_rollout_through_all_stages(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState()
            # 3 stages to promote through (0->1, 1->2, 2->3)
            for stage_target in range(1, 4):
                for i in range(REQUIRED_STABLE_CYCLES):
                    result = evaluate_cycle(
                        _make_stable_metrics(f"CYC-S{stage_target}-{i}"),
                        state=state,
                    )
                assert result["stage"] == stage_target

            assert result["real_data_pct"] == 1.00

    def test_no_promotion_beyond_stage_3(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(current_stage=3, consecutive_stable_cycles=0)
            for i in range(REQUIRED_STABLE_CYCLES + 2):
                result = evaluate_cycle(
                    _make_stable_metrics(f"CYC-{i}"),
                    state=state,
                )
            assert result["promoted"] is False
            assert result["stage"] == 3


class TestBlockingScenarios:
    """Test that blocking conditions freeze promotion."""

    def test_regression_blocks_promotion(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(consecutive_stable_cycles=2)
            # One more stable cycle would promote, but regression blocks
            bad_metrics = CycleMetrics(
                **{**_make_stable_metrics().__dict__,
                   "fpr_current": 0.10, "fpr_baseline": 0.03}
            )
            result = evaluate_cycle(bad_metrics, state=state)
            assert result["blocked"] is True
            assert result["promoted"] is False
            assert "FPR_REGRESSION" in result["blocking_reasons"]
            assert result["consecutive_stable"] == 0  # reset

    def test_drift_blocks_promotion(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(consecutive_stable_cycles=2)
            bad_metrics = CycleMetrics(
                **{**_make_stable_metrics().__dict__, "js_divergence": 0.25}
            )
            result = evaluate_cycle(bad_metrics, state=state)
            assert result["blocked"] is True
            assert "DISTRIBUTION_SHIFT" in result["blocking_reasons"]

    def test_determinism_blocks_promotion(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(consecutive_stable_cycles=2)
            bad_metrics = CycleMetrics(
                **{**_make_stable_metrics().__dict__, "determinism_gate_pass": False}
            )
            result = evaluate_cycle(bad_metrics, state=state)
            assert result["blocked"] is True
            assert "DETERMINISM_GATE_FAIL" in result["blocking_reasons"]

    def test_backtest_blocks_promotion(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(consecutive_stable_cycles=2)
            bad_metrics = CycleMetrics(
                **{**_make_stable_metrics().__dict__, "backtest_gate_pass": False}
            )
            result = evaluate_cycle(bad_metrics, state=state)
            assert result["blocked"] is True
            assert "BACKTEST_GATE_FAIL" in result["blocking_reasons"]

    def test_mode_promotion_blocked_by_imbalance(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(consecutive_stable_cycles=2)
            bad_metrics = CycleMetrics(
                **{**_make_stable_metrics().__dict__, "class_imbalance_ratio": 15.0}
            )
            result = evaluate_cycle(bad_metrics, state=state)
            assert result["blocked"] is True
            assert "CLASS_IMBALANCE_HIGH" in result["blocking_reasons"]


class TestStatePersistence:
    """Test state persistence and recovery."""

    def test_state_survives_reload(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(current_stage=2, consecutive_stable_cycles=1)
            save_state(state)
            reloaded = load_state()
            assert reloaded.current_stage == 2
            assert reloaded.consecutive_stable_cycles == 1

    def test_default_state_when_no_file(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = load_state()
            assert state.current_stage == 0
            assert state.consecutive_stable_cycles == 0
            assert state.is_frozen is False

    def test_reset_clears_state(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            state = RolloutState(current_stage=3)
            save_state(state)
            reset_state()
            reloaded = load_state()
            assert reloaded.current_stage == 0


class TestGetCurrentStatus:
    """Test read-only status retrieval."""

    def test_returns_status_dict(self, _clean_state):
        with patch("governance.real_data_rollout_governor._state_path", return_value=_clean_state):
            status = get_current_status()
            assert "stage" in status
            assert "real_data_pct" in status
            assert "frozen" in status
            assert "promotion_history" in status
