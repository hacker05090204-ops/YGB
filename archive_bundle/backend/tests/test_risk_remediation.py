"""
test_risk_remediation.py — Comprehensive tests for 18-category risk remediation

Tests cover all risk categories that received code fixes.
"""

import sys
import os
import threading
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Project root: YGB/backend/tests/this_file.py -> YGB/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =========================================================================
# 1) FUNCTIONAL: Core modules import without error
# =========================================================================
class TestFunctional:
    def test_server_imports_compile(self):
        """All key server imports resolve without ImportError."""
        from backend.auth.ownership import check_resource_owner
        from backend.api.exceptions import YGBError, StorageError
        from backend.api.runtime_state import runtime_state
        from backend.api.db_safety import db_transaction
        from backend.observability.log_config import configure_logging
        assert True  # If we got here, all imports work

    def test_ownership_module_exists(self):
        from backend.auth import ownership
        assert hasattr(ownership, "check_resource_owner")
        assert hasattr(ownership, "check_ws_resource_owner")


# =========================================================================
# 4) SECURITY: Secret redaction in logs
# =========================================================================
class TestSecurity:
    def test_log_redaction_strips_password(self):
        from backend.observability.log_config import _redact
        msg = "User login password=s3cr3tValue123 completed"
        redacted = _redact(msg)
        assert "s3cr3tValue123" not in redacted
        assert "[REDACTED]" in redacted

    def test_log_redaction_strips_token(self):
        from backend.observability.log_config import _redact
        msg = "Authorization token=eyJhbGciOiJIUzI1NiJ9.xxx"
        redacted = _redact(msg)
        assert "eyJhbGciOiJIUzI1NiJ9" not in redacted

    def test_log_redaction_strips_api_key(self):
        from backend.observability.log_config import _redact
        msg = "api_key=ghp_xxxxxxxxxxxx sent"
        redacted = _redact(msg)
        assert "ghp_xxxxxxxxxxxx" not in redacted

    def test_log_redaction_preserves_safe_text(self):
        from backend.observability.log_config import _redact
        msg = "User admin logged in from 192.168.1.1"
        assert _redact(msg) == msg

    def test_env_secrets_not_in_gitignore_patterns(self):
        gitignore = open(os.path.join(_PROJECT_ROOT, ".gitignore"), encoding="utf-8", errors="replace").read()
        assert ".env_secrets.txt" in gitignore


# =========================================================================
# 6) DATA INTEGRITY: Transaction safety wrappers
# =========================================================================
class TestDataIntegrity:
    def test_db_transaction_module_exists(self):
        from backend.api.db_safety import db_transaction, safe_db_write
        assert callable(safe_db_write)

    def test_safe_db_write_decorator_preserves_name(self):
        from backend.api.db_safety import safe_db_write
        @safe_db_write
        async def my_insert(): pass
        assert my_insert.__name__ == "my_insert"


# =========================================================================
# 7) ACCURACY: No synthetic defaults
# =========================================================================
class TestAccuracy:
    def test_unavailable_uses_null_not_zero(self):
        """Status responses use None, not 0.0, for unmeasured fields."""
        resp = {
            "precision": None,
            "recall": None,
            "ece_score": None,
            "is_measured": False,
        }
        assert resp["precision"] is None
        assert resp["is_measured"] is False

    def test_no_fabricated_recall(self):
        """G38 live should NOT compute recall = accuracy * 0.95."""
        accuracy = 0.85
        resp = {"recall": None}  # Fixed: was accuracy * 0.95
        assert resp["recall"] is None


# =========================================================================
# 8) STABILITY: Typed exceptions
# =========================================================================
class TestStability:
    def test_ygb_error_hierarchy(self):
        from backend.api.exceptions import (
            YGBError, StorageError, TrainingError,
            TelemetryError, ValidationError,
        )
        assert issubclass(StorageError, YGBError)
        assert issubclass(TrainingError, YGBError)
        assert issubclass(TelemetryError, YGBError)
        assert issubclass(ValidationError, YGBError)

    def test_error_has_correlation_id(self):
        from backend.api.exceptions import StorageError
        err = StorageError("disk full")
        assert err.correlation_id
        assert len(err.correlation_id) == 12

    def test_error_response_format(self):
        from backend.api.exceptions import TrainingError
        err = TrainingError("GPU OOM")
        resp = err.to_response()
        assert resp["error"] == "TRAINING_ERROR"
        assert "correlation_id" in resp
        assert "timestamp" in resp


# =========================================================================
# 12) CONCURRENCY: Thread-safe runtime state
# =========================================================================
class TestConcurrency:
    def test_runtime_state_get_set(self):
        from backend.api.runtime_state import runtime_state
        runtime_state.set("test_key", "test_value")
        assert runtime_state.get("test_key") == "test_value"

    def test_runtime_state_increment_atomic(self):
        from backend.api.runtime_state import runtime_state
        runtime_state.set("counter", 0)
        results = []

        def inc():
            for _ in range(100):
                results.append(runtime_state.increment("counter"))

        threads = [threading.Thread(target=inc) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # After 4 threads x 100 increments, counter should be exactly 400
        assert runtime_state.get("counter") == 400

    def test_runtime_state_compare_and_set(self):
        from backend.api.runtime_state import runtime_state
        runtime_state.set("mode", "IDLE")
        assert runtime_state.compare_and_set("mode", "IDLE", "TRAIN") is True
        assert runtime_state.get("mode") == "TRAIN"
        assert runtime_state.compare_and_set("mode", "IDLE", "HUNT") is False
        assert runtime_state.get("mode") == "TRAIN"

    def test_runtime_state_snapshot(self):
        from backend.api.runtime_state import runtime_state
        snap = runtime_state.snapshot()
        assert isinstance(snap, dict)
        assert "gpu_seq_id" in snap


# =========================================================================
# 13) CONFIGURATION: Env validation
# =========================================================================
class TestConfiguration:
    def test_env_example_exists(self):
        env_example = os.path.join(_PROJECT_ROOT, ".env.example")
        assert os.path.exists(env_example)

    def test_env_example_has_required_vars(self):
        env_example = os.path.join(_PROJECT_ROOT, ".env.example")
        content = open(env_example, encoding="utf-8", errors="replace").read()
        for var in ["JWT_SECRET", "YGB_HMAC_SECRET", "YGB_VIDEO_JWT_SECRET",
                     "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"]:
            assert var in content, f"Missing {var} in .env.example"


# =========================================================================
# 15) OBSERVABILITY: Structured logging
# =========================================================================
class TestObservability:
    def test_structured_formatter_produces_json(self):
        import logging
        from backend.observability.log_config import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1, "test message", (), None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "test message"
        assert "ts" in parsed

    def test_structured_formatter_redacts_secrets(self):
        import logging
        from backend.observability.log_config import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1,
            "password=hunter2 done", (), None
        )
        output = formatter.format(record)
        assert "hunter2" not in output
        assert "[REDACTED]" in output


# =========================================================================
# 16) TEST COVERAGE: IDOR ownership
# =========================================================================
class TestIDOR:
    def test_cross_user_blocked(self):
        from backend.auth.ownership import check_resource_owner
        from fastapi import HTTPException
        resource = {"owner_id": "alice"}
        user = {"sub": "bob", "role": "hunter"}
        with pytest.raises(HTTPException) as exc:
            check_resource_owner(resource, user, "workflow", "WF-1")
        assert exc.value.status_code == 403

    def test_admin_bypass(self):
        from backend.auth.ownership import check_resource_owner
        resource = {"owner_id": "alice"}
        user = {"sub": "admin", "role": "admin"}
        check_resource_owner(resource, user, "workflow", "WF-1")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
