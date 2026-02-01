# Phase-47 Tests
import pytest
from impl_v1.phase47.truth_store import *


class TestEnumClosure:
    def test_entry_type_5(self): assert len(EntryType) == 5
    def test_truth_status_4(self): assert len(TruthStatus) == 4


class TestTruthStore:
    def test_create_genesis_entry(self):
        entry = create_truth_entry(EntryType.FACT, {"key": "value"}, "A-001", [])
        assert entry.previous_hash == "GENESIS"
        assert entry.entry_type == EntryType.FACT
    
    def test_chain_entries(self):
        store = []
        e1 = create_truth_entry(EntryType.FACT, {"k": 1}, "A-001", store)
        store.append(e1)
        e2 = create_truth_entry(EntryType.CLAIM, {"k": 2}, "A-002", store)
        store.append(e2)
        
        assert e2.previous_hash == e1.signature
    
    def test_verify_empty(self):
        assert verify_truth_chain([]) is True
    
    def test_verify_valid_chain(self):
        store = []
        e1 = create_truth_entry(EntryType.FACT, {"k": 1}, "A-001", store)
        store.append(e1)
        e2 = create_truth_entry(EntryType.CLAIM, {"k": 2}, "A-002", store)
        store.append(e2)
        
        assert verify_truth_chain(store) is True
    
    def test_verify_tampered_fails(self):
        store = []
        e1 = create_truth_entry(EntryType.FACT, {"k": 1}, "A-001", store)
        store.append(e1)
        
        # Tamper
        tampered = TruthEntry(
            entry_id=e1.entry_id,
            entry_type=e1.entry_type,
            content='{"k": 999}',  # Changed!
            author_id=e1.author_id,
            timestamp=e1.timestamp,
            signature=e1.signature,
            previous_hash=e1.previous_hash,
            status=e1.status,
        )
        
        assert verify_truth_chain([tampered]) is False
    
    def test_query_found(self):
        store = []
        e1 = create_truth_entry(EntryType.FACT, {"k": 1}, "A-001", store)
        store.append(e1)
        
        result = query_truth(store, e1.entry_id)
        assert result == e1
    
    def test_query_not_found(self):
        result = query_truth([], "TRU-NOTEXIST")
        assert result is None
    
    def test_count_by_author(self):
        store = []
        e1 = create_truth_entry(EntryType.FACT, {"k": 1}, "A-001", store)
        store.append(e1)
        e2 = create_truth_entry(EntryType.CLAIM, {"k": 2}, "A-001", store)
        store.append(e2)
        e3 = create_truth_entry(EntryType.FACT, {"k": 3}, "A-002", store)
        store.append(e3)
        
        assert count_by_author(store, "A-001") == 2
        assert count_by_author(store, "A-002") == 1
