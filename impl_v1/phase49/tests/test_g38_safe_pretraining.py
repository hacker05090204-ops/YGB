# Test G38 Safe Pre-Training
"""
Comprehensive tests for G38 Safe Auto-Mode Pre-Training Governance.

Tests cover:
- Training mode definitions
- MODE-A vs MODE-B status
- Safe data sources
- Forbidden data sources
- Sample validation
- All pretraining guards
"""

import pytest

from impl_v1.phase49.governors.g38_safe_pretraining import (
    # Training Modes
    TrainingMode,
    TrainingModeStatus,
    TrainingModeConfig,
    MODE_A_CONFIG,
    MODE_B_CONFIG,
    # Learning Types
    AllowedLearningType,
    ForbiddenLearningType,
    # Data Sources
    SafeDataSource,
    ForbiddenDataSource,
    # Sample Definitions
    PretrainingSample,
    PretrainingValidation,
    PretrainingBatch,
    # Mode Status
    get_mode_a_status,
    get_mode_b_status,
    is_mode_b_unlocked,
    # Validation
    validate_pretraining_sample,
    is_source_safe,
    is_source_forbidden,
    check_learning_type_allowed,
    # Guards
    can_ai_learn_bug_labels_from_internet,
    can_ai_learn_severity_from_internet,
    can_ai_learn_acceptance_status,
    can_ai_use_platform_outcomes,
    can_mode_b_activate_without_proofs,
    can_ai_train_on_scanner_verdicts,
    PRETRAINING_GUARDS,
    verify_pretraining_guards,
    # Batch Creation
    create_pretraining_batch,
    # Summary
    get_training_mode_summary,
    get_safe_sources_list,
    get_forbidden_sources_list,
)


# =============================================================================
# TRAINING MODE TESTS
# =============================================================================

class TestTrainingModes:
    """Tests for training mode definitions."""
    
    def test_mode_representation_only_exists(self):
        assert TrainingMode.REPRESENTATION_ONLY.value == "REPRESENTATION_ONLY"
    
    def test_mode_proof_learning_exists(self):
        assert TrainingMode.PROOF_LEARNING.value == "PROOF_LEARNING"
    
    def test_mode_a_is_active(self):
        assert MODE_A_CONFIG.status == TrainingModeStatus.ACTIVE
    
    def test_mode_b_is_locked(self):
        assert MODE_B_CONFIG.status == TrainingModeStatus.LOCKED
    
    def test_mode_a_allows_internet(self):
        assert MODE_A_CONFIG.internet_allowed is True
    
    def test_mode_a_forbids_bug_labels(self):
        assert MODE_A_CONFIG.bug_label_learning is False
    
    def test_mode_b_forbids_internet(self):
        assert MODE_B_CONFIG.internet_allowed is False


class TestModeStatus:
    """Tests for mode status checks."""
    
    def test_mode_a_status_is_active(self):
        status, msg = get_mode_a_status()
        assert status == TrainingModeStatus.ACTIVE
    
    def test_mode_b_status_is_locked(self):
        status, msg = get_mode_b_status()
        assert status == TrainingModeStatus.LOCKED
    
    def test_mode_b_not_unlocked(self):
        assert is_mode_b_unlocked() is False


# =============================================================================
# ALLOWED LEARNING TYPE TESTS
# =============================================================================

class TestAllowedLearningTypes:
    """Tests for allowed learning types."""
    
    def test_http_request_response_shapes(self):
        assert AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES.value == "HTTP_REQUEST_RESPONSE_SHAPES"
    
    def test_dom_structure_patterns(self):
        assert AllowedLearningType.DOM_STRUCTURE_PATTERNS.value == "DOM_STRUCTURE_PATTERNS"
    
    def test_auth_flow_topology(self):
        assert AllowedLearningType.AUTH_FLOW_TOPOLOGY.value == "AUTH_FLOW_TOPOLOGY"
    
    def test_oauth_sso_structure(self):
        assert AllowedLearningType.OAUTH_SSO_STRUCTURE.value == "OAUTH_SSO_STRUCTURE"
    
    def test_api_graphql_schemas(self):
        assert AllowedLearningType.API_GRAPHQL_SCHEMAS.value == "API_GRAPHQL_SCHEMAS"
    
    def test_error_response_morphology(self):
        assert AllowedLearningType.ERROR_RESPONSE_MORPHOLOGY.value == "ERROR_RESPONSE_MORPHOLOGY"
    
    def test_parameter_behavior(self):
        assert AllowedLearningType.PARAMETER_BEHAVIOR.value == "PARAMETER_BEHAVIOR"
    
    def test_duplicate_fingerprints(self):
        assert AllowedLearningType.DUPLICATE_FINGERPRINTS.value == "DUPLICATE_FINGERPRINTS"
    
    def test_noise_patterns(self):
        assert AllowedLearningType.NOISE_PATTERNS.value == "NOISE_PATTERNS"


class TestForbiddenLearningTypes:
    """Tests for forbidden learning types."""
    
    def test_bug_labels_forbidden(self):
        assert ForbiddenLearningType.BUG_LABELS.value == "BUG_LABELS"
    
    def test_severity_ratings_forbidden(self):
        assert ForbiddenLearningType.SEVERITY_RATINGS.value == "SEVERITY_RATINGS"
    
    def test_acceptance_rejection_forbidden(self):
        assert ForbiddenLearningType.ACCEPTANCE_REJECTION.value == "ACCEPTANCE_REJECTION"
    
    def test_platform_outcomes_forbidden(self):
        assert ForbiddenLearningType.PLATFORM_OUTCOMES.value == "PLATFORM_OUTCOMES"


# =============================================================================
# SAFE DATA SOURCE TESTS
# =============================================================================

class TestSafeDataSources:
    """Tests for safe data sources."""
    
    def test_owasp_juice_shop(self):
        assert SafeDataSource.OWASP_JUICE_SHOP.value == "OWASP_JUICE_SHOP"
    
    def test_webgoat(self):
        assert SafeDataSource.WEBGOAT.value == "WEBGOAT"
    
    def test_dvwa(self):
        assert SafeDataSource.DVWA.value == "DVWA"
    
    def test_portswigger_labs(self):
        assert SafeDataSource.PORTSWIGGER_LABS.value == "PORTSWIGGER_LABS"
    
    def test_openapi_specs(self):
        assert SafeDataSource.OPENAPI_SPECS.value == "OPENAPI_SPECS"
    
    def test_cve_metadata_structure(self):
        assert SafeDataSource.CVE_METADATA_STRUCTURE.value == "CVE_METADATA_STRUCTURE"
    
    def test_http_traffic_replays(self):
        assert SafeDataSource.HTTP_TRAFFIC_REPLAYS.value == "HTTP_TRAFFIC_REPLAYS"
    
    def test_dom_snapshots(self):
        assert SafeDataSource.DOM_SNAPSHOTS.value == "DOM_SNAPSHOTS"
    
    def test_source_safety_check(self):
        is_safe, msg = is_source_safe(SafeDataSource.OWASP_JUICE_SHOP)
        assert is_safe is True


class TestForbiddenDataSources:
    """Tests for forbidden data sources."""
    
    def test_hackerone_forbidden(self):
        assert ForbiddenDataSource.HACKERONE_REPORTS_AS_TRUTH.value == "HACKERONE_REPORTS_AS_TRUTH"
    
    def test_bugcrowd_forbidden(self):
        assert ForbiddenDataSource.BUGCROWD_REPORTS_AS_TRUTH.value == "BUGCROWD_REPORTS_AS_TRUTH"
    
    def test_forum_claims_forbidden(self):
        assert ForbiddenDataSource.FORUM_CLAIMS.value == "FORUM_CLAIMS"
    
    def test_scanner_verdicts_forbidden(self):
        assert ForbiddenDataSource.SCANNER_VERDICTS.value == "SCANNER_VERDICTS"
    
    def test_is_hackerone_forbidden(self):
        is_forbidden, msg = is_source_forbidden("hackerone_reports")
        assert is_forbidden is True
    
    def test_is_severity_keyword_forbidden(self):
        is_forbidden, msg = is_source_forbidden("critical_bugs_list")
        assert is_forbidden is True


# =============================================================================
# SAMPLE VALIDATION TESTS
# =============================================================================

class TestSampleValidation:
    """Tests for sample validation."""
    
    def test_valid_mode_a_sample(self):
        sample = PretrainingSample(
            sample_id="SMP-001",
            source=SafeDataSource.OWASP_JUICE_SHOP,
            learning_type=AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES,
            mode=TrainingMode.REPRESENTATION_ONLY,
            contains_bug_labels=False,
            contains_severity=False,
            contains_acceptance_status=False,
            raw_data_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
        )
        validation = validate_pretraining_sample(sample)
        assert validation.is_valid is True
        assert len(validation.violations) == 0
    
    def test_invalid_sample_with_bug_labels(self):
        sample = PretrainingSample(
            sample_id="SMP-002",
            source=SafeDataSource.OWASP_JUICE_SHOP,
            learning_type=AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES,
            mode=TrainingMode.REPRESENTATION_ONLY,
            contains_bug_labels=True,  # FORBIDDEN
            contains_severity=False,
            contains_acceptance_status=False,
            raw_data_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
        )
        validation = validate_pretraining_sample(sample)
        assert validation.is_valid is False
        assert "bug labels" in validation.violations[0].lower()
    
    def test_invalid_sample_with_severity(self):
        sample = PretrainingSample(
            sample_id="SMP-003",
            source=SafeDataSource.WEBGOAT,
            learning_type=AllowedLearningType.DOM_STRUCTURE_PATTERNS,
            mode=TrainingMode.REPRESENTATION_ONLY,
            contains_bug_labels=False,
            contains_severity=True,  # FORBIDDEN
            contains_acceptance_status=False,
            raw_data_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
        )
        validation = validate_pretraining_sample(sample)
        assert validation.is_valid is False
        assert "severity" in validation.violations[0].lower()
    
    def test_invalid_sample_with_acceptance_status(self):
        sample = PretrainingSample(
            sample_id="SMP-004",
            source=SafeDataSource.DVWA,
            learning_type=AllowedLearningType.AUTH_FLOW_TOPOLOGY,
            mode=TrainingMode.REPRESENTATION_ONLY,
            contains_bug_labels=False,
            contains_severity=False,
            contains_acceptance_status=True,  # FORBIDDEN
            raw_data_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
        )
        validation = validate_pretraining_sample(sample)
        assert validation.is_valid is False
        assert "acceptance" in validation.violations[0].lower()
    
    def test_mode_b_sample_blocked(self):
        sample = PretrainingSample(
            sample_id="SMP-005",
            source=SafeDataSource.PORTSWIGGER_LABS,
            learning_type=AllowedLearningType.API_GRAPHQL_SCHEMAS,
            mode=TrainingMode.PROOF_LEARNING,  # MODE-B: LOCKED
            contains_bug_labels=False,
            contains_severity=False,
            contains_acceptance_status=False,
            raw_data_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
        )
        validation = validate_pretraining_sample(sample)
        assert validation.is_valid is False
        assert "LOCKED" in validation.violations[0]


# =============================================================================
# GUARD TESTS (ALL RETURN FALSE)
# =============================================================================

class TestPretrainingGuards:
    """Tests for pretraining guards."""
    
    def test_cannot_learn_bug_labels_from_internet(self):
        result, msg = can_ai_learn_bug_labels_from_internet()
        assert result is False
        assert "representation only" in msg.lower()
    
    def test_cannot_learn_severity_from_internet(self):
        result, msg = can_ai_learn_severity_from_internet()
        assert result is False
        assert "representation only" in msg.lower()
    
    def test_cannot_learn_acceptance_status(self):
        result, msg = can_ai_learn_acceptance_status()
        assert result is False
    
    def test_cannot_use_platform_outcomes(self):
        result, msg = can_ai_use_platform_outcomes()
        assert result is False
    
    def test_mode_b_cannot_activate_without_proofs(self):
        result, msg = can_mode_b_activate_without_proofs()
        assert result is False
        assert "G33/G36" in msg
    
    def test_cannot_train_on_scanner_verdicts(self):
        result, msg = can_ai_train_on_scanner_verdicts()
        assert result is False


class TestAllPretrainingGuards:
    """Tests for guard collections."""
    
    def test_pretraining_guards_count(self):
        assert len(PRETRAINING_GUARDS) == 6
    
    def test_all_guards_return_false(self):
        for guard in PRETRAINING_GUARDS:
            result, msg = guard()
            assert result is False, f"{guard.__name__} returned True"
    
    def test_verify_pretraining_guards_passes(self):
        result, msg = verify_pretraining_guards()
        assert result is True
        assert "verified" in msg.lower()


# =============================================================================
# BATCH CREATION TESTS
# =============================================================================

class TestBatchCreation:
    """Tests for batch creation."""
    
    def test_create_batch_with_valid_samples(self):
        samples = (
            PretrainingSample(
                sample_id="SMP-001",
                source=SafeDataSource.OWASP_JUICE_SHOP,
                learning_type=AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES,
                mode=TrainingMode.REPRESENTATION_ONLY,
                contains_bug_labels=False,
                contains_severity=False,
                contains_acceptance_status=False,
                raw_data_hash="abc123",
                created_at="2026-01-01T00:00:00Z",
            ),
            PretrainingSample(
                sample_id="SMP-002",
                source=SafeDataSource.WEBGOAT,
                learning_type=AllowedLearningType.DOM_STRUCTURE_PATTERNS,
                mode=TrainingMode.REPRESENTATION_ONLY,
                contains_bug_labels=False,
                contains_severity=False,
                contains_acceptance_status=False,
                raw_data_hash="def456",
                created_at="2026-01-01T00:00:00Z",
            ),
        )
        batch, validations = create_pretraining_batch(samples)
        assert batch.total_samples == 2
        assert batch.valid_samples == 2
        assert len(batch.samples) == 2
    
    def test_create_batch_filters_invalid_samples(self):
        samples = (
            PretrainingSample(
                sample_id="SMP-001",
                source=SafeDataSource.OWASP_JUICE_SHOP,
                learning_type=AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES,
                mode=TrainingMode.REPRESENTATION_ONLY,
                contains_bug_labels=False,
                contains_severity=False,
                contains_acceptance_status=False,
                raw_data_hash="abc123",
                created_at="2026-01-01T00:00:00Z",
            ),
            PretrainingSample(
                sample_id="SMP-002",
                source=SafeDataSource.WEBGOAT,
                learning_type=AllowedLearningType.DOM_STRUCTURE_PATTERNS,
                mode=TrainingMode.REPRESENTATION_ONLY,
                contains_bug_labels=True,  # INVALID
                contains_severity=False,
                contains_acceptance_status=False,
                raw_data_hash="def456",
                created_at="2026-01-01T00:00:00Z",
            ),
        )
        batch, validations = create_pretraining_batch(samples)
        assert batch.total_samples == 2
        assert batch.valid_samples == 1  # Only 1 valid


# =============================================================================
# SUMMARY TESTS
# =============================================================================

class TestSummaryFunctions:
    """Tests for summary functions."""
    
    def test_get_training_mode_summary(self):
        summary = get_training_mode_summary()
        assert "MODE-A" in summary
        assert "MODE-B" in summary
        assert "ACTIVE" in summary
        assert "LOCKED" in summary
    
    def test_get_safe_sources_list(self):
        sources = get_safe_sources_list()
        assert len(sources) >= 8
        assert "OWASP_JUICE_SHOP" in sources
    
    def test_get_forbidden_sources_list(self):
        sources = get_forbidden_sources_list()
        assert len(sources) >= 4
        assert "HACKERONE_REPORTS_AS_TRUTH" in sources


# =============================================================================
# LEARNING TYPE ALLOWED TESTS
# =============================================================================

class TestLearningTypeAllowed:
    """Tests for learning type allowed checks."""
    
    def test_mode_a_allows_http_learning(self):
        allowed, msg = check_learning_type_allowed(
            AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES,
            TrainingMode.REPRESENTATION_ONLY,
        )
        assert allowed is True
    
    def test_mode_b_blocks_all_learning(self):
        allowed, msg = check_learning_type_allowed(
            AllowedLearningType.HTTP_REQUEST_RESPONSE_SHAPES,
            TrainingMode.PROOF_LEARNING,
        )
        assert allowed is False
        assert "LOCKED" in msg
