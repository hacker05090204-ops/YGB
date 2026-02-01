# Phase-40 Tests: Authority Arbitration
"""
Tests for Phase-40 authority arbitration and conflict resolution.
100% coverage required.
Negative paths dominate.
"""

import pytest

from impl_v1.phase40.authority_types import (
    # Enums
    AuthorityLevel,
    ConflictType,
    ResolutionRule,
    AuthorityDecision,
    OverrideReason,
    ArbitrationState,
    # Dataclasses
    AuthoritySource,
    AuthorityConflict,
    ArbitrationResult,
)

from impl_v1.phase40.authority_engine import (
    compare_authority,
    is_higher_authority,
    is_human_authority,
    is_executor_authority,
    detect_conflict,
    detect_conflicts_in_sources,
    resolve_conflict,
    arbitrate_sources,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_source(
    source_id: str = "SRC-001",
    level: AuthorityLevel = AuthorityLevel.GOVERNOR,
    claim_type: str = "ALLOW",
    scope: str = "test-scope",
    timestamp: str = "2026-01-27T00:00:00Z"
) -> AuthoritySource:
    """Create an authority source for testing."""
    return AuthoritySource(
        source_id=source_id,
        level=level,
        claim_type=claim_type,
        scope=scope,
        timestamp=timestamp,
        context_hash="a" * 64
    )


# =============================================================================
# ENUM CLOSURE TESTS
# =============================================================================

class TestEnumClosure:
    """Verify all enums are CLOSED with exact member counts."""
    
    def test_authority_level_has_5_members(self):
        """AuthorityLevel must have exactly 5 members."""
        assert len(AuthorityLevel) == 5
    
    def test_conflict_type_has_8_members(self):
        """ConflictType must have exactly 8 members."""
        assert len(ConflictType) == 8
    
    def test_resolution_rule_has_7_members(self):
        """ResolutionRule must have exactly 7 members."""
        assert len(ResolutionRule) == 7
    
    def test_authority_decision_has_5_members(self):
        """AuthorityDecision must have exactly 5 members."""
        assert len(AuthorityDecision) == 5
    
    def test_override_reason_has_6_members(self):
        """OverrideReason must have exactly 6 members."""
        assert len(OverrideReason) == 6
    
    def test_arbitration_state_has_6_members(self):
        """ArbitrationState must have exactly 6 members."""
        assert len(ArbitrationState) == 6


# =============================================================================
# AUTHORITY HIERARCHY TESTS
# =============================================================================

class TestAuthorityHierarchy:
    """Test authority level ordering."""
    
    def test_human_is_highest(self):
        """HUMAN is the highest authority level."""
        assert AuthorityLevel.HUMAN > AuthorityLevel.GOVERNANCE
        assert AuthorityLevel.HUMAN > AuthorityLevel.GOVERNOR
        assert AuthorityLevel.HUMAN > AuthorityLevel.INTERFACE
        assert AuthorityLevel.HUMAN > AuthorityLevel.EXECUTOR
    
    def test_executor_is_lowest(self):
        """EXECUTOR is the lowest authority level."""
        assert AuthorityLevel.EXECUTOR < AuthorityLevel.INTERFACE
        assert AuthorityLevel.EXECUTOR < AuthorityLevel.GOVERNOR
        assert AuthorityLevel.EXECUTOR < AuthorityLevel.GOVERNANCE
        assert AuthorityLevel.EXECUTOR < AuthorityLevel.HUMAN
    
    def test_ordering_is_complete(self):
        """Full ordering: HUMAN > GOVERNANCE > GOVERNOR > INTERFACE > EXECUTOR."""
        assert (AuthorityLevel.HUMAN > AuthorityLevel.GOVERNANCE >
                AuthorityLevel.GOVERNOR > AuthorityLevel.INTERFACE >
                AuthorityLevel.EXECUTOR)
    
    def test_compare_authority(self):
        """compare_authority returns correct values."""
        human = make_source(level=AuthorityLevel.HUMAN)
        governor = make_source(level=AuthorityLevel.GOVERNOR)
        executor = make_source(level=AuthorityLevel.EXECUTOR)
        
        assert compare_authority(human, governor) > 0
        assert compare_authority(governor, human) < 0
        assert compare_authority(governor, governor) == 0
        assert compare_authority(executor, human) < 0


# =============================================================================
# AUTHORITY SOURCE TESTS
# =============================================================================

class TestAuthoritySource:
    """Test authority source functions."""
    
    def test_is_human_authority(self):
        """is_human_authority works correctly."""
        human = make_source(level=AuthorityLevel.HUMAN)
        governor = make_source(level=AuthorityLevel.GOVERNOR)
        
        assert is_human_authority(human) is True
        assert is_human_authority(governor) is False
    
    def test_is_executor_authority(self):
        """is_executor_authority works correctly."""
        executor = make_source(level=AuthorityLevel.EXECUTOR)
        governor = make_source(level=AuthorityLevel.GOVERNOR)
        
        assert is_executor_authority(executor) is True
        assert is_executor_authority(governor) is False
    
    def test_is_higher_authority(self):
        """is_higher_authority works correctly."""
        human = make_source(level=AuthorityLevel.HUMAN)
        governor = make_source(level=AuthorityLevel.GOVERNOR)
        
        assert is_higher_authority(human, governor) is True
        assert is_higher_authority(governor, human) is False
        assert is_higher_authority(governor, governor) is False


# =============================================================================
# DATACLASS FROZEN TESTS
# =============================================================================

class TestDataclassFrozen:
    """Verify all dataclasses are frozen (immutable)."""
    
    def test_authority_source_is_frozen(self):
        """AuthoritySource must be frozen."""
        source = make_source()
        with pytest.raises(AttributeError):
            source.level = AuthorityLevel.HUMAN


# =============================================================================
# CONFLICT DETECTION TESTS
# =============================================================================

class TestConflictDetection:
    """Test conflict detection logic."""
    
    def test_no_conflict_same_claim(self):
        """No conflict if both claim ALLOW."""
        source_a = make_source(source_id="A", claim_type="ALLOW")
        source_b = make_source(source_id="B", claim_type="ALLOW")
        
        conflict = detect_conflict(source_a, source_b)
        assert conflict is None
    
    def test_no_conflict_different_scope(self):
        """No conflict if different scopes."""
        source_a = make_source(source_id="A", scope="scope-1", claim_type="ALLOW")
        source_b = make_source(source_id="B", scope="scope-2", claim_type="DENY")
        
        conflict = detect_conflict(source_a, source_b)
        assert conflict is None
    
    def test_conflict_allow_vs_deny(self):
        """Conflict when ALLOW vs DENY for same scope."""
        source_a = make_source(source_id="A", claim_type="ALLOW")
        source_b = make_source(source_id="B", claim_type="DENY")
        
        conflict = detect_conflict(source_a, source_b)
        assert conflict is not None
        assert conflict.conflict_type == ConflictType.GOVERNOR_VS_GOVERNOR
    
    def test_conflict_human_vs_governor(self):
        """Human vs governor conflict detected."""
        human = make_source(source_id="H", level=AuthorityLevel.HUMAN, claim_type="ALLOW")
        governor = make_source(source_id="G", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        
        conflict = detect_conflict(human, governor)
        assert conflict is not None
        assert conflict.conflict_type == ConflictType.HUMAN_VS_GOVERNOR
    
    def test_conflict_authority_usurpation(self):
        """Executor trying to override detected as usurpation."""
        executor = make_source(source_id="E", level=AuthorityLevel.EXECUTOR, claim_type="ALLOW")
        governor = make_source(source_id="G", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        
        conflict = detect_conflict(executor, governor)
        assert conflict is not None
        assert conflict.conflict_type == ConflictType.AUTHORITY_USURPATION


# =============================================================================
# CONFLICT RESOLUTION TESTS
# =============================================================================

class TestConflictResolution:
    """Test conflict resolution logic."""
    
    def test_human_always_wins(self):
        """Human authority always wins."""
        human = make_source(source_id="H", level=AuthorityLevel.HUMAN, claim_type="ALLOW")
        governor = make_source(source_id="G", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        
        conflict = detect_conflict(human, governor)
        result = resolve_conflict(conflict)
        
        assert result.winning_source_id == "H"
        assert result.resolution_rule == ResolutionRule.HIGHER_LEVEL_WINS
    
    def test_higher_level_wins(self):
        """Higher authority level wins."""
        governance = make_source(source_id="N", level=AuthorityLevel.GOVERNANCE, claim_type="ALLOW")
        governor = make_source(source_id="G", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        
        conflict = detect_conflict(governance, governor)
        result = resolve_conflict(conflict)
        
        assert result.winning_source_id == "N"
        assert result.resolution_rule == ResolutionRule.HIGHER_LEVEL_WINS
    
    def test_deny_wins_at_same_level(self):
        """DENY wins at same authority level."""
        allow = make_source(source_id="A", level=AuthorityLevel.GOVERNOR, claim_type="ALLOW")
        deny = make_source(source_id="D", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        
        conflict = detect_conflict(allow, deny)
        result = resolve_conflict(conflict)
        
        assert result.winning_source_id == "D"
        assert result.resolution_rule == ResolutionRule.DENY_WINS
        assert result.decision == AuthorityDecision.DENY
    
    def test_authority_usurpation_denied(self):
        """Executor usurpation attempt is denied."""
        executor = make_source(source_id="E", level=AuthorityLevel.EXECUTOR, claim_type="ALLOW")
        governor = make_source(source_id="G", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        
        conflict = detect_conflict(executor, governor)
        result = resolve_conflict(conflict)
        
        assert result.winning_source_id == "G"
        assert result.decision == AuthorityDecision.DENY


# =============================================================================
# MULTI-SOURCE ARBITRATION TESTS
# =============================================================================

class TestMultiSourceArbitration:
    """Test arbitration among multiple sources."""
    
    def test_empty_sources_denied(self):
        """Empty sources list results in DENY."""
        decision, winner, results = arbitrate_sources([])
        assert decision == AuthorityDecision.DENY
        assert winner is None
    
    def test_single_source_granted(self):
        """Single non-executor source is granted."""
        source = make_source(level=AuthorityLevel.GOVERNOR, claim_type="ALLOW")
        decision, winner, results = arbitrate_sources([source])
        assert decision == AuthorityDecision.GRANT
    
    def test_single_executor_denied(self):
        """Single executor cannot self-authorize."""
        executor = make_source(level=AuthorityLevel.EXECUTOR, claim_type="ALLOW")
        decision, winner, results = arbitrate_sources([executor])
        assert decision == AuthorityDecision.DENY
    
    def test_any_deny_causes_deny(self):
        """Any DENY source causes overall DENY."""
        allow = make_source(source_id="A", claim_type="ALLOW", scope="s")
        deny = make_source(source_id="D", claim_type="DENY", scope="s")
        
        decision, winner, results = arbitrate_sources([allow, deny])
        assert decision == AuthorityDecision.DENY


# =============================================================================
# NEGATIVE PATH TESTS
# =============================================================================

class TestNegativePaths:
    """Test denial paths dominate."""
    
    def test_executor_cannot_override_human(self):
        """Executor cannot override human authority."""
        human = make_source(source_id="H", level=AuthorityLevel.HUMAN, claim_type="DENY")
        executor = make_source(source_id="E", level=AuthorityLevel.EXECUTOR, claim_type="ALLOW")
        
        conflict = detect_conflict(executor, human)
        result = resolve_conflict(conflict)
        
        assert result.winning_source_id == "H"
    
    def test_executor_cannot_override_governor(self):
        """Executor cannot override governor."""
        governor = make_source(source_id="G", level=AuthorityLevel.GOVERNOR, claim_type="DENY")
        executor = make_source(source_id="E", level=AuthorityLevel.EXECUTOR, claim_type="ALLOW")
        
        conflict = detect_conflict(executor, governor)
        result = resolve_conflict(conflict)
        
        assert result.winning_source_id == "G"
    
    def test_deny_always_wins_same_level(self):
        """DENY always wins at same authority level."""
        for level in [AuthorityLevel.GOVERNOR, AuthorityLevel.GOVERNANCE]:
            allow = make_source(source_id="A", level=level, claim_type="ALLOW")
            deny = make_source(source_id="D", level=level, claim_type="DENY")
            
            conflict = detect_conflict(allow, deny)
            result = resolve_conflict(conflict)
            
            assert result.winning_source_id == "D", f"DENY should win at {level}"
