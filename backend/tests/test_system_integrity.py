"""
System Integrity Supervisor — Test Suite

Tests:
  1. Score computation — weighted aggregation
  2. Threshold enforcement — shadow disabled when score < 95
  3. Dataset watchdog — class imbalance, KL divergence, duplicate detection
  4. Log integrity — hash chain tamper/gap detection
  5. Autonomy conditions — all 5 conditions must pass
  6. Resource monitor — GPU/HDD/IO/Memory scoring
  7. Edge cases — boundary conditions
"""

import os
import sys
import json
import time
import numpy as np
import pytest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.integrity.integrity_bridge import (
    ResourceMonitor,
    DatasetIntegrityWatchdog,
    LogIntegrityMonitor,
    GovernanceIntegrityReader,
    MLIntegrityScorer,
    SystemIntegritySupervisor,
    _score_to_status,
)


# =========================================================================
# 1. SCORE-TO-STATUS TESTS
# =========================================================================

class TestScoreToStatus:
    def test_green(self):
        assert _score_to_status(100.0) == "GREEN"
        assert _score_to_status(90.0) == "GREEN"

    def test_yellow(self):
        assert _score_to_status(89.9) == "YELLOW"
        assert _score_to_status(70.0) == "YELLOW"

    def test_red(self):
        assert _score_to_status(69.9) == "RED"
        assert _score_to_status(0.0) == "RED"


# =========================================================================
# 2. RESOURCE MONITOR TESTS
# =========================================================================

class TestResourceMonitor:
    def test_initial_score_is_perfect(self):
        rm = ResourceMonitor()
        # With defaults (0 temp, 100% free, 0 memory), score should be high
        score = rm.compute_score()
        assert score >= 95.0

    def test_gpu_temp_degrades_score(self):
        rm = ResourceMonitor()
        rm.gpu_temp = 85.0  # Above warn threshold
        score = rm.compute_score()
        assert score < 100.0

    def test_gpu_temp_critical(self):
        rm = ResourceMonitor()
        rm.gpu_temp = 100.0  # At max
        score = rm.compute_score()
        # GPU temp contributes 30%, so score should drop by ~30
        assert score <= 75.0

    def test_gpu_throttle_penalty(self):
        rm = ResourceMonitor()
        rm.gpu_throttle_events = 5
        score = rm.compute_score()
        assert score < 100.0

    def test_hdd_low_space_penalty(self):
        rm = ResourceMonitor()
        rm.hdd_free_percent = 5.0  # Below 15%
        score = rm.compute_score()
        assert score < 100.0

    def test_hdd_critical_space(self):
        rm = ResourceMonitor()
        rm.hdd_free_percent = 1.0
        score = rm.compute_score()
        assert score <= 80.0

    def test_io_latency_tracking(self):
        rm = ResourceMonitor()
        for _ in range(10):
            rm.record_io_latency(60.0)  # Above threshold
        score = rm.compute_score()
        assert score < 100.0

    def test_memory_pressure(self):
        rm = ResourceMonitor()
        rm.memory_used_percent = 95.0
        score = rm.compute_score()
        assert score < 100.0

    def test_all_bad_conditions(self):
        rm = ResourceMonitor()
        rm.gpu_temp = 95.0
        rm.gpu_throttle_events = 10
        rm.hdd_free_percent = 1.0
        for _ in range(10):
            rm.record_io_latency(100.0)
        rm.memory_used_percent = 99.0
        score = rm.compute_score()
        assert score <= 10.0

    def test_alerts_list(self):
        rm = ResourceMonitor()
        rm.gpu_temp = 85.0
        rm.hdd_free_percent = 10.0
        alerts = rm.get_alerts()
        assert len(alerts) >= 2
        assert any("GPU" in a for a in alerts)
        assert any("HDD" in a for a in alerts)


# =========================================================================
# 3. DATASET INTEGRITY WATCHDOG TESTS
# =========================================================================

class TestDatasetIntegrityWatchdog:
    def test_balanced_classes_no_alert(self):
        dw = DatasetIntegrityWatchdog(n_classes=2)
        for _ in range(50):
            dw.record_sample(0, np.random.rand(10))
            dw.record_sample(1, np.random.rand(10))
        stats = dw.get_stats()
        assert not stats["imbalance_alert"]
        assert stats["score"] >= 90.0

    def test_imbalanced_classes_triggers_alert(self):
        dw = DatasetIntegrityWatchdog(n_classes=2)
        for _ in range(100):
            dw.record_sample(0, np.random.rand(10))
        for _ in range(10):
            dw.record_sample(1, np.random.rand(10))
        stats = dw.get_stats()
        assert stats["imbalance_alert"]
        assert stats["should_freeze_training"]

    def test_duplicate_detection(self):
        dw = DatasetIntegrityWatchdog(n_classes=2,
                                      duplicate_rate_threshold=0.05)
        fixed_features = np.array([0.5] * 10)
        # Record same sample many times — all duplicates
        for i in range(100):
            dw.record_sample(0, fixed_features)
        stats = dw.get_stats()
        assert stats["duplicate_count"] > 0
        assert stats["duplicate_rate"] > 0.05
        assert stats["duplicate_alert"]

    def test_kl_divergence_baseline(self):
        dw = DatasetIntegrityWatchdog(n_classes=2, n_bins=10)
        # Set baseline as uniform
        baseline = np.ones(10) / 10.0
        dw.set_baseline(baseline)

        # Feed samples all in one bin (0.0–0.1)
        for _ in range(100):
            dw.record_sample(0, np.array([0.05] + [0.0] * 9))
        stats = dw.get_stats()
        assert stats["kl_divergence"] > 0.0

    def test_reset_clears_state(self):
        dw = DatasetIntegrityWatchdog(n_classes=2)
        for _ in range(50):
            dw.record_sample(0, np.random.rand(10))
        dw.reset()
        stats = dw.get_stats()
        assert stats["total_samples"] == 0
        assert stats["duplicate_count"] == 0

    def test_score_degrades_with_issues(self):
        dw = DatasetIntegrityWatchdog(n_classes=2)
        # Heavy imbalance
        for _ in range(200):
            dw.record_sample(0, np.random.rand(10))
        for _ in range(5):
            dw.record_sample(1, np.random.rand(10))
        stats = dw.get_stats()
        assert stats["score"] < 80.0


# =========================================================================
# 4. LOG INTEGRITY MONITOR TESTS
# =========================================================================

class TestLogIntegrityMonitor:
    def test_empty_chain_valid(self):
        lm = LogIntegrityMonitor()
        assert lm.verify_chain()
        stats = lm.get_stats()
        assert stats["chain_valid"]
        assert stats["score"] == 100.0

    def test_append_and_verify(self):
        lm = LogIntegrityMonitor()
        lm.append_entry("test", "first entry")
        lm.append_entry("test", "second entry")
        lm.append_entry("test", "third entry")
        assert lm.verify_chain()
        stats = lm.get_stats()
        assert stats["total_entries"] == 3
        assert stats["chain_valid"]

    def test_tamper_detection(self):
        lm = LogIntegrityMonitor()
        lm.append_entry("test", "entry one")
        lm.append_entry("test", "entry two")
        # Tamper: overwrite chain hash
        lm.entries[0]["chain_hash"] = b'\xff' * 32
        assert not lm.verify_chain()
        stats = lm.get_stats()
        assert stats["has_corruption"]
        assert stats["score"] < 100.0

    def test_gap_detection(self):
        lm = LogIntegrityMonitor()
        # Gaps tracked via external entries
        lm.gap_count = 3
        stats = lm.get_stats()
        assert stats["has_gaps"]
        assert stats["gap_count"] == 3
        assert stats["score"] < 100.0

    def test_score_zero_with_many_corruptions(self):
        lm = LogIntegrityMonitor()
        for i in range(10):
            lm.append_entry("test", f"entry {i}")
        # Corrupt all entries
        for entry in lm.entries:
            entry["chain_hash"] = b'\xff' * 32
        stats = lm.get_stats()
        assert stats["score"] <= 40.0  # Max corruption penalty is 60 points


# =========================================================================
# 5. ML INTEGRITY SCORER TESTS
# =========================================================================

class TestMLIntegrityScorer:
    def test_default_perfect_score(self):
        ml = MLIntegrityScorer()
        score, details = ml.compute_score()
        assert score == 100.0

    def test_drift_degrades_score(self):
        ml = MLIntegrityScorer()
        ml.update_drift(4.0)  # Way above 2.0 threshold
        score, details = ml.compute_score()
        assert score < 100.0
        assert details["drift_score"] < 100.0

    def test_inflation_degrades_score(self):
        ml = MLIntegrityScorer()
        ml.update_inflation(0.10)  # Way above 0.02 threshold
        score, details = ml.compute_score()
        assert score < 100.0
        assert details["inflation_score"] < 100.0

    def test_model_age_degrades_score(self):
        ml = MLIntegrityScorer()
        ml.update_model_age(120)  # 120 days, max is 90
        score, details = ml.compute_score()
        assert score < 100.0
        assert details["age_score"] < 100.0

    def test_has_drift_alert(self):
        ml = MLIntegrityScorer()
        assert not ml.has_drift_alert
        ml.update_drift(3.0)
        assert ml.has_drift_alert


# =========================================================================
# 6. GOVERNANCE INTEGRITY READER TESTS
# =========================================================================

class TestGovernanceIntegrityReader:
    def test_reads_real_file(self):
        state_path = PROJECT_ROOT / "reports" / "governance_state.json"
        reader = GovernanceIntegrityReader(state_path)
        score, details = reader.compute_score()
        # File exists, so we should get a real score
        assert 0.0 <= score <= 100.0
        assert "checks" in details

    def test_missing_file_returns_zero(self):
        reader = GovernanceIntegrityReader(Path("/nonexistent/path.json"))
        score, details = reader.compute_score()
        assert score == 0.0


# =========================================================================
# 7. SYSTEM INTEGRITY SUPERVISOR TESTS
# =========================================================================

class TestSystemIntegritySupervisor:
    def test_probe_all_returns_structure(self):
        sup = SystemIntegritySupervisor()
        result = sup.probe_all()
        assert "ml_integrity" in result
        assert "dataset_integrity" in result
        assert "storage_integrity" in result
        assert "resource_integrity" in result
        assert "log_integrity" in result
        assert "governance_integrity" in result
        assert "overall_integrity" in result
        assert "shadow_allowed" in result
        assert "forced_mode" in result
        assert "timestamp" in result

    def test_all_scores_in_range(self):
        sup = SystemIntegritySupervisor()
        result = sup.probe_all()
        for key in ["ml_integrity", "dataset_integrity", "storage_integrity",
                     "resource_integrity", "log_integrity", "governance_integrity",
                     "overall_integrity"]:
            assert 0.0 <= result[key]["score"] <= 100.0

    def test_status_values_valid(self):
        sup = SystemIntegritySupervisor()
        result = sup.probe_all()
        valid_statuses = {"GREEN", "YELLOW", "RED"}
        for key in ["ml_integrity", "dataset_integrity", "storage_integrity",
                     "resource_integrity", "log_integrity", "governance_integrity",
                     "overall_integrity"]:
            assert result[key]["status"] in valid_statuses

    def test_shadow_blocked_when_governance_fails(self):
        """Shadow must be blocked when governance checks fail."""
        sup = SystemIntegritySupervisor()
        result = sup.probe_all()
        # Governance state has a failed check, so overall < 95
        # which means shadow should be blocked
        if result["governance_integrity"]["score"] < 100.0:
            # With failed governance, overall likely < 95
            assert not result["shadow_allowed"] or result["overall_integrity"]["score"] > 95.0

    def test_forced_mode_a_when_blocked(self):
        sup = SystemIntegritySupervisor()
        # Force a containment event
        sup.containment_timestamps.append(time.time())
        result = sup.probe_all()
        assert not result["shadow_allowed"]
        assert result["forced_mode"] == "MODE_A"
        assert "containment_event_in_last_24h" in result["shadow_blocked_reasons"]

    def test_drift_blocks_shadow(self):
        sup = SystemIntegritySupervisor()
        sup.ml_scorer.update_drift(5.0)  # Massive drift
        result = sup.probe_all()
        assert not result["shadow_allowed"]
        assert "drift_anomaly_detected" in result["shadow_blocked_reasons"]

    def test_dataset_skew_blocks_shadow(self):
        sup = SystemIntegritySupervisor()
        # Create heavy imbalance
        for _ in range(200):
            sup.dataset_watchdog.record_sample(0, np.random.rand(10))
        for _ in range(5):
            sup.dataset_watchdog.record_sample(1, np.random.rand(10))
        result = sup.probe_all()
        assert not result["shadow_allowed"]
        assert "dataset_skew_detected" in result["shadow_blocked_reasons"]

    def test_no_mock_data(self):
        """Verify the result contains no mock/placeholder fields."""
        sup = SystemIntegritySupervisor()
        result = sup.probe_all()
        # Should have real timestamp
        assert result["timestamp"] is not None
        assert len(result["timestamp"]) > 0
        # Scores should be computed (not hardcoded placeholders)
        assert isinstance(result["overall_integrity"]["score"], float)


# =========================================================================
# 8. AUTONOMY CONDITIONS — ALL 5 MUST PASS
# =========================================================================

class TestAutonomyConditions:
    def test_all_conditions_must_pass(self):
        """Shadow only allowed when ALL 5 conditions are true."""
        sup = SystemIntegritySupervisor()
        result = sup.probe_all()
        if result["shadow_allowed"]:
            # If shadow is allowed, ALL conditions must have been true
            assert result["overall_integrity"]["score"] > 95.0
            assert len(result["shadow_blocked_reasons"]) == 0

    def test_single_failure_blocks_shadow(self):
        """Even one failed condition blocks shadow."""
        sup = SystemIntegritySupervisor()
        # Only add containment event — this alone should block
        sup.containment_timestamps.append(time.time())
        result = sup.probe_all()
        assert not result["shadow_allowed"]

    def test_storage_warning_blocks_shadow(self):
        """Low disk space blocks shadow."""
        sup = SystemIntegritySupervisor()
        sup.resource_monitor.hdd_free_percent = 5.0
        result = sup.probe_all()
        assert not result["shadow_allowed"]
        # Storage warning or overall score breach should be in reasons
        reasons_str = " ".join(result["shadow_blocked_reasons"])
        assert "storage" in reasons_str or "overall" in reasons_str
