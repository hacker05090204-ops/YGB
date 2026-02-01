# Phase-41 Tests: Duplicate Prevention Engine
"""
Tests for Phase-41 duplicate prevention.
100% coverage required.
Negative paths dominate.
"""

import pytest

from impl_v1.phase41.duplicate_types import (
    SignatureTier,
    DuplicateDecision,
    BlockReason,
    SignatureSource,
    HistoryScope,
    DuplicateConfidence,
    Signature,
    DuplicateCheck,
    DuplicateResult,
    HistoryEntry,
    PublicReport,
)

from impl_v1.phase41.duplicate_engine import (
    generate_signature_hash,
    generate_pattern_hash,
    create_signature,
    match_exact,
    match_pattern,
    calculate_similarity,
    determine_confidence,
    check_local_history,
    check_team_history,
    check_public_reports,
    detect_duplicate,
    create_duplicate_audit_entry,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_signature(
    signature_id: str = "SIG-0001",
    tier: SignatureTier = SignatureTier.EXACT,
    hash_value: str = "a" * 64,
    pattern: str = "test-pattern",
) -> Signature:
    """Create a test signature."""
    return Signature(
        signature_id=signature_id,
        tier=tier,
        hash_value=hash_value,
        pattern=pattern,
        created_at="2026-01-27T00:00:00Z",
        source=SignatureSource.LOCAL_HISTORY,
    )


def make_check(
    check_id: str = "CHK-0001",
    finding_hash: str = "a" * 64,
    finding_pattern: str = "test-pattern",
    hunter_id: str = "hunter-001",
    target_id: str = "target-001",
    scope: HistoryScope = HistoryScope.SELF_ONLY,
) -> DuplicateCheck:
    """Create a test duplicate check."""
    return DuplicateCheck(
        check_id=check_id,
        finding_hash=finding_hash,
        finding_pattern=finding_pattern,
        target_id=target_id,
        hunter_id=hunter_id,
        scope=scope,
        timestamp="2026-01-27T00:00:00Z",
    )


def make_history_entry(
    entry_id: str = "ENT-0001",
    signature: Signature = None,
    hunter_id: str = "hunter-001",
    target_id: str = "target-001",
) -> HistoryEntry:
    """Create a test history entry."""
    if signature is None:
        signature = make_signature()
    return HistoryEntry(
        entry_id=entry_id,
        signature=signature,
        target_id=target_id,
        hunter_id=hunter_id,
        submitted_at="2026-01-27T00:00:00Z",
        status="SUBMITTED",
    )


def make_public_report(
    report_id: str = "PUB-0001",
    cve_id: str = "CVE-2026-0001",
    signature_pattern: str = "test-pattern",
) -> PublicReport:
    """Create a test public report."""
    return PublicReport(
        report_id=report_id,
        cve_id=cve_id,
        disclosure_date="2026-01-01T00:00:00Z",
        signature_pattern=signature_pattern,
        source_url="https://example.com/advisory",
    )


# =============================================================================
# ENUM CLOSURE TESTS
# =============================================================================

class TestEnumClosure:
    """Verify all enums are CLOSED."""
    
    def test_signature_tier_has_4_members(self):
        assert len(SignatureTier) == 4
    
    def test_duplicate_decision_has_5_members(self):
        assert len(DuplicateDecision) == 5
    
    def test_block_reason_has_8_members(self):
        assert len(BlockReason) == 8
    
    def test_signature_source_has_5_members(self):
        assert len(SignatureSource) == 5
    
    def test_history_scope_has_4_members(self):
        assert len(HistoryScope) == 4
    
    def test_duplicate_confidence_has_5_members(self):
        assert len(DuplicateConfidence) == 5


# =============================================================================
# DATACLASS FROZEN TESTS
# =============================================================================

class TestDataclassFrozen:
    """Verify all dataclasses are frozen."""
    
    def test_signature_is_frozen(self):
        sig = make_signature()
        with pytest.raises(AttributeError):
            sig.hash_value = "changed"
    
    def test_duplicate_check_is_frozen(self):
        check = make_check()
        with pytest.raises(AttributeError):
            check.finding_hash = "changed"


# =============================================================================
# SIGNATURE GENERATION TESTS
# =============================================================================

class TestSignatureGeneration:
    """Test signature generation."""
    
    def test_hash_empty_returns_empty(self):
        assert generate_signature_hash("") == ""
    
    def test_hash_deterministic(self):
        h1 = generate_signature_hash("test content")
        h2 = generate_signature_hash("test content")
        assert h1 == h2
    
    def test_hash_different_content(self):
        h1 = generate_signature_hash("content A")
        h2 = generate_signature_hash("content B")
        assert h1 != h2
    
    def test_pattern_hash_empty(self):
        assert generate_pattern_hash("") == ""
    
    def test_pattern_hash_normalizes(self):
        h1 = generate_pattern_hash("TEST Pattern")
        h2 = generate_pattern_hash("test pattern")
        assert h1 == h2
    
    def test_create_signature(self):
        sig = create_signature("content", "pattern", SignatureSource.LOCAL_HISTORY)
        assert sig.signature_id.startswith("SIG-")
        assert sig.tier == SignatureTier.EXACT


# =============================================================================
# MATCHING TESTS
# =============================================================================

class TestMatching:
    """Test signature matching."""
    
    def test_exact_match_true(self):
        assert match_exact("abc123", "abc123") is True
    
    def test_exact_match_false(self):
        assert match_exact("abc123", "xyz789") is False
    
    def test_exact_match_empty(self):
        assert match_exact("", "abc") is False
        assert match_exact("abc", "") is False
    
    def test_pattern_match_true(self):
        assert match_pattern("pattern", "pattern") is True
    
    def test_pattern_match_false(self):
        assert match_pattern("pattern1", "pattern2") is False
    
    def test_calculate_similarity_identical(self):
        assert calculate_similarity("abcd", "abcd") == 1.0
    
    def test_calculate_similarity_different(self):
        sim = calculate_similarity("abcd", "wxyz")
        assert sim == 0.0
    
    def test_calculate_similarity_partial(self):
        sim = calculate_similarity("abcd", "abxy")
        assert 0.0 < sim < 1.0
    
    def test_calculate_similarity_empty(self):
        assert calculate_similarity("", "abc") == 0.0


# =============================================================================
# CONFIDENCE TESTS
# =============================================================================

class TestConfidence:
    """Test confidence determination."""
    
    def test_certain_confidence(self):
        assert determine_confidence(1.0) == DuplicateConfidence.CERTAIN
    
    def test_high_confidence(self):
        assert determine_confidence(0.95) == DuplicateConfidence.HIGH
    
    def test_medium_confidence(self):
        assert determine_confidence(0.75) == DuplicateConfidence.MEDIUM
    
    def test_low_confidence(self):
        assert determine_confidence(0.55) == DuplicateConfidence.LOW
    
    def test_uncertain_confidence(self):
        assert determine_confidence(0.3) == DuplicateConfidence.UNCERTAIN


# =============================================================================
# HISTORY CHECK TESTS
# =============================================================================

class TestHistoryChecks:
    """Test history checking."""
    
    def test_local_history_match(self):
        check = make_check()
        entry = make_history_entry()
        
        result = check_local_history(check, [entry])
        assert result is not None
    
    def test_local_history_no_match(self):
        check = make_check(finding_hash="x" * 64, finding_pattern="different-pattern")
        entry = make_history_entry()
        
        result = check_local_history(check, [entry])
        assert result is None
    
    def test_local_history_different_hunter(self):
        check = make_check(hunter_id="hunter-002")
        entry = make_history_entry(hunter_id="hunter-001")
        
        result = check_local_history(check, [entry])
        assert result is None
    
    def test_team_history_match(self):
        check = make_check(hunter_id="hunter-002")
        entry = make_history_entry(hunter_id="hunter-001")
        
        result = check_team_history(check, [entry], ["hunter-001", "hunter-002"])
        assert result is not None
    
    def test_team_history_not_team_member(self):
        check = make_check(hunter_id="hunter-002")
        entry = make_history_entry(hunter_id="hunter-003")
        
        result = check_team_history(check, [entry], ["hunter-001", "hunter-002"])
        assert result is None
    
    def test_public_report_match(self):
        check = make_check()
        report = make_public_report()
        
        result = check_public_reports(check, [report])
        assert result is not None
    
    def test_public_report_no_match(self):
        check = make_check(finding_pattern="other-pattern")
        report = make_public_report()
        
        result = check_public_reports(check, [report])
        assert result is None


# =============================================================================
# DUPLICATE DETECTION TESTS
# =============================================================================

class TestDuplicateDetection:
    """Test duplicate detection engine."""
    
    def test_no_duplicates_allows(self):
        check = make_check(finding_hash="x" * 64, finding_pattern="unique")
        result = detect_duplicate(check)
        
        assert result.decision == DuplicateDecision.ALLOW
    
    def test_self_duplicate_blocks(self):
        check = make_check()
        entry = make_history_entry()
        
        result = detect_duplicate(check, local_history=[entry])
        
        assert result.decision == DuplicateDecision.BLOCK
        assert result.block_reason == BlockReason.SELF_DUPLICATE
    
    def test_team_duplicate_blocks(self):
        check = make_check(hunter_id="hunter-002", scope=HistoryScope.TEAM)
        entry = make_history_entry(hunter_id="hunter-001")
        
        result = detect_duplicate(
            check,
            team_history=[entry],
            team_ids=["hunter-001", "hunter-002"],
        )
        
        assert result.decision == DuplicateDecision.BLOCK
        assert result.block_reason == BlockReason.TEAM_DUPLICATE
    
    def test_public_duplicate_blocks(self):
        check = make_check()
        report = make_public_report()
        
        result = detect_duplicate(check, public_reports=[report])
        
        assert result.decision == DuplicateDecision.BLOCK
        assert result.block_reason == BlockReason.PUBLIC_REPORT


# =============================================================================
# AUDIT TESTS
# =============================================================================

class TestAudit:
    """Test audit entry creation."""
    
    def test_create_audit_entry(self):
        result = DuplicateResult(
            check_id="CHK-001",
            decision=DuplicateDecision.BLOCK,
            confidence=DuplicateConfidence.CERTAIN,
            block_reason=BlockReason.SELF_DUPLICATE,
            matching_signature_id="SIG-001",
            explanation="Test",
        )
        
        audit = create_duplicate_audit_entry(result)
        assert audit.audit_id.startswith("DAUD-")
        assert audit.decision == DuplicateDecision.BLOCK


# =============================================================================
# NEGATIVE PATH TESTS
# =============================================================================

class TestNegativePaths:
    """Test error cases and denial paths."""
    
    def test_empty_inputs_allows(self):
        check = make_check(finding_hash="unique" * 8, finding_pattern="unique")
        result = detect_duplicate(check, local_history=[], team_history=[], public_reports=[])
        assert result.decision == DuplicateDecision.ALLOW
    
    def test_self_only_scope_ignores_team(self):
        check = make_check(hunter_id="hunter-002", scope=HistoryScope.SELF_ONLY)
        team_entry = make_history_entry(hunter_id="hunter-001")
        
        result = detect_duplicate(
            check,
            team_history=[team_entry],
            team_ids=["hunter-001", "hunter-002"],
        )
        
        # SELF_ONLY scope should NOT check team history
        assert result.decision == DuplicateDecision.ALLOW
