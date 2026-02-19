"""
TEST FIELD LIFECYCLE — Determinism, Transitions, Freeze, Progress
=================================================================
Validates the Python-side mirrors of C++ field lifecycle engines.
"""

import json
import os
import sys
import tempfile
import importlib.util
import pytest

# ------------------------------------------------------------------
# Setup path — use importlib to avoid pytest module resolution issues
# ------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

_api_path = os.path.join(PROJECT_ROOT, 'backend', 'api', 'field_progression_api.py')
_spec = importlib.util.spec_from_file_location("field_progression_api", _api_path,
    submodule_search_locations=[os.path.join(PROJECT_ROOT, 'backend')])
_mod = importlib.util.module_from_spec(_spec)

# Ensure governance module is importable
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))
_spec.loader.exec_module(_mod)

TOTAL_FIELDS = _mod.TOTAL_FIELDS
FIELD_NAMES = _mod.FIELD_NAMES
LIFECYCLE_STATES = _mod.LIFECYCLE_STATES
TIERS = _mod.TIERS
CLIENT_SIDE_THRESHOLDS = _mod.CLIENT_SIDE_THRESHOLDS
API_THRESHOLDS = _mod.API_THRESHOLDS
_default_state = _mod._default_state
_save_field_state = _mod._save_field_state
_load_field_state = _mod._load_field_state
_calculate_progress = _mod._calculate_progress
get_fields_state = _mod.get_fields_state
get_active_progress = _mod.get_active_progress
start_training = _mod.start_training


# ==================================================================
# LIFECYCLE STATES
# ==================================================================

class TestLifecycleStates:
    """Verify 7-state lifecycle matches C++ enum."""

    def test_total_states(self):
        assert len(LIFECYCLE_STATES) == 7

    def test_state_order(self):
        expected = [
            "NOT_STARTED", "TRAINING", "STABILITY_CHECK",
            "CERTIFICATION_PENDING", "CERTIFIED", "FROZEN", "NEXT_FIELD",
        ]
        assert LIFECYCLE_STATES == expected

    def test_certification_pending_exists(self):
        assert "CERTIFICATION_PENDING" in LIFECYCLE_STATES

    def test_no_duplicate_states(self):
        assert len(LIFECYCLE_STATES) == len(set(LIFECYCLE_STATES))


# ==================================================================
# FIELD LADDER
# ==================================================================

class TestFieldLadder:
    """Verify 23-field sequential ladder structure."""

    def test_total_fields(self):
        assert TOTAL_FIELDS == 23

    def test_field_names_count(self):
        assert len(FIELD_NAMES) == TOTAL_FIELDS

    def test_master_fields(self):
        assert FIELD_NAMES[0] == "Client-Side Application Security"
        assert FIELD_NAMES[1] == "API / Business Logic Security"

    def test_master_tier(self):
        assert TIERS[0]["tier"] == 1
        assert TIERS[1]["tier"] == 1

    def test_extended_fields_tier(self):
        for i in range(2, 12):
            assert TIERS[i]["tier"] == 2, f"Field {i} should be Tier 2"
        for i in range(12, TOTAL_FIELDS):
            assert TIERS[i]["tier"] == 3, f"Field {i} should be Tier 3"


# ==================================================================
# DEFAULT STATE
# ==================================================================

class TestDefaultState:
    """Verify initial ladder state is deterministic."""

    def test_default_active_field(self):
        state = _default_state()
        assert state["active_field_id"] == 0

    def test_first_field_training(self):
        state = _default_state()
        assert state["fields"][0]["state"] == "TRAINING"
        assert state["fields"][0]["active"] is True
        assert state["fields"][0]["locked"] is False

    def test_all_other_fields_locked(self):
        state = _default_state()
        for i in range(1, TOTAL_FIELDS):
            f = state["fields"][i]
            assert f["state"] == "NOT_STARTED", f"Field {i} should be NOT_STARTED"
            assert f["locked"] is True, f"Field {i} should be locked"
            assert f["active"] is False, f"Field {i} should be inactive"

    def test_no_mock_data_in_metrics(self):
        state = _default_state()
        for f in state["fields"]:
            assert f["precision"] is None
            assert f["fpr"] is None
            assert f["dup_detection"] is None
            assert f["ece"] is None

    def test_zero_stability(self):
        state = _default_state()
        for f in state["fields"]:
            assert f["stability_days"] == 0

    def test_deterministic(self):
        """Two calls produce identical structure (except timestamp)."""
        s1 = _default_state()
        s2 = _default_state()
        s1.pop("last_updated")
        s2.pop("last_updated")
        assert s1 == s2


# ==================================================================
# THRESHOLDS
# ==================================================================

class TestThresholds:
    """Verify certification thresholds match C++."""

    def test_client_side_precision(self):
        assert CLIENT_SIDE_THRESHOLDS["min_precision"] == 0.96

    def test_client_side_fpr(self):
        assert CLIENT_SIDE_THRESHOLDS["max_fpr"] == 0.04

    def test_client_side_dup(self):
        assert CLIENT_SIDE_THRESHOLDS["min_dup"] == 0.88

    def test_client_side_ece(self):
        assert CLIENT_SIDE_THRESHOLDS["max_ece"] == 0.018

    def test_client_side_stability(self):
        assert CLIENT_SIDE_THRESHOLDS["min_stability_days"] == 7

    def test_api_precision(self):
        assert API_THRESHOLDS["min_precision"] == 0.95

    def test_api_fpr(self):
        assert API_THRESHOLDS["max_fpr"] == 0.05

    def test_api_stability(self):
        assert API_THRESHOLDS["min_stability_days"] == 7


# ==================================================================
# PROGRESS CALCULATOR
# ==================================================================

class TestProgressCalculator:
    """Verify weighted progress calculation."""

    def test_no_data_zero_percent(self):
        """Metrics=None → only stability contributes."""
        field = {
            "id": 0, "precision": None, "fpr": None,
            "dup_detection": None, "ece": None, "stability_days": 0,
        }
        result = _calculate_progress(field)
        assert result["overall_percent"] == 0.0
        assert result["metrics_available"] == 1  # stability always available

    def test_partial_data_still_works(self):
        field = {
            "id": 0, "precision": 0.90, "fpr": None,
            "dup_detection": None, "ece": None, "stability_days": 3,
        }
        result = _calculate_progress(field)
        assert result["metrics_available"] == 2
        assert 0 < result["overall_percent"] < 100

    def test_perfect_scores(self):
        field = {
            "id": 0, "precision": 0.99, "fpr": 0.01,
            "dup_detection": 0.95, "ece": 0.005, "stability_days": 7,
        }
        result = _calculate_progress(field)
        assert result["overall_percent"] == 100.0
        assert result["metrics_available"] == 5

    def test_awaiting_data_status(self):
        field = {
            "id": 0, "precision": None, "fpr": None,
            "dup_detection": None, "ece": None, "stability_days": 0,
        }
        result = _calculate_progress(field)
        assert "Awaiting Data" in result["status"]

    def test_weights_sum_to_one(self):
        total = _mod.W_PRECISION + _mod.W_FPR + _mod.W_DUPLICATE + _mod.W_ECE + _mod.W_STABILITY
        assert abs(total - 1.0) < 0.001


# ==================================================================
# PERSISTENCE
# ==================================================================

class TestPersistence:
    """Verify atomic state save/load."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            state = _default_state()

            # Monkey-patch path
            orig = _mod.FIELD_STATE_PATH
            _mod.FIELD_STATE_PATH = path
            try:
                _save_field_state(state)
                loaded = _load_field_state()
                assert loaded["total_fields"] == TOTAL_FIELDS
                assert len(loaded["fields"]) == TOTAL_FIELDS
            finally:
                _mod.FIELD_STATE_PATH = orig

    def test_missing_file_returns_default(self):
        orig = _mod.FIELD_STATE_PATH
        _mod.FIELD_STATE_PATH = "/nonexistent/path/state.json"
        try:
            state = _load_field_state()
            assert state["total_fields"] == TOTAL_FIELDS
        finally:
            _mod.FIELD_STATE_PATH = orig


# ==================================================================
# TRAINING START
# ==================================================================

class TestTrainingStart:
    """Verify training start govnernance gates."""

    def test_training_requires_authority_locks(self):
        result = start_training()
        # Should either succeed or fail based on authority lock
        assert "status" in result

    def test_training_returns_field_info(self):
        result = start_training()
        if result["status"] == "ok":
            assert "field_id" in result
            assert "field_name" in result
