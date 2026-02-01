# Phase-37 Tests: Capability Engine
"""
Tests for Phase-37 capability governance decision engine.
100% coverage required.
Negative paths dominate.
"""

import pytest
from datetime import datetime, timedelta

from impl_v1.phase37.capability_types import (
    RequestScope,
    CapabilityRequest,
    CapabilityGrant,
    RequestDecision,
    SandboxCapability,
    ScopeType,
    DenialReason,
    ConflictType,
    AuditEventType,
)

from impl_v1.phase37.capability_engine import (
    detect_conflict,
    make_capability_decision,
    create_grant,
    create_audit_entry,
)

from impl_v1.phase37.capability_validator import (
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
    requester_id: str = "test-requester",
    scope_type: ScopeType = ScopeType.SINGLE_USE,
) -> CapabilityRequest:
    """Create a valid capability request for testing."""
    now = datetime.utcnow()
    expiry = now + timedelta(hours=1)
    return CapabilityRequest(
        request_id=request_id,
        capability=capability,
        intent_description="Test request for engine",
        requested_scope=RequestScope(
            scope_type=scope_type,
            scope_value="test-scope",
            scope_limit=1
        ),
        timestamp=now.isoformat() + "Z",
        expiry=expiry.isoformat() + "Z",
        context_hash="a" * 64,
        requester_id=requester_id
    )


def make_grant(
    request: CapabilityRequest,
    consumed: bool = False
) -> CapabilityGrant:
    """Create a grant from a request."""
    return CapabilityGrant(
        grant_id="GRANT-0123456789ABCDEF",
        request_id=request.request_id,
        capability=request.capability,
        scope=request.requested_scope,
        granted_at=request.timestamp,
        expires_at=request.expiry,
        context_hash=request.context_hash,
        consumed=consumed,
    )


# =============================================================================
# CONFLICT DETECTION TESTS
# =============================================================================

class TestConflictDetection:
    """Test conflict detection between requests and grants."""
    
    def test_no_conflict_empty_state(self):
        """No conflict with empty pending/grants."""
        request = make_valid_request()
        result = detect_conflict(request, [], [])
        assert result.has_conflict is False
    
    def test_conflict_duplicate_capability(self):
        """Conflict when same capability requested twice."""
        request1 = make_valid_request(request_id="REQ-0123456789ABCDEF")
        request2 = make_valid_request(request_id="REQ-FEDCBA9876543210")
        
        result = detect_conflict(request2, [request1], [])
        assert result.has_conflict is True
        assert result.conflict_type == ConflictType.RESOURCE_CONTENTION
    
    def test_conflict_exclusive_capability(self):
        """NETWORK conflicts with any other request."""
        network_request = make_valid_request(
            request_id="REQ-NETWORK123456789",
            capability=SandboxCapability.NETWORK
        )
        other_request = make_valid_request(request_id="REQ-OTHER1234567890")
        
        result = detect_conflict(network_request, [other_request], [])
        assert result.has_conflict is True
        assert result.conflict_type == ConflictType.MUTUAL_EXCLUSION
    
    def test_conflict_active_grant(self):
        """Conflict with active grant for same capability."""
        request = make_valid_request()
        grant = make_grant(request, consumed=False)
        
        # New request for same capability
        new_request = make_valid_request(request_id="REQ-NEW1234567890AB")
        
        result = detect_conflict(new_request, [], [grant])
        assert result.has_conflict is True
    
    def test_no_conflict_consumed_grant(self):
        """No conflict with consumed grant."""
        request = make_valid_request()
        grant = make_grant(request, consumed=True)
        
        new_request = make_valid_request(request_id="REQ-NEW1234567890AB")
        
        result = detect_conflict(new_request, [], [grant])
        assert result.has_conflict is False


# =============================================================================
# DECISION ENGINE TESTS
# =============================================================================

class TestDecisionEngine:
    """Test capability decision making."""
    
    def test_valid_allow_capability_granted(self):
        """Valid ALLOW capability is granted."""
        request = make_valid_request(capability=SandboxCapability.MEMORY_READ)
        response = make_capability_decision(request)
        
        assert response.decision == RequestDecision.GRANTED
        assert response.grant_token != ""
        assert response.requires_human is False
    
    def test_never_capability_denied(self):
        """NEVER capability is immediately denied."""
        request = make_valid_request(capability=SandboxCapability.NETWORK)
        response = make_capability_decision(request)
        
        assert response.decision == RequestDecision.DENIED
        assert response.reason_code == DenialReason.NEVER_CAPABILITY.value
    
    def test_escalate_capability_pending(self):
        """ESCALATE capability goes to PENDING."""
        request = make_valid_request(capability=SandboxCapability.MEMORY_WRITE)
        response = make_capability_decision(request)
        
        assert response.decision == RequestDecision.PENDING
        assert response.requires_human is True
    
    def test_unbounded_scope_pending(self):
        """UNBOUNDED scope requires escalation."""
        request = make_valid_request(
            capability=SandboxCapability.MEMORY_READ,
            scope_type=ScopeType.UNBOUNDED
        )
        response = make_capability_decision(request)
        
        assert response.decision == RequestDecision.PENDING
        assert response.requires_human is True
    
    def test_human_approved_granted(self):
        """Human approval grants the capability."""
        request = make_valid_request(capability=SandboxCapability.MEMORY_WRITE)
        response = make_capability_decision(request, human_approved=True)
        
        assert response.decision == RequestDecision.GRANTED
        assert response.reason_code == "HUMAN_APPROVED"
    
    def test_human_denied(self):
        """Human denial rejects the capability."""
        request = make_valid_request(capability=SandboxCapability.MEMORY_WRITE)
        response = make_capability_decision(request, human_approved=False)
        
        assert response.decision == RequestDecision.DENIED
        assert response.reason_code == DenialReason.HUMAN_DENIED.value
    
    def test_conflict_denied(self):
        """Conflict causes denial."""
        request1 = make_valid_request(request_id="REQ-0123456789ABCDEF")
        request2 = make_valid_request(request_id="REQ-FEDCBA9876543210")
        
        response = make_capability_decision(request2, pending_requests=[request1])
        
        assert response.decision == RequestDecision.DENIED
        assert response.reason_code == DenialReason.CONFLICT_DETECTED.value


# =============================================================================
# GRANT CREATION TESTS
# =============================================================================

class TestGrantCreation:
    """Test capability grant creation."""
    
    def test_grant_created_correctly(self):
        """Grant is created with correct fields."""
        request = make_valid_request()
        grant = create_grant(request)
        
        assert grant.request_id == request.request_id
        assert grant.capability == request.capability
        assert grant.scope == request.requested_scope
        assert grant.context_hash == request.context_hash
        assert grant.consumed is False
    
    def test_grant_id_format(self):
        """Grant ID has correct format."""
        request = make_valid_request()
        grant = create_grant(request)
        
        assert grant.grant_id.startswith("GRANT-")
        assert len(grant.grant_id) == 22  # GRANT- + 16 chars
    
    def test_grant_has_expiry(self):
        """Grant has expiry timestamp."""
        request = make_valid_request()
        grant = create_grant(request)
        
        assert grant.expires_at != ""
        assert grant.granted_at != ""


# =============================================================================
# AUDIT ENTRY TESTS
# =============================================================================

class TestAuditEntry:
    """Test audit entry creation."""
    
    def test_audit_entry_created(self):
        """Audit entry is created with correct fields."""
        request = make_valid_request()
        entry = create_audit_entry(
            request,
            AuditEventType.REQUEST_RECEIVED,
            RequestDecision.PENDING,
            "TEST"
        )
        
        assert entry.request_id == request.request_id
        assert entry.event_type == AuditEventType.REQUEST_RECEIVED
        assert entry.decision == RequestDecision.PENDING
        assert entry.reason_code == "TEST"
        assert entry.audit_id.startswith("AUDIT-")
    
    def test_audit_entry_has_timestamp(self):
        """Audit entry has timestamp."""
        request = make_valid_request()
        entry = create_audit_entry(
            request,
            AuditEventType.GRANT_ISSUED,
            RequestDecision.GRANTED,
            "GRANTED"
        )
        
        assert entry.timestamp != ""
        assert "T" in entry.timestamp  # ISO format


# =============================================================================
# NEGATIVE PATH TESTS
# =============================================================================

class TestNegativePaths:
    """Test denial paths dominate."""
    
    def test_all_never_capabilities_denied(self):
        """All NEVER capabilities are denied."""
        never_caps = [
            SandboxCapability.NETWORK,
            SandboxCapability.FILESYSTEM,
            SandboxCapability.PROCESS,
        ]
        
        for cap in never_caps:
            request = make_valid_request(
                request_id=f"REQ-{cap.value[:12]:0<16}",
                capability=cap
            )
            response = make_capability_decision(request)
            assert response.decision == RequestDecision.DENIED, f"{cap} should be denied"
    
    def test_invalid_request_id_denied(self):
        """Invalid request ID is denied."""
        now = datetime.utcnow()
        expiry = now + timedelta(hours=1)
        request = CapabilityRequest(
            request_id="INVALID",  # Bad format
            capability=SandboxCapability.MEMORY_READ,
            intent_description="Test",
            requested_scope=RequestScope(ScopeType.SINGLE_USE, "test", 1),
            timestamp=now.isoformat() + "Z",
            expiry=expiry.isoformat() + "Z",
            context_hash="a" * 64,
            requester_id="test"
        )
        response = make_capability_decision(request)
        assert response.decision == RequestDecision.DENIED
    
    def test_context_mismatch_denied(self):
        """Context mismatch is denied."""
        request = make_valid_request()
        response = make_capability_decision(
            request,
            expected_context_hash="b" * 64  # Mismatch
        )
        assert response.decision == RequestDecision.DENIED
