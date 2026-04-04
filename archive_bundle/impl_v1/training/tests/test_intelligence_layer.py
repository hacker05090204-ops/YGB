"""
test_intelligence_layer.py — Tests for 7-Phase Autonomous Intelligence Layer
"""

import os
import sys

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 — DATA SOURCE REGISTRY
# ===========================================================================

class TestDataSourceRegistry:

    def test_register_source(self):
        from impl_v1.training.distributed.data_source_registry import DataSourceRegistry, TrustedSource
        reg = DataSourceRegistry()
        reg.register(TrustedSource("nvd", "cve_feed", 0.95))
        assert reg.source_count == 1

    def test_trusted_allows(self):
        from impl_v1.training.distributed.data_source_registry import DataSourceRegistry, TrustedSource
        reg = DataSourceRegistry()
        reg.register(TrustedSource("nvd", "cve_feed", 0.95))
        r = reg.check_source("nvd")
        assert r.allowed is True

    def test_unknown_rejects(self):
        from impl_v1.training.distributed.data_source_registry import DataSourceRegistry
        reg = DataSourceRegistry()
        r = reg.check_source("unknown")
        assert r.allowed is False


# ===========================================================================
# PHASE 1 — INGESTION POLICY
# ===========================================================================

class TestIngestionPolicy:

    def test_all_pass(self):
        from impl_v1.training.distributed.ingestion_policy import IngestionPolicy, IngestionCandidate
        policy = IngestionPolicy()
        c = IngestionCandidate("s1", "/api", "sqli", "high", "nvd", True, True, True)
        r = policy.check(c)
        assert r.accepted is True

    def test_missing_repro(self):
        from impl_v1.training.distributed.ingestion_policy import IngestionPolicy, IngestionCandidate
        policy = IngestionPolicy()
        c = IngestionCandidate("s2", "/api", "sqli", "high", "nvd", False, True, True)
        r = policy.check(c)
        assert r.accepted is False

    def test_batch(self):
        from impl_v1.training.distributed.ingestion_policy import IngestionPolicy, IngestionCandidate
        policy = IngestionPolicy()
        batch = [
            IngestionCandidate("s1", "/a", "sqli", "h", "n", True, True, True),
            IngestionCandidate("s2", "/b", "xss", "m", "n", False, True, True),
        ]
        results = policy.batch_check(batch)
        assert results["s1"].accepted is True
        assert results["s2"].accepted is False


# ===========================================================================
# PHASE 2 — DATA QUALITY SCORER
# ===========================================================================

class TestDataQualityScorer:

    def test_high_quality_accepted(self):
        from impl_v1.training.distributed.data_quality_scorer import DataQualityScorer
        scorer = DataQualityScorer()
        r = scorer.score("s1", 0.8, 0.7, 0.9, 0.6, 0.7)
        assert r.accepted is True

    def test_low_quality_rejected(self):
        from impl_v1.training.distributed.data_quality_scorer import DataQualityScorer
        scorer = DataQualityScorer(threshold=0.8)
        r = scorer.score("s2", 0.1, 0.1, 0.1, 0.1, 0.1)
        assert r.accepted is False

    def test_score_features(self):
        from impl_v1.training.distributed.data_quality_scorer import DataQualityScorer
        scorer = DataQualityScorer()
        rng = np.random.RandomState(42)
        features = rng.randn(64).astype(np.float32)
        r = scorer.score_features("s3", features, "high", 2)
        assert isinstance(r.composite, float)


# ===========================================================================
# PHASE 2 — HARD NEGATIVE MINER
# ===========================================================================

class TestHardNegativeMiner:

    def test_mine_augments(self):
        from impl_v1.training.distributed.hard_negative_miner import HardNegativeMiner
        miner = HardNegativeMiner()
        rng = np.random.RandomState(42)
        X = rng.randn(200, 16).astype(np.float32)
        y = np.concatenate([np.zeros(100), np.ones(100)]).astype(np.int64)
        X_aug, y_aug, report = miner.mine(X, y, ratio=0.3)
        assert len(X_aug) > len(X)
        assert report.total_mined > 0

    def test_three_strategies(self):
        from impl_v1.training.distributed.hard_negative_miner import HardNegativeMiner
        miner = HardNegativeMiner()
        rng = np.random.RandomState(42)
        X = rng.randn(200, 16).astype(np.float32)
        y = np.concatenate([np.zeros(100), np.ones(100)]).astype(np.int64)
        _, _, report = miner.mine(X, y, ratio=0.5)
        assert report.slight_mutations >= 0
        assert report.near_misses >= 0
        assert report.boundary_cases >= 0


# ===========================================================================
# PHASE 2 — DATASET BALANCE
# ===========================================================================

class TestDatasetBalance:

    def test_already_balanced(self):
        from impl_v1.training.distributed.dataset_balance_controller import DatasetBalanceController
        ctrl = DatasetBalanceController()
        y = np.array([0, 0, 0, 1, 1, 1])
        assert ctrl.check_balance(y)

    def test_rebalance(self):
        from impl_v1.training.distributed.dataset_balance_controller import DatasetBalanceController
        ctrl = DatasetBalanceController(max_imbalance=0.2)
        rng = np.random.RandomState(42)
        X = rng.randn(200, 8).astype(np.float32)
        y = np.concatenate([np.zeros(180), np.ones(20)]).astype(np.int64)
        X_b, y_b, report = ctrl.balance(X, y)
        assert report.balanced is True


# ===========================================================================
# PHASE 3 — LIVE FEEDBACK
# ===========================================================================

class TestLiveFeedback:

    def test_record(self):
        from impl_v1.training.distributed.live_feedback_collector import LiveFeedbackCollector
        fc = LiveFeedbackCollector()
        fc.record("e1", "vuln", "true_positive", 0.95, "abc")
        assert fc.entry_count == 1

    def test_stats(self):
        from impl_v1.training.distributed.live_feedback_collector import LiveFeedbackCollector
        fc = LiveFeedbackCollector()
        fc.record("e1", "vuln", "true_positive", 0.95, "a")
        fc.record("e2", "vuln", "false_positive", 0.4, "b")
        stats = fc.get_stats()
        assert stats.true_positives == 1
        assert stats.false_positives == 1


# ===========================================================================
# PHASE 3 — REINFORCEMENT SCHEDULER
# ===========================================================================

class TestReinforcementScheduler:

    def test_weights(self):
        from impl_v1.training.distributed.reinforcement_scheduler import ReinforcementScheduler
        sched = ReinforcementScheduler()
        w = sched.compute_weights(["true_positive", "false_positive", "accepted"])
        assert w[0] > w[1]  # TP > FP

    def test_run_cycle(self):
        from impl_v1.training.distributed.reinforcement_scheduler import ReinforcementScheduler
        sched = ReinforcementScheduler()
        cycle = sched.run_cycle(
            ["true_positive", "false_positive"], 0.85,
        )
        assert cycle.samples_used == 2


# ===========================================================================
# PHASE 3 — EXPLOIT STABILITY
# ===========================================================================

class TestExploitStability:

    def test_stable(self):
        from impl_v1.training.distributed.exploit_stability_test import ExploitStabilityTester
        tester = ExploitStabilityTester()
        tester.register_known("CVE-2024-001", 0.95)
        report = tester.test(lambda eid: 0.93)
        assert report.stable is True

    def test_regression(self):
        from impl_v1.training.distributed.exploit_stability_test import ExploitStabilityTester
        tester = ExploitStabilityTester(threshold=0.05)
        tester.register_known("CVE-2024-001", 0.95)
        report = tester.test(lambda eid: 0.80)
        assert report.stable is False
        assert report.regressions == 1


# ===========================================================================
# PHASE 4 — ASSISTANT CONTROLLER
# ===========================================================================

class TestAssistantController:

    def test_generate(self):
        from impl_v1.training.distributed.assistant_controller import AssistantController, DetectionInput
        ctrl = AssistantController()
        det = DetectionInput("sqli", 0.92, "vuln", ["param_injection"], "/api/login", "username")
        out = ctrl.generate(det)
        assert out.cvss_score > 0
        assert "sqli" in out.poc.lower() or "SQLi" in out.poc
        assert len(out.repro_steps) > 0

    def test_report_validation(self):
        from impl_v1.training.distributed.report_validation_gate import ReportValidationGate
        gate = ReportValidationGate()
        r = gate.validate(
            "## Report\nType: sqli - SQL Injection found with param_injection indicator",
            "sqli", ["param_injection"], 8.6,
        )
        assert r.valid is True


# ===========================================================================
# PHASE 6 — AUTONOMOUS CYCLE
# ===========================================================================

class TestAutonomousCycle:

    def test_full_cycle(self):
        from impl_v1.training.distributed.autonomous_cycle import AutonomousCycle
        ac = AutonomousCycle()
        report = ac.run_cycle(
            ingest_fn=lambda: {"ingested": 10},
            curate_fn=lambda: {"scored": 10},
            train_fn=lambda: {"accuracy": 0.85},
            govern_fn=lambda: {"mode": "A"},
            reinforce_fn=lambda: {"updated": True},
        )
        assert report.all_success is True
        assert ac.cycle_count == 1

    def test_partial_cycle(self):
        from impl_v1.training.distributed.autonomous_cycle import AutonomousCycle
        ac = AutonomousCycle()
        report = ac.run_cycle(
            ingest_fn=lambda: {"ingested": 5},
        )
        assert report.all_success is True


# ===========================================================================
# PHASE 7 — UNIFIED SAFETY
# ===========================================================================

class TestUnifiedSafety:

    def test_all_pass(self):
        from impl_v1.training.distributed.unified_safety_gate import UnifiedSafetyGate
        gate = UnifiedSafetyGate()
        r = gate.evaluate()
        assert r.training_allowed is True
        assert r.promotion_allowed is True

    def test_data_fail(self):
        from impl_v1.training.distributed.unified_safety_gate import UnifiedSafetyGate
        gate = UnifiedSafetyGate()
        r = gate.evaluate(data_valid=False)
        assert r.training_allowed is False

    def test_source_fail(self):
        from impl_v1.training.distributed.unified_safety_gate import UnifiedSafetyGate
        gate = UnifiedSafetyGate()
        r = gate.evaluate(source_reliable=False)
        assert r.promotion_allowed is False


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestIntelligenceIntegration:

    def test_ingest_curate_train(self):
        """Registry → Policy → Quality → Balance → Cycle."""
        from impl_v1.training.distributed.data_source_registry import DataSourceRegistry, TrustedSource
        from impl_v1.training.distributed.ingestion_policy import IngestionPolicy, IngestionCandidate
        from impl_v1.training.distributed.data_quality_scorer import DataQualityScorer
        from impl_v1.training.distributed.autonomous_cycle import AutonomousCycle

        reg = DataSourceRegistry()
        reg.register(TrustedSource("nvd", "cve_feed", 0.95))
        assert reg.check_source("nvd").allowed

        policy = IngestionPolicy()
        c = IngestionCandidate("s1", "/api", "sqli", "high", "nvd", True, True, True)
        assert policy.check(c).accepted

        scorer = DataQualityScorer()
        q = scorer.score("s1", 0.8, 0.7, 0.9, 0.6, 0.7)
        assert q.accepted

        ac = AutonomousCycle()
        report = ac.run_cycle(ingest_fn=lambda: {"ok": True})
        assert report.all_success
