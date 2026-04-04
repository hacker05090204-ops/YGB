# Phase-46 Tests
import pytest
from impl_v1.phase46.mutex_contracts import *


class TestEnumClosure:
    def test_lock_state_5(self): assert len(LockState) == 5
    def test_lock_scope_4(self): assert len(LockScope) == 4
    def test_lock_decision_4(self): assert len(LockDecision) == 4


class TestLocking:
    def setup_method(self):
        clear_all_locks()
    
    def test_acquire_free_grants(self):
        req = LockRequest("REQ-001", "H-001", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        result = acquire_lock(req)
        assert result.decision == LockDecision.GRANT
        assert result.lock is not None
    
    def test_acquire_held_denies(self):
        req1 = LockRequest("REQ-001", "H-001", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        req2 = LockRequest("REQ-002", "H-002", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        
        acquire_lock(req1)
        result = acquire_lock(req2)
        
        assert result.decision == LockDecision.DENY
    
    def test_release_allows_reacquire(self):
        req1 = LockRequest("REQ-001", "H-001", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        acquire_lock(req1)
        
        released = release_lock("R-001", LockScope.VECTOR, "H-001")
        assert released is True
        
        req2 = LockRequest("REQ-002", "H-002", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        result = acquire_lock(req2)
        assert result.decision == LockDecision.GRANT
    
    def test_release_wrong_holder_fails(self):
        req1 = LockRequest("REQ-001", "H-001", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        acquire_lock(req1)
        
        released = release_lock("R-001", LockScope.VECTOR, "H-002")
        assert released is False
    
    def test_check_availability(self):
        assert check_lock_available("R-001", LockScope.VECTOR) is True
        
        req = LockRequest("REQ-001", "H-001", "R-001", LockScope.VECTOR, "2026-01-27", 300)
        acquire_lock(req)
        
        assert check_lock_available("R-001", LockScope.VECTOR) is False
