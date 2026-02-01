# Phase-37 Tests: Capability Validator
"""
Tests for Phase-37 capability request validation.
100% coverage required.
Negative paths dominate.
"""

import pytest
from datetime import datetime, timedelta

from impl_v1.phase37.capability_types import (
    RequestScope,
    CapabilityRequest,
    SandboxCapability,
    CapabilityState,
    ScopeType,
    DenialReason,
)

from impl_v1.phase37.capability_validator import (
    get_capability_state,
    validate_request_id,
    validate_timestamp,
    validate_expiry_after_timestamp,
    validate_scope,
    validate_context_hash,
    validate_intent_description,
    scope_requires_escalate,
    validate_capability_request,
    NEVER_CAPABILITIES,
    ESCALATE_CAPABILITIES,
    ALLOW_CAPABILITIES,
    reset_replay_detection,
    reset_rate_limits,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    reset_replay_detection()
    reset_rate_limits()
    yield


def make_valid_request(
    request_id: str = "REQ-0123456789ABCDEF",
    capability: SandboxCapability = SandboxCapability.MEMORY_READ,
    requester_id: str = "test-requester"
) -> CapabilityRequest:
    """Create a valid capability request for testing."""
    now = datetime.utcnow()
    expiry = now + timedelta(hours=1)
    return CapabilityRequest(
        request_id=request_id,
        capability=capability,
        intent_description="Test request for validation",
        requested_scope=RequestScope(
            scope_type=ScopeType.SINGLE_USE,
            scope_value="test-scope",
            scope_limit=1
        ),
        timestamp=now.isoformat() + "Z",
        expiry=expiry.isoformat() + "Z",
        context_hash="a" * 64,
        requester_id=requester_id
    )


# =============================================================================
# CAPABILITY STATE TESTS
# =============================================================================

class TestCapabilityState:
    """Test capability state classification."""
    
    def test_never_capabilities(self):
        """NETWORK, FILESYSTEM, PROCESS are NEVER."""
        assert get_capability_state(SandboxCapability.NETWORK) == CapabilityState.NEVER
        assert get_capability_state(SandboxCapability.FILESYSTEM) == CapabilityState.NEVER
        assert get_capability_state(SandboxCapability.PROCESS) == CapabilityState.NEVER
    
    def test_escalate_capabilities(self):
        """MEMORY_WRITE requires ESCALATE."""
        assert get_capability_state(SandboxCapability.MEMORY_WRITE) == CapabilityState.ESCALATE
    
    def test_allow_capabilities(self):
        """MEMORY_READ, HEAP_ALLOCATE, INPUT_READ, OUTPUT_WRITE are ALLOW."""
        assert get_capability_state(SandboxCapability.MEMORY_READ) == CapabilityState.ALLOW
        assert get_capability_state(SandboxCapability.HEAP_ALLOCATE) == CapabilityState.ALLOW
        assert get_capability_state(SandboxCapability.INPUT_READ) == CapabilityState.ALLOW
        assert get_capability_state(SandboxCapability.OUTPUT_WRITE) == CapabilityState.ALLOW
    
    def test_never_capabilities_set(self):
        """NEVER_CAPABILITIES contains correct capabilities."""
        assert SandboxCapability.NETWORK in NEVER_CAPABILITIES
        assert SandboxCapability.FILESYSTEM in NEVER_CAPABILITIES
        assert SandboxCapability.PROCESS in NEVER_CAPABILITIES
        assert len(NEVER_CAPABILITIES) == 3


# =============================================================================
# REQUEST ID VALIDATION TESTS
# =============================================================================

class TestRequestIdValidation:
    """Test request ID format validation."""
    
    def test_valid_request_id(self):
        """Valid REQ-[16 hex chars] format passes."""
        assert validate_request_id("REQ-0123456789ABCDEF") is True
        assert validate_request_id("REQ-abcdef0123456789") is True
    
    def test_invalid_request_id_empty(self):
        """Empty request ID fails."""
        assert validate_request_id("") is False
        assert validate_request_id(None) is False
    
    def test_invalid_request_id_wrong_prefix(self):
        """Wrong prefix fails."""
        assert validate_request_id("REX-0123456789ABCDEF") is False
        assert validate_request_id("0123456789ABCDEF") is False
    
    def test_invalid_request_id_wrong_length(self):
        """Wrong length fails."""
        assert validate_request_id("REQ-0123456789ABC") is False  # Too short
        assert validate_request_id("REQ-0123456789ABCDEF0") is False  # Too long
    
    def test_invalid_request_id_invalid_chars(self):
        """Non-hex characters fail."""
        assert validate_request_id("REQ-GHIJKLMNOPQRSTUV") is False


# =============================================================================
# TIMESTAMP VALIDATION TESTS
# =============================================================================

class TestTimestampValidation:
    """Test timestamp format validation."""
    
    def test_valid_timestamps(self):
        """Valid ISO 8601 timestamps pass."""
        assert validate_timestamp("2026-01-27T00:00:00Z") is True
        assert validate_timestamp("2026-01-27T00:00:00+00:00") is True
        assert validate_timestamp("2026-01-27T12:30:45.123456Z") is True
    
    def test_invalid_timestamp_empty(self):
        """Empty timestamp fails."""
        assert validate_timestamp("") is False
        assert validate_timestamp(None) is False
    
    def test_invalid_timestamp_format(self):
        """Invalid format fails."""
        assert validate_timestamp("not-a-timestamp") is False
        assert validate_timestamp("") is False
    
    def test_expiry_after_timestamp(self):
        """Expiry must be after timestamp."""
        ts = "2026-01-27T00:00:00Z"
        exp_valid = "2026-01-27T01:00:00Z"
        exp_invalid = "2026-01-26T23:00:00Z"
        
        assert validate_expiry_after_timestamp(ts, exp_valid) is True
        assert validate_expiry_after_timestamp(ts, exp_invalid) is False
        assert validate_expiry_after_timestamp(ts, ts) is False  # Equal not allowed


# =============================================================================
# SCOPE VALIDATION TESTS
# =============================================================================

class TestScopeValidation:
    """Test scope validation."""
    
    def test_valid_scope(self):
        """Valid scope passes."""
        scope = RequestScope(ScopeType.SINGLE_USE, "test", 1)
        assert validate_scope(scope) is True
    
    def test_invalid_scope_none(self):
        """None scope fails."""
        assert validate_scope(None) is False
    
    def test_invalid_scope_empty_value(self):
        """Empty scope value fails."""
        scope = RequestScope(ScopeType.SINGLE_USE, "", 1)
        assert validate_scope(scope) is False
    
    def test_invalid_scope_zero_limit(self):
        """Zero limit fails (except UNBOUNDED)."""
        scope = RequestScope(ScopeType.SINGLE_USE, "test", 0)
        assert validate_scope(scope) is False
    
    def test_unbounded_scope_requires_escalate(self):
        """UNBOUNDED scope requires escalation."""
        scope = RequestScope(ScopeType.UNBOUNDED, "test", 0)
        assert scope_requires_escalate(scope) is True
    
    def test_bounded_scope_no_escalate(self):
        """Bounded scope does not require escalation."""
        scope = RequestScope(ScopeType.SINGLE_USE, "test", 1)
        assert scope_requires_escalate(scope) is False


# =============================================================================
# CONTEXT HASH VALIDATION TESTS
# =============================================================================

class TestContextHashValidation:
    """Test context hash validation."""
    
    def test_valid_context_hash(self):
        """Valid SHA-256 hash passes."""
        assert validate_context_hash("a" * 64) is True
        assert validate_context_hash("0123456789abcdef" * 4) is True
    
    def test_invalid_context_hash_empty(self):
        """Empty hash fails."""
        assert validate_context_hash("") is False
        assert validate_context_hash(None) is False
    
    def test_invalid_context_hash_wrong_length(self):
        """Wrong length fails."""
        assert validate_context_hash("a" * 63) is False
        assert validate_context_hash("a" * 65) is False
    
    def test_invalid_context_hash_invalid_chars(self):
        """Non-hex characters fail."""
        assert validate_context_hash("g" * 64) is False


# =============================================================================
# INTENT DESCRIPTION VALIDATION TESTS
# =============================================================================

class TestIntentDescriptionValidation:
    """Test intent description validation."""
    
    def test_valid_intent(self):
        """Valid intent passes."""
        assert validate_intent_description("Test intent") is True
        assert validate_intent_description("a") is True
    
    def test_invalid_intent_empty(self):
        """Empty intent fails."""
        assert validate_intent_description("") is False
        assert validate_intent_description(None) is False
    
    def test_invalid_intent_too_long(self):
        """Intent > 256 chars fails."""
        assert validate_intent_description("a" * 257) is False
        assert validate_intent_description("a" * 256) is True  # Boundary


# =============================================================================
# FULL VALIDATION TESTS
# =============================================================================

class TestFullValidation:
    """Test full capability request validation."""
    
    def test_valid_request_passes(self):
        """Valid request passes all checks."""
        request = make_valid_request()
        result = validate_capability_request(request)
        assert result.is_valid is True
        assert result.denial_reason is None
    
    def test_never_capability_denied(self):
        """NEVER capability is denied."""
        request = make_valid_request(capability=SandboxCapability.NETWORK)
        result = validate_capability_request(request)
        assert result.is_valid is False
        assert result.denial_reason == DenialReason.NEVER_CAPABILITY
    
    def test_invalid_request_id_denied(self):
        """Invalid request ID is denied."""
        request = make_valid_request(request_id="INVALID")
        result = validate_capability_request(request)
        assert result.is_valid is False
        assert result.denial_reason == DenialReason.INVALID_FIELD
    
    def test_context_mismatch_denied(self):
        """Context mismatch is denied."""
        request = make_valid_request()
        result = validate_capability_request(request, expected_context_hash="b" * 64)
        assert result.is_valid is False
        assert result.denial_reason == DenialReason.CONTEXT_MISMATCH
    
    def test_replay_detected_denied(self):
        """Replay is denied."""
        request = make_valid_request()
        # First request passes
        result1 = validate_capability_request(request)
        assert result1.is_valid is True
        
        # Same request ID = replay
        request2 = make_valid_request()  # Same ID
        result2 = validate_capability_request(request2)
        assert result2.is_valid is False
        assert result2.denial_reason == DenialReason.REPLAY_DETECTED
    
    def test_rate_limit_enforced(self):
        """Rate limit is enforced."""
        reset_replay_detection()
        reset_rate_limits()
        
        # Make 100 requests (limit) with valid unique IDs
        for i in range(100):
            # Build a valid REQ-[16 hex chars] format
            hex_part = format(i, '016X')
            request = make_valid_request(
                request_id=f"REQ-{hex_part}",
                requester_id="rate-test"
            )
            result = validate_capability_request(request)
            assert result.is_valid is True, f"Request {i} should be valid"
        
        # 101st request should be rate limited
        request = make_valid_request(
            request_id="REQ-00000000000000FF",
            requester_id="rate-test"
        )
        result = validate_capability_request(request)
        assert result.is_valid is False
        assert result.denial_reason == DenialReason.RATE_LIMITED
