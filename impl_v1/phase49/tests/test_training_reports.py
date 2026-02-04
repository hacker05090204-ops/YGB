# Tests for G38 Training Reports
"""
Test coverage for training report generation.

100% coverage required for:
- Guard enforcement
- Report file generation
- Learned vs not-learned separation
- CPU fallback
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from impl_v1.phase49.runtime.training_reports import (
    TrainingMode,
    LearnedDomain,
    LockedAbility,
    TrainingSummary,
    LearnedFeatures,
    NotLearnedYet,
    TrainingReportGenerator,
    can_ai_explain_decisions,
    can_ai_claim_verification,
    can_ai_hide_training_state,
    verify_report_guards,
    generate_training_report,
    update_latest_symlinks,
)


# =============================================================================
# GUARD TESTS
# =============================================================================

class TestReportGuards:
    """Test all report guards return False."""
    
    def test_can_ai_explain_decisions_returns_false(self):
        """AI cannot explain decisions authoritatively."""
        result, msg = can_ai_explain_decisions()
        assert result is False
        assert "advisory" in msg.lower()
    
    def test_can_ai_claim_verification_returns_false(self):
        """AI cannot claim verification."""
        result, msg = can_ai_claim_verification()
        assert result is False
        assert "G33" in msg or "G36" in msg
    
    def test_can_ai_hide_training_state_returns_false(self):
        """AI cannot hide training state."""
        result, msg = can_ai_hide_training_state()
        assert result is False
        assert "transparency" in msg.lower()
    
    def test_verify_all_report_guards(self):
        """All report guards pass verification."""
        ok, msg = verify_report_guards()
        assert ok is True
        assert "verified" in msg.lower()


# =============================================================================
# TRAINING MODE TESTS
# =============================================================================

class TestTrainingMode:
    """Test training mode enumeration."""
    
    def test_mode_a_is_representation_only(self):
        """MODE-A is representation only."""
        assert TrainingMode.MODE_A.value == "REPRESENTATION_ONLY"
    
    def test_mode_b_is_proof_learning(self):
        """MODE-B is proof learning."""
        assert TrainingMode.MODE_B.value == "PROOF_LEARNING"


# =============================================================================
# LEARNED DOMAIN TESTS
# =============================================================================

class TestLearnedDomains:
    """Test learned domain enumeration."""
    
    def test_has_code_patterns(self):
        """Has code patterns domain."""
        assert LearnedDomain.CODE_PATTERNS.value == "code_patterns"
    
    def test_has_ui_layouts(self):
        """Has UI layouts domain."""
        assert LearnedDomain.UI_LAYOUTS.value == "ui_layouts"
    
    def test_has_network_protocols(self):
        """Has network protocols domain."""
        assert LearnedDomain.NETWORK_PROTOCOLS.value == "network_protocols"
    
    def test_has_at_least_5_domains(self):
        """At least 5 learnable domains."""
        assert len(LearnedDomain) >= 5


# =============================================================================
# LOCKED ABILITY TESTS
# =============================================================================

class TestLockedAbilities:
    """Test locked ability enumeration."""
    
    def test_has_bug_decision_locked(self):
        """Bug decision is locked."""
        assert LockedAbility.BUG_DECISION.value == "bug_decision"
    
    def test_has_severity_labeling_locked(self):
        """Severity labeling is locked."""
        assert LockedAbility.SEVERITY_LABELING.value == "severity_labeling"
    
    def test_has_exploit_logic_locked(self):
        """Exploit logic is locked."""
        assert LockedAbility.EXPLOIT_LOGIC.value == "exploit_logic"
    
    def test_has_submission_logic_locked(self):
        """Submission logic is locked."""
        assert LockedAbility.SUBMISSION_LOGIC.value == "submission_logic"
    
    def test_has_at_least_5_locked(self):
        """At least 5 locked abilities."""
        assert len(LockedAbility) >= 5


# =============================================================================
# REPORT GENERATOR TESTS
# =============================================================================

class TestTrainingReportGenerator:
    """Test TrainingReportGenerator."""
    
    @pytest.fixture
    def temp_reports_dir(self):
        """Create temporary reports directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def generator(self, temp_reports_dir):
        """Create generator with temp directory."""
        return TrainingReportGenerator(temp_reports_dir)
    
    def test_init_creates_directory(self, temp_reports_dir):
        """Init creates reports directory."""
        subdir = Path(temp_reports_dir) / "subdir"
        gen = TrainingReportGenerator(str(subdir))
        assert subdir.exists()
    
    def test_init_verifies_guards(self, temp_reports_dir):
        """Init verifies all guards."""
        gen = TrainingReportGenerator(temp_reports_dir)
        assert gen is not None
    
    def test_generate_session_id(self, generator):
        """Session ID is generated correctly."""
        session_id = generator.generate_session_id()
        assert session_id.startswith("G38-")
        assert len(session_id) > 10
    
    def test_generate_summary(self, generator):
        """Summary is generated correctly."""
        summary = generator.generate_summary(
            session_id="TEST-001",
            total_epochs=100,
            training_mode=TrainingMode.MODE_A,
            gpu_used=False,
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T01:00:00Z",
            checkpoints_saved=10,
            last_checkpoint_hash="abc123",
        )
        assert summary.session_id == "TEST-001"
        assert summary.total_epochs == 100
        assert summary.backend == "CPU"
        assert "representation" in summary.learning_focus.lower()
    
    def test_generate_summary_with_gpu(self, generator):
        """Summary shows GPU when used."""
        summary = generator.generate_summary(
            session_id="TEST-002",
            total_epochs=100,
            training_mode=TrainingMode.MODE_A,
            gpu_used=True,
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T01:00:00Z",
            checkpoints_saved=10,
            last_checkpoint_hash="abc123",
        )
        assert summary.backend == "GPU"
    
    def test_generate_learned_features(self, generator):
        """Learned features generated correctly."""
        features = generator.generate_learned_features(
            session_id="TEST-001",
            samples_processed=1000,
        )
        assert features.session_id == "TEST-001"
        assert features.proof_learning is False
        assert features.representation_only is True
        assert len(features.domains_learned) > 0
    
    def test_generate_not_learned(self, generator):
        """Not learned report generated correctly."""
        not_learned = generator.generate_not_learned("TEST-001")
        assert not_learned.session_id == "TEST-001"
        assert not_learned.governance_enforced is True
        assert len(not_learned.locked_abilities) > 0


# =============================================================================
# FILE WRITING TESTS
# =============================================================================

class TestReportFileWriting:
    """Test report file writing."""
    
    @pytest.fixture
    def temp_reports_dir(self):
        """Create temporary reports directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def generator(self, temp_reports_dir):
        """Create generator with temp directory."""
        return TrainingReportGenerator(temp_reports_dir)
    
    def test_write_summary_txt(self, generator):
        """Summary TXT file is written."""
        summary = TrainingSummary(
            session_id="TEST-001",
            total_epochs=100,
            training_mode="REPRESENTATION_ONLY",
            backend="CPU",
            learning_focus="Test focus",
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T01:00:00Z",
            duration_seconds=3600,
            checkpoints_saved=10,
            last_checkpoint_hash="abc123",
        )
        path = generator.write_summary_txt(summary)
        assert path.exists()
        content = path.read_text()
        assert "G38 TRAINING SUMMARY" in content
        assert "TEST-001" in content
        assert "100" in content
    
    def test_write_learned_json(self, generator):
        """Learned features JSON is written."""
        features = LearnedFeatures(
            session_id="TEST-001",
            domains_learned=["code_patterns", "ui_layouts"],
            confidence_calibration=0.85,
            duplicate_detection_accuracy=0.78,
            noise_detection_accuracy=0.82,
            proof_learning=False,
            total_samples_processed=1000,
            representation_only=True,
        )
        path = generator.write_learned_json(features)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["session_id"] == "TEST-001"
        assert data["proof_learning"] is False
        assert data["representation_only"] is True
        assert data["governance"]["ai_has_authority"] is False
    
    def test_write_not_learned_txt(self, generator):
        """Not learned TXT file is written."""
        not_learned = NotLearnedYet(
            session_id="TEST-001",
            locked_abilities=["bug_decision", "severity_labeling"],
            reason="Test reason",
            governance_enforced=True,
        )
        path = generator.write_not_learned_txt(not_learned)
        assert path.exists()
        content = path.read_text()
        assert "GOVERNANCE-LOCKED" in content
        assert "bug_decision" in content
        assert "NEVER DECIDE" in content


# =============================================================================
# FULL REPORT GENERATION TESTS
# =============================================================================

class TestGenerateAllReports:
    """Test complete report generation."""
    
    @pytest.fixture
    def temp_reports_dir(self):
        """Create temporary reports directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_generate_all_reports(self, temp_reports_dir):
        """All three report files are generated."""
        generator = TrainingReportGenerator(temp_reports_dir)
        paths = generator.generate_all_reports(
            total_epochs=100,
            training_mode=TrainingMode.MODE_A,
            gpu_used=False,
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T01:00:00Z",
            checkpoints_saved=10,
            last_checkpoint_hash="abc123",
            samples_processed=1000,
        )
        assert "summary" in paths
        assert "learned" in paths
        assert "not_learned" in paths
        assert paths["summary"].exists()
        assert paths["learned"].exists()
        assert paths["not_learned"].exists()
    
    def test_generate_training_report_function(self, temp_reports_dir):
        """Main generate_training_report function works."""
        paths = generate_training_report(
            total_epochs=50,
            gpu_used=False,
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T00:30:00Z",
            checkpoints_saved=5,
            last_checkpoint_hash="def456",
            samples_processed=500,
            training_mode=TrainingMode.MODE_A,
            reports_dir=temp_reports_dir,
        )
        assert "summary" in paths
        assert "learned" in paths
        assert "not_learned" in paths


# =============================================================================
# CPU FALLBACK TESTS
# =============================================================================

class TestCPUFallback:
    """Test CPU fallback behavior."""
    
    @pytest.fixture
    def temp_reports_dir(self):
        """Create temporary reports directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_cpu_fallback_in_summary(self, temp_reports_dir):
        """Summary shows CPU when GPU not available."""
        generator = TrainingReportGenerator(temp_reports_dir)
        summary = generator.generate_summary(
            session_id="TEST-CPU",
            total_epochs=100,
            training_mode=TrainingMode.MODE_A,
            gpu_used=False,
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T01:00:00Z",
            checkpoints_saved=10,
            last_checkpoint_hash="abc123",
        )
        assert summary.backend == "CPU"
    
    def test_gpu_in_summary_when_used(self, temp_reports_dir):
        """Summary shows GPU when available and used."""
        generator = TrainingReportGenerator(temp_reports_dir)
        summary = generator.generate_summary(
            session_id="TEST-GPU",
            total_epochs=100,
            training_mode=TrainingMode.MODE_A,
            gpu_used=True,
            started_at="2026-02-04T00:00:00Z",
            stopped_at="2026-02-04T01:00:00Z",
            checkpoints_saved=10,
            last_checkpoint_hash="abc123",
        )
        assert summary.backend == "GPU"


# =============================================================================
# LEARNED VS NOT-LEARNED SEPARATION TESTS
# =============================================================================

class TestLearnedVsNotLearned:
    """Test clear separation of learned vs locked abilities."""
    
    def test_domains_are_representation_only(self):
        """All learned domains are representation patterns."""
        for domain in LearnedDomain:
            # None should contain "bug", "exploit", "severity"
            assert "bug" not in domain.value.lower()
            assert "exploit" not in domain.value.lower()
            assert "severity" not in domain.value.lower()
    
    def test_locked_abilities_include_bug_decision(self):
        """Bug decision is always locked."""
        locked_values = [a.value for a in LockedAbility]
        assert "bug_decision" in locked_values
    
    def test_locked_abilities_include_exploit_logic(self):
        """Exploit logic is always locked."""
        locked_values = [a.value for a in LockedAbility]
        assert "exploit_logic" in locked_values
    
    def test_locked_abilities_include_submission_logic(self):
        """Submission logic is always locked."""
        locked_values = [a.value for a in LockedAbility]
        assert "submission_logic" in locked_values
    
    def test_learned_features_never_has_proof_learning_mode_a(self):
        """Learned features never has proof_learning=True in MODE-A."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = TrainingReportGenerator(tmpdir)
            features = generator.generate_learned_features("TEST", 100)
            assert features.proof_learning is False
    
    def test_not_learned_always_governance_enforced(self):
        """Not learned always has governance_enforced=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = TrainingReportGenerator(tmpdir)
            not_learned = generator.generate_not_learned("TEST")
            assert not_learned.governance_enforced is True
