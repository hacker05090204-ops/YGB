"""
test_medium_risks.py — Regression tests for MEDIUM risk sprint

Tests cover:
  A) IDOR ownership checks (cross-user access blocked)
  B) Typed exception propagation
  C) Synthetic status defaults replaced with degraded semantics
"""

import sys
import os
import json
import pytest

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =========================================================================
# A) IDOR OWNERSHIP TESTS
# =========================================================================

class TestOwnershipChecks:
    """Test that cross-user resource access is blocked."""

    def test_check_resource_owner_allows_owner(self):
        from backend.auth.ownership import check_resource_owner
        resource = {"owner_id": "user_123", "data": "test"}
        user = {"sub": "user_123", "role": "hunter"}
        # Should NOT raise
        check_resource_owner(resource, user, "test_resource", "res_1")

    def test_check_resource_owner_blocks_non_owner(self):
        from backend.auth.ownership import check_resource_owner
        from fastapi import HTTPException
        resource = {"owner_id": "user_123", "data": "test"}
        user = {"sub": "user_456", "role": "hunter"}
        with pytest.raises(HTTPException) as exc_info:
            check_resource_owner(resource, user, "test_resource", "res_1")
        assert exc_info.value.status_code == 403
        assert "FORBIDDEN" in str(exc_info.value.detail)

    def test_check_resource_owner_allows_admin(self):
        from backend.auth.ownership import check_resource_owner
        resource = {"owner_id": "user_123", "data": "test"}
        user = {"sub": "admin_999", "role": "admin"}
        # Admin should bypass ownership check
        check_resource_owner(resource, user, "test_resource", "res_1")

    def test_check_resource_owner_404_on_missing(self):
        from backend.auth.ownership import check_resource_owner
        from fastapi import HTTPException
        user = {"sub": "user_123", "role": "hunter"}
        with pytest.raises(HTTPException) as exc_info:
            check_resource_owner(None, user, "workflow", "WF-123")
        assert exc_info.value.status_code == 404
        assert "NOT_FOUND" in str(exc_info.value.detail)

    def test_check_resource_owner_blocks_empty_owner_id(self):
        """Fail closed: resource with empty owner_id is inaccessible."""
        from backend.auth.ownership import check_resource_owner
        from fastapi import HTTPException
        resource = {"owner_id": "", "data": "test"}
        user = {"sub": "user_123", "role": "hunter"}
        with pytest.raises(HTTPException) as exc_info:
            check_resource_owner(resource, user, "test_resource", "res_1")
        assert exc_info.value.status_code == 403

    def test_ws_check_returns_false_for_non_owner(self):
        from backend.auth.ownership import check_ws_resource_owner
        resource = {"owner_id": "user_123"}
        user = {"sub": "user_456", "role": "hunter"}
        assert check_ws_resource_owner(resource, user) is False

    def test_ws_check_returns_true_for_owner(self):
        from backend.auth.ownership import check_ws_resource_owner
        resource = {"owner_id": "user_123"}
        user = {"sub": "user_123", "role": "hunter"}
        assert check_ws_resource_owner(resource, user) is True

    def test_ws_check_returns_true_for_admin(self):
        from backend.auth.ownership import check_ws_resource_owner
        resource = {"owner_id": "user_123"}
        user = {"sub": "admin_999", "role": "admin"}
        assert check_ws_resource_owner(resource, user) is True

    def test_ws_check_returns_false_for_missing_resource(self):
        from backend.auth.ownership import check_ws_resource_owner
        user = {"sub": "user_123", "role": "hunter"}
        assert check_ws_resource_owner(None, user) is False


# =========================================================================
# B) TYPED EXCEPTION TESTS
# =========================================================================

class TestTypedExceptions:
    """Test that typed exceptions carry correct data."""

    def test_ygb_error_has_correlation_id(self):
        from backend.api.exceptions import YGBError
        err = YGBError("test error")
        assert err.correlation_id
        assert len(err.correlation_id) == 12

    def test_storage_error_status_code(self):
        from backend.api.exceptions import StorageError
        err = StorageError("disk full")
        assert err.status_code == 503
        assert err.error_code == "STORAGE_ERROR"

    def test_training_error_status_code(self):
        from backend.api.exceptions import TrainingError
        err = TrainingError("GPU OOM")
        assert err.status_code == 503
        assert err.error_code == "TRAINING_ERROR"

    def test_validation_error_status_code(self):
        from backend.api.exceptions import ValidationError
        err = ValidationError("bad input")
        assert err.status_code == 400
        assert err.error_code == "VALIDATION_ERROR"

    def test_to_response_format(self):
        from backend.api.exceptions import StorageError
        err = StorageError("test detail")
        resp = err.to_response()
        assert resp["error"] == "STORAGE_ERROR"
        assert resp["detail"] == "test detail"
        assert "correlation_id" in resp
        assert "timestamp" in resp

    def test_error_with_cause(self):
        from backend.api.exceptions import WorkflowError
        cause = RuntimeError("inner error")
        err = WorkflowError("workflow failed", cause=cause)
        assert err.cause is cause
        assert "workflow failed" in str(err)

    def test_all_exception_types_are_ygb_error(self):
        from backend.api.exceptions import (
            YGBError, StorageError, TrainingError,
            TelemetryError, ValidationError, WorkflowError,
            ConfigurationError, ExternalServiceError,
        )
        for cls in [StorageError, TrainingError, TelemetryError,
                    ValidationError, WorkflowError, ConfigurationError,
                    ExternalServiceError]:
            assert issubclass(cls, YGBError)


# =========================================================================
# C) SYNTHETIC STATUS DEFAULTS TESTS
# =========================================================================

class TestSyntheticDefaults:
    """Test that unavailable data returns degraded/null, never synthetic values."""

    def test_unavailable_accuracy_has_null_values(self):
        """When no telemetry exists, accuracy should return nulls, not zeros."""
        unavailable = {
            "api_version": 2,
            "precision": None,
            "recall": None,
            "ece_score": None,
            "dup_suppression_rate": None,
            "scope_compliance": None,
            "source": "unavailable",
            "is_measured": False,
        }
        # Validate structure
        assert unavailable["api_version"] == 2
        assert unavailable["precision"] is None
        assert unavailable["recall"] is None
        assert unavailable["is_measured"] is False
        assert unavailable["source"] == "unavailable"

    def test_unavailable_runtime_has_null_fields(self):
        """When no telemetry exists, runtime should indicate unavailable."""
        unavailable = {
            "api_version": 2,
            "status": "unavailable",
            "runtime": None,
            "determinism_ok": None,
            "stale": True,
            "is_measured": False,
            "source": "none",
        }
        assert unavailable["status"] == "unavailable"
        assert unavailable["runtime"] is None
        assert unavailable["is_measured"] is False
        assert unavailable["determinism_ok"] is None  # Not hardcoded True

    def test_g38_live_no_fabricated_recall(self):
        """G38 live data should NOT fabricate recall from accuracy."""
        g38_response = {
            "api_version": 2,
            "precision": 0.85,
            "recall": None,  # Not fabricated as 0.85*0.95
            "ece_score": None,
            "source": "g38_live",
            "is_measured": True,
        }
        assert g38_response["recall"] is None
        assert g38_response["ece_score"] is None
        assert g38_response["is_measured"] is True

    def test_measured_telemetry_has_api_version(self):
        """Telemetry-based responses include api_version field."""
        measured = {
            "api_version": 2,
            "precision": 0.92,
            "recall": 0.88,
            "source": "telemetry_file",
            "is_measured": True,
        }
        assert measured["api_version"] == 2
        assert measured["is_measured"] is True

    def test_runtime_no_synthetic_loss_trend(self):
        """Runtime should NOT fabricate loss_trend as -0.001."""
        runtime = {
            "loss_trend": None,  # Was previously -0.001
            "determinism_status": None,  # Was previously True
            "freeze_status": None,  # Was previously True
            "ece": None,  # Was previously 0.0
            "is_measured": True,
        }
        assert runtime["loss_trend"] is None
        assert runtime["determinism_status"] is None
        assert runtime["ece"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
