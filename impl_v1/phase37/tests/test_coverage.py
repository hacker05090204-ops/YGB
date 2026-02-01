# Phase-37 Additional Coverage Tests
"""Additional tests for full coverage."""

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
    validate_request_id,
    validate_timestamp,
    validate_scope,
    ESCALATE_CAPABILITIES,
    ALLOW_CAPABILITIES,
)

from impl_v1.phase37.capability_engine import (
    detect_conflict,
    make_capability_decision,
    EXCLUSIVE_CAPABILITIES,
)


def make_valid_request(
    request_id: str = "REQ-0123456789ABCDEF",
    capability: SandboxCapability = SandboxCapability.MEMORY_READ,
    requester_id: str = "test-requester",
    scope_type: ScopeType = ScopeType.SINGLE_USE,
    context_hash: str = "a" * 64
) -> CapabilityRequest:
    """Create a valid capability request for testing."""
    now = datetime.utcnow()
    expiry = now + timedelta(hours=1)
    return CapabilityRequest(
        request_id=request_id,
        capability=capability,
        intent_description="Test request",
        requested_scope=RequestScope(
            scope_type=scope_type,
            scope_value="test-scope",
            scope_limit=1
        ),
        timestamp=now.isoformat() + "Z",
        expiry=expiry.isoformat() + "Z",
        context_hash=context_hash,
        requester_id=requester_id
    )


class TestAdditionalCoverage:
    """Additional tests for full coverage."""
    
    def test_escalate_capabilities_set(self):
        """ESCALATE_CAPABILITIES contains correct items."""
        assert SandboxCapability.MEMORY_WRITE in ESCALATE_CAPABILITIES
    
    def test_allow_capabilities_set(self):
        """ALLOW_CAPABILITIES contains correct items.""" 
        assert SandboxCapability.MEMORY_READ in ALLOW_CAPABILITIES
        assert SandboxCapability.HEAP_ALLOCATE in ALLOW_CAPABILITIES
        assert SandboxCapability.INPUT_READ in ALLOW_CAPABILITIES
        assert SandboxCapability.OUTPUT_WRITE in ALLOW_CAPABILITIES
    
    def test_scope_types(self):
        """Test all scope types."""
        for scope_type in ScopeType:
            if scope_type == ScopeType.UNBOUNDED:
                scope = RequestScope(scope_type, "test", 0)
            else:
                scope = RequestScope(scope_type, "test", 1)
            assert scope.scope_type == scope_type
    
    def test_exclusive_capabilities(self):
        """Test exclusive capabilities."""
        assert SandboxCapability.NETWORK in EXCLUSIVE_CAPABILITIES


class TestEdgeCases:
    """Edge case testing."""
    
    def test_timestamp_with_plus_timezone(self):
        """Test timestamp with + timezone."""
        assert validate_timestamp("2026-01-27T00:00:00+05:00") is True
    
    def test_scope_unbounded(self):
        """Test UNBOUNDED scope."""
        scope = RequestScope(ScopeType.UNBOUNDED, "test", 0)
        result = validate_scope(scope)
        # UNBOUNDED with 0 limit is valid
        assert result is True
