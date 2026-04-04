# Test G38 External Failover
"""
Comprehensive tests for G38 External AI Failover Governance.

Tests cover:
- Failover state management
- Failover condition checks
- REPAIR_MODE activation and recovery
- Logging requirements
- Dashboard visibility
- Guard enforcement
"""

import pytest
from unittest.mock import patch

from impl_v1.phase49.governors.g38_external_failover import (
    # State Enums
    FailoverState,
    FailoverReason,
    # Data Classes
    FailoverStatus,
    FailoverLogEntry,
    FailoverRegistry,
    # Condition Checks
    check_failover_conditions,
    # Registry Management
    create_failover_registry,
    activate_failover,
    record_failover_usage,
    recover_from_failover,
    # Usage Controls
    is_external_ai_allowed,
    validate_external_ai_request,
    # Guards
    can_failover_activate_silently,
    can_failover_run_continuously,
    can_failover_be_primary,
    can_failover_send_telemetry,
    can_failover_train_remotely,
    can_failover_hide_usage,
    # Summary
    get_failover_summary,
)


# =============================================================================
# FAILOVER STATE TESTS
# =============================================================================

class TestFailoverState:
    """Tests for failover state enum."""
    
    def test_has_disabled(self):
        assert FailoverState.DISABLED.value == "DISABLED"
    
    def test_has_repair_mode(self):
        assert FailoverState.REPAIR_MODE.value == "REPAIR_MODE"
    
    def test_has_recovering(self):
        assert FailoverState.RECOVERING.value == "RECOVERING"
    
    def test_has_error(self):
        assert FailoverState.ERROR.value == "ERROR"


class TestFailoverReason:
    """Tests for failover reason enum."""
    
    def test_has_none(self):
        assert FailoverReason.NONE.value == "NONE"
    
    def test_has_integrity_check_failed(self):
        assert FailoverReason.INTEGRITY_CHECK_FAILED.value == "INTEGRITY_CHECK_FAILED"
    
    def test_has_checkpoint_corruption(self):
        assert FailoverReason.CHECKPOINT_CORRUPTION.value == "CHECKPOINT_CORRUPTION"
    
    def test_has_training_error(self):
        assert FailoverReason.TRAINING_ERROR.value == "TRAINING_ERROR"
    
    def test_has_inference_error(self):
        assert FailoverReason.INFERENCE_ERROR.value == "INFERENCE_ERROR"
    
    def test_has_model_unavailable(self):
        assert FailoverReason.MODEL_UNAVAILABLE.value == "MODEL_UNAVAILABLE"


# =============================================================================
# FAILOVER CONDITION TESTS
# =============================================================================

class TestFailoverConditions:
    """Tests for failover condition checks."""
    
    def test_all_ok_no_failover(self):
        should_activate, reason = check_failover_conditions(
            integrity_ok=True,
            checkpoint_valid=True,
            training_error=None,
            inference_error=None,
            model_available=True,
        )
        assert should_activate is False
        assert reason == FailoverReason.NONE
    
    def test_integrity_failed_triggers_failover(self):
        should_activate, reason = check_failover_conditions(
            integrity_ok=False,
            checkpoint_valid=True,
            training_error=None,
            inference_error=None,
            model_available=True,
        )
        assert should_activate is True
        assert reason == FailoverReason.INTEGRITY_CHECK_FAILED
    
    def test_checkpoint_corruption_triggers_failover(self):
        should_activate, reason = check_failover_conditions(
            integrity_ok=True,
            checkpoint_valid=False,
            training_error=None,
            inference_error=None,
            model_available=True,
        )
        assert should_activate is True
        assert reason == FailoverReason.CHECKPOINT_CORRUPTION
    
    def test_training_error_triggers_failover(self):
        should_activate, reason = check_failover_conditions(
            integrity_ok=True,
            checkpoint_valid=True,
            training_error="CUDA out of memory",
            inference_error=None,
            model_available=True,
        )
        assert should_activate is True
        assert reason == FailoverReason.TRAINING_ERROR
    
    def test_inference_error_triggers_failover(self):
        should_activate, reason = check_failover_conditions(
            integrity_ok=True,
            checkpoint_valid=True,
            training_error=None,
            inference_error="Model weight mismatch",
            model_available=True,
        )
        assert should_activate is True
        assert reason == FailoverReason.INFERENCE_ERROR
    
    def test_model_unavailable_triggers_failover(self):
        should_activate, reason = check_failover_conditions(
            integrity_ok=True,
            checkpoint_valid=True,
            training_error=None,
            inference_error=None,
            model_available=False,
        )
        assert should_activate is True
        assert reason == FailoverReason.MODEL_UNAVAILABLE


# =============================================================================
# REGISTRY MANAGEMENT TESTS
# =============================================================================

class TestFailoverRegistry:
    """Tests for failover registry management."""
    
    def test_create_registry_starts_disabled(self):
        registry = create_failover_registry()
        assert registry.current_status.state == FailoverState.DISABLED
        assert registry.current_status.external_ai_active is False
    
    def test_create_registry_is_logged(self):
        registry = create_failover_registry()
        assert registry.current_status.logged is True
    
    def test_create_registry_is_visible(self):
        registry = create_failover_registry()
        assert registry.current_status.dashboard_visible is True
    
    def test_activate_failover_changes_state(self):
        registry = create_failover_registry()
        updated = activate_failover(
            registry,
            FailoverReason.INTEGRITY_CHECK_FAILED,
            "Model hash mismatch",
        )
        assert updated.current_status.state == FailoverState.REPAIR_MODE
        assert updated.current_status.external_ai_active is True
    
    def test_activate_failover_logs_event(self):
        registry = create_failover_registry()
        updated = activate_failover(
            registry,
            FailoverReason.CHECKPOINT_CORRUPTION,
            "Checkpoint file corrupted",
        )
        assert len(updated.log_entries) == 1
        assert updated.log_entries[0].event_type == "ACTIVATED"
    
    def test_activate_failover_increments_count(self):
        registry = create_failover_registry()
        updated = activate_failover(
            registry,
            FailoverReason.TRAINING_ERROR,
            "CUDA error",
        )
        assert updated.total_activations == 1
    
    def test_activate_failover_requires_reason(self):
        registry = create_failover_registry()
        with pytest.raises(ValueError):
            activate_failover(registry, FailoverReason.NONE, "No reason")
    
    def test_record_usage_logs_event(self):
        registry = create_failover_registry()
        registry = activate_failover(
            registry,
            FailoverReason.INFERENCE_ERROR,
            "Model crashed",
        )
        updated = record_failover_usage(registry, "Used for inference recovery")
        assert len(updated.log_entries) == 2
        assert updated.log_entries[1].event_type == "USED"
    
    def test_record_usage_requires_repair_mode(self):
        registry = create_failover_registry()
        with pytest.raises(RuntimeError):
            record_failover_usage(registry, "Should fail")
    
    def test_recover_from_failover_disables_external(self):
        registry = create_failover_registry()
        registry = activate_failover(
            registry,
            FailoverReason.MODEL_UNAVAILABLE,
            "Model not found",
        )
        updated = recover_from_failover(registry, "Model restored")
        assert updated.current_status.state == FailoverState.DISABLED
        assert updated.current_status.external_ai_active is False
    
    def test_recover_logs_recovery(self):
        registry = create_failover_registry()
        registry = activate_failover(
            registry,
            FailoverReason.TRAINING_ERROR,
            "Error",
        )
        updated = recover_from_failover(registry, "Fixed")
        assert updated.log_entries[-1].event_type == "RECOVERED"
    
    def test_recover_sets_last_recovery(self):
        registry = create_failover_registry()
        registry = activate_failover(
            registry,
            FailoverReason.CHECKPOINT_CORRUPTION,
            "Corrupt",
        )
        updated = recover_from_failover(registry, "Restored")
        assert updated.last_recovery is not None


# =============================================================================
# USAGE CONTROL TESTS
# =============================================================================

class TestUsageControls:
    """Tests for external AI usage controls."""
    
    def test_disabled_state_blocks_external_ai(self):
        registry = create_failover_registry()
        allowed, reason = is_external_ai_allowed(registry)
        assert allowed is False
    
    def test_repair_mode_allows_external_ai(self):
        registry = create_failover_registry()
        registry = activate_failover(
            registry,
            FailoverReason.INTEGRITY_CHECK_FAILED,
            "Test",
        )
        allowed, reason = is_external_ai_allowed(registry)
        assert allowed is True
        assert "REPAIR_MODE" in reason
    
    def test_validate_request_in_disabled_state(self):
        registry = create_failover_registry()
        allowed, reason = validate_external_ai_request(registry, "inference")
        assert allowed is False
    
    def test_validate_request_in_repair_mode(self):
        registry = create_failover_registry()
        registry = activate_failover(
            registry,
            FailoverReason.MODEL_UNAVAILABLE,
            "Test",
        )
        allowed, reason = validate_external_ai_request(registry, "inference")
        assert allowed is True


# =============================================================================
# GUARD TESTS
# =============================================================================

class TestFailoverGuards:
    """Tests for failover guards."""
    
    def test_can_failover_activate_silently_returns_false(self):
        result, msg = can_failover_activate_silently()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_failover_run_continuously_returns_false(self):
        result, msg = can_failover_run_continuously()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_failover_be_primary_returns_false(self):
        result, msg = can_failover_be_primary()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_failover_send_telemetry_returns_false(self):
        result, msg = can_failover_send_telemetry()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_failover_train_remotely_returns_false(self):
        result, msg = can_failover_train_remotely()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_failover_hide_usage_returns_false(self):
        result, msg = can_failover_hide_usage()
        assert result is False
        assert isinstance(msg, str)


# =============================================================================
# SUMMARY TESTS
# =============================================================================

class TestFailoverSummary:
    """Tests for failover summary."""
    
    def test_get_summary_returns_string(self):
        registry = create_failover_registry()
        summary = get_failover_summary(registry)
        assert isinstance(summary, str)
    
    def test_summary_contains_state(self):
        registry = create_failover_registry()
        summary = get_failover_summary(registry)
        assert "DISABLED" in summary
    
    def test_summary_contains_external_ai_status(self):
        registry = create_failover_registry()
        summary = get_failover_summary(registry)
        assert "External AI Active" in summary


# =============================================================================
# EXTERNAL AI DETECTION TESTS
# =============================================================================

class TestNoExternalAIInModule:
    """Tests that no external AI is imported."""
    
    def test_no_huggingface_import(self):
        import impl_v1.phase49.governors.g38_external_failover as module
        source = open(module.__file__, encoding='utf-8', errors='ignore').read()
        assert "hugging" not in source.lower()
    
    def test_no_openai_import(self):
        import impl_v1.phase49.governors.g38_external_failover as module
        source = open(module.__file__, encoding='utf-8', errors='ignore').read()
        assert "openai" not in source.lower()
    
    def test_no_anthropic_import(self):
        import impl_v1.phase49.governors.g38_external_failover as module
        source = open(module.__file__, encoding='utf-8', errors='ignore').read()
        assert "anthropic" not in source.lower()
