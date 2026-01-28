# Test G27: Evidence Integrity Chain
"""
Tests for evidence integrity chain governor.

100% coverage required.
"""

import pytest
from impl_v1.phase49.governors.g27_integrity_chain import (
    ChainStatus,
    IntegrityViolation,
    ChainLink,
    ChainVerificationResult,
    IntegrityViolationRecord,
    ReportIntegrityStatus,
    can_integrity_skip_verification,
    can_integrity_modify_chain,
    can_report_bypass_integrity,
    compute_content_hash,
    compute_link_hash,
    compute_chain_root_hash,
    IntegrityChainBuilder,
    IntegrityChainVerifier,
    verify_for_report,
    invalidate_report_on_failure,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_integrity_skip_verification_always_false(self):
        """Guard: Cannot skip verification."""
        assert can_integrity_skip_verification() is False
    
    def test_can_integrity_modify_chain_always_false(self):
        """Guard: Cannot modify chain."""
        assert can_integrity_modify_chain() is False
    
    def test_can_report_bypass_integrity_always_false(self):
        """Guard: Cannot bypass integrity for report."""
        assert can_report_bypass_integrity() is False


class TestHashFunctions:
    """Test hash utility functions."""
    
    def test_compute_content_hash(self):
        """Compute content hash."""
        data = b"test data"
        hash1 = compute_content_hash(data)
        hash2 = compute_content_hash(data)
        assert hash1 == hash2
        assert len(hash1) == 64
    
    def test_compute_content_hash_different_data(self):
        """Different data = different hash."""
        hash1 = compute_content_hash(b"data1")
        hash2 = compute_content_hash(b"data2")
        assert hash1 != hash2
    
    def test_compute_link_hash_genesis(self):
        """Compute link hash for genesis."""
        content_hash = compute_content_hash(b"test")
        link_hash = compute_link_hash(content_hash, None)
        assert len(link_hash) == 64
    
    def test_compute_link_hash_chained(self):
        """Compute link hash with prev."""
        content_hash = compute_content_hash(b"test")
        prev_hash = "abc123"
        link_hash = compute_link_hash(content_hash, prev_hash)
        assert len(link_hash) == 64
    
    def test_compute_chain_root_hash(self):
        """Compute chain root hash."""
        chain = [
            ChainLink("L1", "E1", "h1", None, "lh1", "t1", "s1", 0),
            ChainLink("L2", "E2", "h2", "lh1", "lh2", "t2", "s1", 1),
        ]
        root = compute_chain_root_hash(chain)
        assert root is not None
        assert len(root) == 64
    
    def test_compute_chain_root_hash_empty(self):
        """Empty chain has no root hash."""
        root = compute_chain_root_hash([])
        assert root is None


class TestChainBuilder:
    """Test integrity chain builder."""
    
    def test_builder_creation(self):
        """Create chain builder."""
        builder = IntegrityChainBuilder("SES-123")
        assert builder.session_id == "SES-123"
        assert builder.chain_id.startswith("CHN-")
    
    def test_add_evidence(self):
        """Add evidence to chain."""
        builder = IntegrityChainBuilder("SES-123")
        link = builder.add_evidence("EV-001", b"evidence data")
        
        assert link.evidence_id == "EV-001"
        assert link.prev_hash is None  # Genesis
        assert link.sequence == 0
        assert link.session_id == "SES-123"
    
    def test_add_multiple_evidence(self):
        """Add multiple evidence items."""
        builder = IntegrityChainBuilder("SES-123")
        
        link1 = builder.add_evidence("EV-001", b"data1")
        link2 = builder.add_evidence("EV-002", b"data2")
        link3 = builder.add_evidence("EV-003", b"data3")
        
        assert link1.sequence == 0
        assert link2.sequence == 1
        assert link3.sequence == 2
        
        assert link1.prev_hash is None
        assert link2.prev_hash == link1.link_hash
        assert link3.prev_hash == link2.link_hash
    
    def test_get_chain(self):
        """Get immutable chain."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data")
        builder.add_evidence("EV-002", b"data2")
        
        chain = builder.get_chain()
        assert len(chain) == 2
        assert isinstance(chain, tuple)
    
    def test_get_root_hash(self):
        """Get root hash."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data")
        
        root = builder.get_root_hash()
        assert root is not None


class TestChainVerifier:
    """Test chain verifier."""
    
    def test_verify_valid_chain(self):
        """Verify valid chain."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data1")
        builder.add_evidence("EV-002", b"data2")
        chain = builder.get_chain()
        
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain(chain, "SES-123")
        
        assert result.status == ChainStatus.VALID
        assert result.is_valid is True
        assert result.total_links == 2
        assert result.verified_links == 2
        assert len(result.violations) == 0
    
    def test_verify_empty_chain(self):
        """Verify empty chain."""
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain((), "SES-123")
        
        assert result.status == ChainStatus.EMPTY
        assert result.is_valid is True
    
    def test_verify_session_mismatch(self):
        """Detect session mismatch."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data")
        chain = builder.get_chain()
        
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain(chain, "WRONG-SESSION")
        
        assert result.is_valid is False
        assert any(v.violation_type == IntegrityViolation.SESSION_MISMATCH 
                   for v in result.violations)
    
    def test_verify_chain_break(self):
        """Detect chain break."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data1")
        link2 = builder.add_evidence("EV-002", b"data2")
        
        # Tamper with chain - create broken link
        tampered = ChainLink(
            link_id=link2.link_id,
            evidence_id=link2.evidence_id,
            content_hash=link2.content_hash,
            prev_hash="WRONG_PREV_HASH",  # Broken!
            link_hash=link2.link_hash,
            timestamp=link2.timestamp,
            session_id=link2.session_id,
            sequence=link2.sequence,
        )
        
        chain = (builder.get_chain()[0], tampered)
        
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain(chain, "SES-123")
        
        assert result.status == ChainStatus.BROKEN
        assert result.is_valid is False
    
    def test_verify_sequence_mismatch(self):
        """Detect sequence mismatch."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data1")
        link2 = builder.add_evidence("EV-002", b"data2")
        
        # Tamper with sequence
        tampered = ChainLink(
            link_id=link2.link_id,
            evidence_id=link2.evidence_id,
            content_hash=link2.content_hash,
            prev_hash=link2.prev_hash,
            link_hash=link2.link_hash,
            timestamp=link2.timestamp,
            session_id=link2.session_id,
            sequence=99,  # Wrong sequence!
        )
        
        chain = (builder.get_chain()[0], tampered)
        
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain(chain, "SES-123")
        
        assert result.is_valid is False
        assert any(v.violation_type == IntegrityViolation.MISSING_LINK
                   for v in result.violations)
    
    def test_verify_genesis_with_prev_hash(self):
        """Detect genesis link with prev_hash."""
        # Create tampered genesis link
        tampered_genesis = ChainLink(
            link_id="LNK-001",
            evidence_id="EV-001",
            content_hash=compute_content_hash(b"data"),
            prev_hash="SHOULD_NOT_EXIST",  # Genesis should have None!
            link_hash="fake_hash",
            timestamp="2026-01-28T00:00:00Z",
            session_id="SES-123",
            sequence=0,
        )
        
        chain = (tampered_genesis,)
        
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain(chain, "SES-123")
        
        assert result.is_valid is False
        assert any(v.violation_type == IntegrityViolation.CHAIN_BREAK
                   for v in result.violations)
    
    def test_verify_hash_mismatch(self):
        """Detect link hash mismatch."""
        builder = IntegrityChainBuilder("SES-123")
        link1 = builder.add_evidence("EV-001", b"data1")
        
        # Tamper with link_hash
        tampered = ChainLink(
            link_id=link1.link_id,
            evidence_id=link1.evidence_id,
            content_hash=link1.content_hash,
            prev_hash=link1.prev_hash,
            link_hash="TAMPERED_HASH",  # Wrong hash!
            timestamp=link1.timestamp,
            session_id=link1.session_id,
            sequence=link1.sequence,
        )
        
        chain = (tampered,)
        
        verifier = IntegrityChainVerifier()
        result = verifier.verify_chain(chain, "SES-123")
        
        assert result.is_valid is False
        assert any(v.violation_type == IntegrityViolation.HASH_MISMATCH
                   for v in result.violations)


class TestReportIntegrity:
    """Test report integrity functions."""
    
    def test_verify_for_report_valid(self):
        """Verify valid chain for report."""
        builder = IntegrityChainBuilder("SES-123")
        builder.add_evidence("EV-001", b"data")
        chain = builder.get_chain()
        
        status = verify_for_report(chain, "RPT-001", "SES-123")
        
        assert status.report_id == "RPT-001"
        assert status.is_valid is True
        assert status.evidence_count == 1
    
    def test_verify_for_report_empty_chain(self):
        """Verify empty chain for report."""
        status = verify_for_report((), "RPT-001", "SES-123")
        
        assert status.is_valid is True
        assert status.root_hash == "EMPTY"
        assert status.evidence_count == 0
    
    def test_invalidate_report_on_failure_valid(self):
        """Valid report is not invalidated."""
        status = ReportIntegrityStatus(
            report_id="RPT-001",
            chain_id="CHN-123",
            is_valid=True,
            root_hash="abc",
            evidence_count=1,
            verification_timestamp="2026-01-28T00:00:00Z",
        )
        assert invalidate_report_on_failure(status) is False
    
    def test_invalidate_report_on_failure_invalid(self):
        """Invalid report is invalidated."""
        status = ReportIntegrityStatus(
            report_id="RPT-001",
            chain_id="CHN-123",
            is_valid=False,
            root_hash="abc",
            evidence_count=1,
            verification_timestamp="2026-01-28T00:00:00Z",
        )
        assert invalidate_report_on_failure(status) is True


class TestDataclasses:
    """Test dataclass immutability."""
    
    def test_chain_link_frozen(self):
        """ChainLink is immutable."""
        link = ChainLink("L1", "E1", "h1", None, "lh1", "t1", "s1", 0)
        with pytest.raises(Exception):
            link.link_id = "changed"
    
    def test_violation_record_frozen(self):
        """IntegrityViolationRecord is immutable."""
        record = IntegrityViolationRecord(
            violation_type=IntegrityViolation.HASH_MISMATCH,
            link_id="L1",
            expected="abc",
            actual="def",
            message="test",
        )
        with pytest.raises(Exception):
            record.link_id = "changed"

