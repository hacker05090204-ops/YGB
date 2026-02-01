# Phase-37 Tests: Capability Types
"""
Tests for Phase-37 capability governance types.
100% coverage required.
Negative paths dominate.
"""

import pytest
from enum import Enum

from impl_v1.phase37.capability_types import (
    # Enums
    RequestDecision,
    ScopeType,
    DenialReason,
    ConflictType,
    AuditEventType,
    SandboxCapability,
    CapabilityState,
    # Dataclasses
    RequestScope,
    CapabilityRequest,
    CapabilityResponse,
    CapabilityGrant,
    RateLimitState,
    AuditEntry,
    ConflictDetectionResult,
    ValidationResult,
)


# =============================================================================
# ENUM CLOSURE TESTS
# =============================================================================

class TestEnumClosure:
    """Verify all enums are CLOSED with exact member counts."""
    
    def test_request_decision_has_3_members(self):
        """RequestDecision must have exactly 3 members."""
        assert len(RequestDecision) == 3
        assert RequestDecision.GRANTED in RequestDecision
        assert RequestDecision.DENIED in RequestDecision
        assert RequestDecision.PENDING in RequestDecision
    
    def test_scope_type_has_6_members(self):
        """ScopeType must have exactly 6 members."""
        assert len(ScopeType) == 6
        expected = {"MEMORY_RANGE", "TIME_WINDOW", "OPERATION_COUNT", 
                    "BYTE_LIMIT", "SINGLE_USE", "UNBOUNDED"}
        actual = {m.value for m in ScopeType}
        assert actual == expected
    
    def test_denial_reason_has_12_members(self):
        """DenialReason must have exactly 12 members."""
        assert len(DenialReason) == 12
    
    def test_conflict_type_has_5_members(self):
        """ConflictType must have exactly 5 members."""
        assert len(ConflictType) == 5
    
    def test_audit_event_type_has_8_members(self):
        """AuditEventType must have exactly 8 members."""
        assert len(AuditEventType) == 8
    
    def test_sandbox_capability_has_8_members(self):
        """SandboxCapability must have exactly 8 members."""
        assert len(SandboxCapability) == 8
    
    def test_capability_state_has_3_members(self):
        """CapabilityState must have exactly 3 members."""
        assert len(CapabilityState) == 3
        assert CapabilityState.NEVER in CapabilityState
        assert CapabilityState.ESCALATE in CapabilityState
        assert CapabilityState.ALLOW in CapabilityState


# =============================================================================
# DATACLASS FROZEN TESTS
# =============================================================================

class TestDataclassFrozen:
    """Verify all dataclasses are frozen (immutable)."""
    
    def test_request_scope_is_frozen(self):
        """RequestScope must be frozen."""
        scope = RequestScope(
            scope_type=ScopeType.SINGLE_USE,
            scope_value="test",
            scope_limit=1
        )
        with pytest.raises(AttributeError):
            scope.scope_limit = 2
    
    def test_capability_request_is_frozen(self):
        """CapabilityRequest must be frozen."""
        scope = RequestScope(ScopeType.SINGLE_USE, "test", 1)
        request = CapabilityRequest(
            request_id="REQ-0123456789ABCDEF",
            capability=SandboxCapability.MEMORY_READ,
            intent_description="test",
            requested_scope=scope,
            timestamp="2026-01-27T00:00:00Z",
            expiry="2026-01-27T01:00:00Z",
            context_hash="a" * 64,
            requester_id="test"
        )
        with pytest.raises(AttributeError):
            request.intent_description = "modified"
    
    def test_capability_response_is_frozen(self):
        """CapabilityResponse must be frozen."""
        response = CapabilityResponse(
            request_id="REQ-0123456789ABCDEF",
            decision=RequestDecision.DENIED,
            reason_code="TEST",
            reason_description="test",
            grant_token="",
            grant_expiry="",
            requires_human=False
        )
        with pytest.raises(AttributeError):
            response.decision = RequestDecision.GRANTED
    
    def test_capability_grant_is_frozen(self):
        """CapabilityGrant must be frozen."""
        scope = RequestScope(ScopeType.SINGLE_USE, "test", 1)
        grant = CapabilityGrant(
            grant_id="GRANT-0123456789ABCDEF",
            request_id="REQ-0123456789ABCDEF",
            capability=SandboxCapability.MEMORY_READ,
            scope=scope,
            granted_at="2026-01-27T00:00:00Z",
            expires_at="2026-01-27T01:00:00Z",
            context_hash="a" * 64,
            consumed=False
        )
        with pytest.raises(AttributeError):
            grant.consumed = True
    
    def test_validation_result_is_frozen(self):
        """ValidationResult must be frozen."""
        result = ValidationResult(
            is_valid=True,
            denial_reason=None,
            description="test"
        )
        with pytest.raises(AttributeError):
            result.is_valid = False


# =============================================================================
# ENUM VALUE TESTS
# =============================================================================

class TestEnumValues:
    """Verify enum values are correct strings."""
    
    def test_request_decision_values(self):
        """RequestDecision values must match design."""
        assert RequestDecision.GRANTED.value == "GRANTED"
        assert RequestDecision.DENIED.value == "DENIED"
        assert RequestDecision.PENDING.value == "PENDING"
    
    def test_denial_reason_values(self):
        """DenialReason values must be uppercase with underscores."""
        for reason in DenialReason:
            assert reason.value == reason.name
            assert reason.value.isupper() or "_" in reason.value
    
    def test_capability_state_values(self):
        """CapabilityState values must match design."""
        assert CapabilityState.NEVER.value == "NEVER"
        assert CapabilityState.ESCALATE.value == "ESCALATE"
        assert CapabilityState.ALLOW.value == "ALLOW"


# =============================================================================
# NEGATIVE TESTS - DATACLASS CONSTRUCTION
# =============================================================================

class TestDataclassConstruction:
    """Test dataclass construction requirements."""
    
    def test_request_scope_requires_all_fields(self):
        """RequestScope requires all fields."""
        with pytest.raises(TypeError):
            RequestScope(scope_type=ScopeType.SINGLE_USE)
    
    def test_capability_request_requires_all_fields(self):
        """CapabilityRequest requires all fields."""
        with pytest.raises(TypeError):
            CapabilityRequest(request_id="test")
    
    def test_validation_result_allows_none_denial_reason(self):
        """ValidationResult allows None for denial_reason when valid."""
        result = ValidationResult(
            is_valid=True,
            denial_reason=None,
            description="Valid"
        )
        assert result.denial_reason is None
