"""
Phase-31 Evidence Chain Tests.

Tests evidence chain integrity and hash correctness.
"""
import pytest

from HUMANOID_HUNTER.observation import (
    ObservationPoint,
    EvidenceType,
    EvidenceRecord,
    EvidenceChain,
    ObservationContext,
    capture_evidence,
    validate_chain,
    attach_observer,
    create_empty_chain
)
from HUMANOID_HUNTER.observation.observation_engine import _compute_evidence_hash


class TestEmptyChain:
    """Test empty evidence chain behavior."""
    
    def test_empty_chain_is_valid(self) -> None:
        """Empty chain is valid."""
        chain = create_empty_chain("CHAIN-test")
        assert validate_chain(chain) is True
    
    def test_empty_chain_has_zero_length(self) -> None:
        """Empty chain has length 0."""
        chain = create_empty_chain()
        assert chain.length == 0
    
    def test_empty_chain_has_empty_head_hash(self) -> None:
        """Empty chain has empty head hash."""
        chain = create_empty_chain()
        assert chain.head_hash == ""
    
    def test_empty_chain_has_empty_records(self) -> None:
        """Empty chain has empty records tuple."""
        chain = create_empty_chain()
        assert chain.records == ()


class TestSingleRecordChain:
    """Test chain with single record."""
    
    @pytest.fixture
    def valid_context(self) -> ObservationContext:
        """Create a valid observation context."""
        return attach_observer(
            loop_id="LOOP-test123",
            executor_id="EXEC-test456",
            envelope_hash="abc123hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
    
    def test_single_record_chain_is_valid(
        self, valid_context: ObservationContext
    ) -> None:
        """Chain with single record is valid."""
        empty = create_empty_chain()
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"test_data",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=empty
        )
        assert validate_chain(chain) is True
    
    def test_single_record_has_empty_prior_hash(
        self, valid_context: ObservationContext
    ) -> None:
        """First record has empty prior hash."""
        empty = create_empty_chain()
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"test_data",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=empty
        )
        assert chain.records[0].prior_hash == ""
    
    def test_single_record_has_non_empty_self_hash(
        self, valid_context: ObservationContext
    ) -> None:
        """Record has non-empty self hash."""
        empty = create_empty_chain()
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"test_data",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=empty
        )
        assert chain.records[0].self_hash != ""
        assert len(chain.records[0].self_hash) == 64  # SHA-256 hex


class TestMultiRecordChain:
    """Test chain with multiple records."""
    
    @pytest.fixture
    def valid_context(self) -> ObservationContext:
        """Create a valid observation context."""
        return attach_observer(
            loop_id="LOOP-test123",
            executor_id="EXEC-test456",
            envelope_hash="abc123hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
    
    def test_multi_record_chain_is_valid(
        self, valid_context: ObservationContext
    ) -> None:
        """Chain with multiple records is valid."""
        chain = create_empty_chain()
        
        # Add first record
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"first",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=chain
        )
        
        # Add second record
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.POST_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"second",
            timestamp="2026-01-25T19:02:00-05:00",
            prior_chain=chain
        )
        
        assert chain.length == 2
        assert validate_chain(chain) is True
    
    def test_chain_hash_linking(
        self, valid_context: ObservationContext
    ) -> None:
        """Records are properly linked via hashes."""
        chain = create_empty_chain()
        
        # Add first record
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"first",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=chain
        )
        first_hash = chain.records[0].self_hash
        
        # Add second record
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.POST_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"second",
            timestamp="2026-01-25T19:02:00-05:00",
            prior_chain=chain
        )
        
        # Second record's prior_hash should be first record's self_hash
        assert chain.records[1].prior_hash == first_hash
    
    def test_head_hash_matches_last_record(
        self, valid_context: ObservationContext
    ) -> None:
        """Chain head_hash matches last record's self_hash."""
        chain = create_empty_chain()
        
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"data",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=chain
        )
        
        assert chain.head_hash == chain.records[-1].self_hash


class TestBrokenChainDetection:
    """Test detection of broken evidence chains."""
    
    def test_broken_chain_invalid_prior_hash(self) -> None:
        """Chain with invalid prior_hash is detected."""
        # Create a record with wrong prior_hash
        record = EvidenceRecord(
            record_id="REC-test",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-25T19:01:00-05:00",
            raw_data=b"test",
            prior_hash="WRONG_HASH",  # Should be empty for first record
            self_hash="anything"
        )
        
        chain = EvidenceChain(
            chain_id="CHAIN-test",
            records=(record,),
            head_hash=record.self_hash,
            length=1
        )
        
        assert validate_chain(chain) is False
    
    def test_broken_chain_invalid_self_hash(self) -> None:
        """Chain with tampered self_hash is detected."""
        # Compute correct hash
        correct_hash = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"test",
            ""
        )
        
        # Create record with wrong self_hash
        record = EvidenceRecord(
            record_id="REC-test",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-25T19:01:00-05:00",
            raw_data=b"test",
            prior_hash="",
            self_hash="TAMPERED_HASH"  # Wrong!
        )
        
        chain = EvidenceChain(
            chain_id="CHAIN-test",
            records=(record,),
            head_hash=record.self_hash,
            length=1
        )
        
        assert validate_chain(chain) is False
    
    def test_broken_chain_wrong_length(self) -> None:
        """Chain with wrong length is detected."""
        record = EvidenceRecord(
            record_id="REC-test",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-25T19:01:00-05:00",
            raw_data=b"test",
            prior_hash="",
            self_hash=_compute_evidence_hash(
                "REC-test",
                ObservationPoint.PRE_DISPATCH,
                EvidenceType.STATE_TRANSITION,
                "2026-01-25T19:01:00-05:00",
                b"test",
                ""
            )
        )
        
        chain = EvidenceChain(
            chain_id="CHAIN-test",
            records=(record,),
            head_hash=record.self_hash,
            length=5  # Wrong! Should be 1
        )
        
        assert validate_chain(chain) is False
    
    def test_broken_chain_wrong_head_hash(self) -> None:
        """Chain with wrong head_hash is detected."""
        self_hash = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"test",
            ""
        )
        
        record = EvidenceRecord(
            record_id="REC-test",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-25T19:01:00-05:00",
            raw_data=b"test",
            prior_hash="",
            self_hash=self_hash
        )
        
        chain = EvidenceChain(
            chain_id="CHAIN-test",
            records=(record,),
            head_hash="WRONG_HEAD_HASH",  # Should match self_hash
            length=1
        )
        
        assert validate_chain(chain) is False


class TestHashComputation:
    """Test hash computation correctness."""
    
    def test_hash_is_deterministic(self) -> None:
        """Same inputs produce same hash."""
        hash1 = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"test_data",
            ""
        )
        hash2 = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"test_data",
            ""
        )
        assert hash1 == hash2
    
    def test_hash_changes_with_different_data(self) -> None:
        """Different inputs produce different hashes."""
        hash1 = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"data1",
            ""
        )
        hash2 = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"data2",
            ""
        )
        assert hash1 != hash2
    
    def test_hash_is_64_hex_characters(self) -> None:
        """Hash is SHA-256 (64 hex characters)."""
        hash_val = _compute_evidence_hash(
            "REC-test",
            ObservationPoint.PRE_DISPATCH,
            EvidenceType.STATE_TRANSITION,
            "2026-01-25T19:01:00-05:00",
            b"test",
            ""
        )
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)
