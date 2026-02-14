"""
Tests for Isolation Guard — Cross-Contamination Prevention

Validates:
  - Blocked imports (training, integrity, storage)
  - Blocked paths (models, datasets, governance)
  - Blocked file extensions (.pt, .onnx, .h5, etc.)
  - Write blocks (research = read-only)
  - Audit logging
  - Pre-query check verifies all walls
"""

import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.assistant.isolation_guard import (
    IsolationGuard,
    IsolationViolation,
    IsolationCheckResult,
    get_audit_log,
    clear_audit_log,
    BLOCKED_IMPORT_PATTERNS,
    BLOCKED_PATH_FRAGMENTS,
    BLOCKED_EXTENSIONS,
)


class TestIsolationGuardImports:
    """Test import blocking."""

    def setup_method(self):
        self.guard = IsolationGuard()

    def test_block_training_import(self):
        """Training module imports are blocked."""
        result = self.guard.check_import("training")
        assert not result.allowed
        assert result.violation == IsolationViolation.IMPORT_BLOCKED

    def test_block_training_submodule(self):
        """Training submodule imports are blocked."""
        result = self.guard.check_import("training.models.weights")
        assert not result.allowed
        assert result.violation == IsolationViolation.IMPORT_BLOCKED

    def test_block_integrity_import(self):
        """Integrity module imports are blocked."""
        result = self.guard.check_import("backend.integrity")
        assert not result.allowed
        assert result.violation == IsolationViolation.IMPORT_BLOCKED

    def test_block_storage_import(self):
        """Storage module imports are blocked."""
        result = self.guard.check_import("backend.storage")
        assert not result.allowed
        assert result.violation == IsolationViolation.IMPORT_BLOCKED

    def test_block_containment_import(self):
        """Containment module imports are blocked."""
        result = self.guard.check_import("native.containment")
        assert not result.allowed
        assert result.violation == IsolationViolation.IMPORT_BLOCKED

    def test_allow_safe_import(self):
        """Non-blocked imports are allowed."""
        result = self.guard.check_import("json")
        assert result.allowed
        assert result.violation is None

    def test_allow_research_module(self):
        """Research assistant's own module is allowed."""
        result = self.guard.check_import("backend.assistant.query_router")
        assert result.allowed

    def test_allow_stdlib_import(self):
        """Standard library imports are allowed."""
        result = self.guard.check_import("os.path")
        assert result.allowed


class TestIsolationGuardPaths:
    """Test path access blocking."""

    def setup_method(self):
        self.guard = IsolationGuard()

    def test_block_training_path(self):
        """Training directory is blocked."""
        result = self.guard.check_path_read("/project/training/data.csv")
        assert not result.allowed
        assert result.violation == IsolationViolation.TRAINING_ACCESS

    def test_block_models_path(self):
        """Models directory is blocked."""
        result = self.guard.check_path_read("/project/models/weights.pt")
        assert not result.allowed
        assert result.violation == IsolationViolation.PATH_BLOCKED

    def test_block_datasets_path(self):
        """Datasets directory is blocked."""
        result = self.guard.check_path_read("/project/datasets/train.json")
        assert not result.allowed
        assert result.violation == IsolationViolation.PATH_BLOCKED

    def test_block_governance_path(self):
        """Governance state file is blocked."""
        result = self.guard.check_path_read("/config/governance_state.json")
        assert not result.allowed
        assert result.violation == IsolationViolation.GOVERNANCE_ACCESS

    def test_block_integrity_path(self):
        """Integrity backend path is blocked."""
        result = self.guard.check_path_read("/project/backend/integrity/check.py")
        assert not result.allowed
        assert result.violation == IsolationViolation.STORAGE_ENGINE_ACCESS

    def test_block_windows_path(self):
        """Windows-style paths are also blocked."""
        result = self.guard.check_path_read("C:\\project\\training\\data.csv")
        assert not result.allowed

    def test_allow_safe_path(self):
        """Non-blocked paths are allowed for reading."""
        result = self.guard.check_path_read("/tmp/research_output.txt")
        assert result.allowed

    def test_block_all_writes(self):
        """All writes are blocked (research = read-only)."""
        result = self.guard.check_path_write("/tmp/research_output.txt")
        assert not result.allowed
        assert result.violation == IsolationViolation.WRITE_BLOCKED


class TestIsolationGuardExtensions:
    """Test model file extension blocking."""

    def setup_method(self):
        self.guard = IsolationGuard()

    def test_block_pytorch_model(self):
        """PyTorch .pt files are blocked."""
        result = self.guard.check_path_read("/models/model.pt")
        assert not result.allowed

    def test_block_onnx_model(self):
        """ONNX .onnx files are blocked."""
        result = self.guard.check_path_read("/tmp/exported.onnx")
        assert not result.allowed

    def test_block_h5_model(self):
        """Keras .h5 files are blocked."""
        result = self.guard.check_path_read("/data/model.h5")
        assert not result.allowed

    def test_block_safetensors(self):
        """SafeTensors files are blocked."""
        result = self.guard.check_path_read("/cache/weights.safetensors")
        assert not result.allowed

    def test_allow_text_file(self):
        """Text files are allowed."""
        result = self.guard.check_path_read("/tmp/output.txt")
        assert result.allowed

    def test_allow_json_file(self):
        """JSON files are allowed (non-governance)."""
        result = self.guard.check_path_read("/tmp/results.json")
        assert result.allowed


class TestIsolationGuardGovernanceStorage:
    """Test governance and storage access blocks."""

    def setup_method(self):
        self.guard = IsolationGuard()

    def test_governance_access_blocked(self):
        """Direct governance access is always blocked."""
        result = self.guard.check_governance_access()
        assert not result.allowed
        assert result.violation == IsolationViolation.GOVERNANCE_ACCESS

    def test_storage_engine_access_blocked(self):
        """Direct storage engine access is always blocked."""
        result = self.guard.check_storage_engine_access()
        assert not result.allowed
        assert result.violation == IsolationViolation.STORAGE_ENGINE_ACCESS


class TestIsolationGuardAudit:
    """Test audit logging."""

    def setup_method(self):
        self.guard = IsolationGuard()
        clear_audit_log()

    def test_audit_log_entry_created(self):
        """Audit entries are created for research queries."""
        entry = self.guard.log_research_query(
            query="What is Python?",
            result_status="SUCCESS",
            checks_passed=5,
            checks_failed=0,
            violations=[],
        )
        assert entry.entry_id.startswith("AUD-")
        assert entry.query == "What is Python?"
        assert entry.result_status == "SUCCESS"
        assert entry.isolation_checks_passed == 5
        assert entry.isolation_checks_failed == 0

    def test_audit_log_accumulates(self):
        """Multiple audit entries accumulate."""
        self.guard.log_research_query("q1", "SUCCESS", 5, 0, [])
        self.guard.log_research_query("q2", "BLOCKED", 4, 1, ["import_blocked"])
        log = get_audit_log()
        assert len(log) == 2

    def test_audit_log_truncates_long_queries(self):
        """Long queries are truncated to 256 chars."""
        long_query = "A" * 500
        entry = self.guard.log_research_query(long_query, "SUCCESS", 5, 0, [])
        assert len(entry.query) <= 256

    def test_audit_log_records_violations(self):
        """Violations are recorded in audit entries."""
        entry = self.guard.log_research_query(
            "bad query", "BLOCKED", 3, 2,
            ["IMPORT_BLOCKED", "PATH_BLOCKED"]
        )
        assert len(entry.violations) == 2
        assert "IMPORT_BLOCKED" in entry.violations

    def test_clear_audit_log(self):
        """Audit log can be cleared."""
        self.guard.log_research_query("q1", "SUCCESS", 5, 0, [])
        clear_audit_log()
        assert len(get_audit_log()) == 0


class TestIsolationGuardPreQueryCheck:
    """Test full pre-query isolation check."""

    def setup_method(self):
        self.guard = IsolationGuard()

    def test_pre_query_check_passes(self):
        """Pre-query check passes when all isolation walls hold."""
        result = self.guard.pre_query_check("What is Python?")
        assert result.allowed
        assert result.violation is None
        assert "passed" in result.reason.lower()

    def test_pre_query_check_has_timestamp(self):
        """Pre-query result has timestamp."""
        result = self.guard.pre_query_check("What is Python?")
        assert result.timestamp
        assert "T" in result.timestamp


class TestIsolationBlacklists:
    """Test that blacklists are properly populated."""

    def test_blocked_imports_not_empty(self):
        assert len(BLOCKED_IMPORT_PATTERNS) >= 5

    def test_blocked_paths_not_empty(self):
        assert len(BLOCKED_PATH_FRAGMENTS) >= 10

    def test_blocked_extensions_not_empty(self):
        assert len(BLOCKED_EXTENSIONS) >= 8
        assert ".pt" in BLOCKED_EXTENSIONS
        assert ".onnx" in BLOCKED_EXTENSIONS
        assert ".h5" in BLOCKED_EXTENSIONS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
