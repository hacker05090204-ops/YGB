# Phase-45 Tests
import pytest
from impl_v1.phase45.hunter_ledger import *


class TestEnumClosure:
    def test_hunter_role_5(self): assert len(HunterRole) == 5
    def test_action_type_8(self): assert len(ActionType) == 8
    def test_ledger_entry_type_4(self): assert len(LedgerEntryType) == 4


class TestIdentity:
    def test_create_identity(self):
        identity = create_hunter_identity("H-001", HunterRole.RESEARCHER)
        assert identity.hunter_id == "H-001"
        assert identity.role == HunterRole.RESEARCHER
        assert len(identity.identity_hash) == 64
    
    def test_identity_hash_deterministic(self):
        h1 = create_identity_hash("H-001", HunterRole.RESEARCHER, "2026-01-27")
        h2 = create_identity_hash("H-001", HunterRole.RESEARCHER, "2026-01-27")
        assert h1 == h2


class TestLedger:
    def test_append_genesis(self):
        entry = append_ledger_entry([], "H-001", ActionType.SCAN, "T-001")
        assert entry.previous_hash == "GENESIS"
        assert entry.entry_id.startswith("LED-")
    
    def test_append_chained(self):
        e1 = append_ledger_entry([], "H-001", ActionType.SCAN, "T-001")
        e2 = append_ledger_entry([e1], "H-001", ActionType.DISCOVER, "T-001")
        assert e2.previous_hash == e1.entry_hash
    
    def test_verify_empty(self):
        assert verify_ledger_integrity([]) is True
    
    def test_verify_valid_chain(self):
        e1 = append_ledger_entry([], "H-001", ActionType.SCAN, "T-001")
        e2 = append_ledger_entry([e1], "H-001", ActionType.DISCOVER, "T-001")
        assert verify_ledger_integrity([e1, e2]) is True
    
    def test_verify_tampered_fails(self):
        e1 = append_ledger_entry([], "H-001", ActionType.SCAN, "T-001")
        e2 = append_ledger_entry([e1], "H-001", ActionType.DISCOVER, "T-001")
        
        # Tamper with entry
        tampered = LedgerEntry(
            entry_id=e2.entry_id,
            entry_type=e2.entry_type,
            hunter_id="H-FAKE",  # Changed!
            action=e2.action,
            target_id=e2.target_id,
            timestamp=e2.timestamp,
            previous_hash=e2.previous_hash,
            entry_hash=e2.entry_hash,  # Hash won't match
        )
        
        assert verify_ledger_integrity([e1, tampered]) is False
