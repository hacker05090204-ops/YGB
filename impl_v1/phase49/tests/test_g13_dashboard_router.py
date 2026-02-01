# test_g13_dashboard_router.py
"""Tests for G13: Dashboard Router"""

import pytest
from impl_v1.phase49.governors.g13_dashboard_router import (
    ApprovalStatus,
    ProposedMode,
    RiskLevel,
    ApprovalRequest,
    ApprovalDecision,
    clear_requests,
    get_pending_requests,
    create_approval_request,
    submit_decision,
    is_execution_approved,
    get_decision_audit_log,
)


class TestEnumClosure:
    def test_approval_status_5_members(self):
        assert len(ApprovalStatus) == 5
    
    def test_proposed_mode_3_members(self):
        assert len(ProposedMode) == 3
    
    def test_risk_level_4_members(self):
        assert len(RiskLevel) == 4


class TestCreateApprovalRequest:
    def setup_method(self):
        clear_requests()
    
    def test_request_has_id(self):
        request = create_approval_request("example.com", "*")
        assert request.request_id.startswith("APR-")
    
    def test_request_starts_pending(self):
        request = create_approval_request("example.com", "*")
        assert request.status == ApprovalStatus.PENDING
    
    def test_request_has_target(self):
        request = create_approval_request("test.io", "api/*")
        assert request.target == "test.io"
        assert request.scope == "api/*"


class TestSubmitDecision:
    def setup_method(self):
        clear_requests()
    
    def test_approve_request(self):
        request = create_approval_request("example.com", "*")
        decision = submit_decision(request.request_id, True, "human-1", "Looks safe")
        assert decision is not None
        assert decision.approved
    
    def test_reject_request(self):
        request = create_approval_request("example.com", "*")
        decision = submit_decision(request.request_id, False, "human-1", "Too risky")
        assert decision is not None
        assert not decision.approved
    
    def test_decision_updates_status(self):
        request = create_approval_request("example.com", "*")
        submit_decision(request.request_id, True, "human-1", "")
        approved, reason = is_execution_approved(request.request_id)
        assert approved
    
    def test_unknown_request_returns_none(self):
        decision = submit_decision("UNKNOWN-ID", True, "human-1", "")
        assert decision is None


class TestIsExecutionApproved:
    def setup_method(self):
        clear_requests()
    
    def test_pending_not_approved(self):
        request = create_approval_request("example.com", "*")
        approved, reason = is_execution_approved(request.request_id)
        assert not approved
        assert "Awaiting" in reason
    
    def test_approved_after_decision(self):
        request = create_approval_request("example.com", "*")
        submit_decision(request.request_id, True, "human-1", "")
        approved, reason = is_execution_approved(request.request_id)
        assert approved
    
    def test_rejected_not_approved(self):
        request = create_approval_request("example.com", "*")
        submit_decision(request.request_id, False, "human-1", "")
        approved, reason = is_execution_approved(request.request_id)
        assert not approved
        assert "REJECTED" in reason


class TestAuditLog:
    def setup_method(self):
        clear_requests()
    
    def test_decisions_logged(self):
        request = create_approval_request("example.com", "*")
        submit_decision(request.request_id, True, "human-1", "")
        log = get_decision_audit_log()
        assert len(log) == 1
    
    def test_multiple_decisions_logged(self):
        r1 = create_approval_request("a.com", "*")
        r2 = create_approval_request("b.com", "*")
        submit_decision(r1.request_id, True, "h1", "")
        submit_decision(r2.request_id, False, "h2", "")
        log = get_decision_audit_log()
        assert len(log) == 2


class TestGetPendingRequests:
    def setup_method(self):
        clear_requests()
    
    def test_empty_initially(self):
        assert len(get_pending_requests()) == 0
    
    def test_pending_listed(self):
        create_approval_request("a.com", "*")
        create_approval_request("b.com", "*")
        assert len(get_pending_requests()) == 2
    
    def test_approved_not_pending(self):
        request = create_approval_request("a.com", "*")
        submit_decision(request.request_id, True, "h1", "")
        assert len(get_pending_requests()) == 0


class TestDataclassFrozen:
    def setup_method(self):
        clear_requests()
    
    def test_request_frozen(self):
        request = create_approval_request("a.com", "*")
        with pytest.raises(AttributeError):
            request.status = ApprovalStatus.APPROVED
