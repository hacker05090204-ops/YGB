# Test G39-G43 Hardening Governors
"""
Tests for G39-G43 final hardening governors.

100% coverage required.
"""

import pytest


# =============================================================================
# G39 ENVIRONMENT FINGERPRINT TESTS
# =============================================================================

class TestG39EnvironmentFingerprint:
    """Tests for G39 environment fingerprint governor."""
    
    def test_capture_fingerprint(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            capture_environment_fingerprint,
        )
        fp = capture_environment_fingerprint()
        assert fp.fingerprint_id
        assert fp.os_name
        assert fp.python_version
    
    def test_compare_same_fingerprints(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            capture_environment_fingerprint,
            compare_fingerprints,
        )
        fp = capture_environment_fingerprint()
        matches, mismatches = compare_fingerprints(fp, fp)
        assert matches is True
        assert len(mismatches) == 0
    
    def test_detect_drift_no_baseline(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            capture_environment_fingerprint,
            detect_drift,
            DriftStatus,
            SafeMode,
        )
        current = capture_environment_fingerprint()
        drift = detect_drift(None, current)
        assert drift.status == DriftStatus.UNKNOWN
        assert drift.recommended_mode == SafeMode.SAFE
    
    def test_detect_drift_trusted(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            capture_environment_fingerprint,
            detect_drift,
            DriftStatus,
            SafeMode,
        )
        fp = capture_environment_fingerprint()
        drift = detect_drift(fp, fp)
        assert drift.status == DriftStatus.TRUSTED
        assert drift.recommended_mode == SafeMode.NORMAL
    
    def test_should_enter_safe_mode(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            capture_environment_fingerprint,
            detect_drift,
            should_enter_safe_mode,
        )
        fp = capture_environment_fingerprint()
        drift = detect_drift(None, fp)
        assert should_enter_safe_mode(drift) is True
    
    def test_guards_return_false(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            can_ignore_environment_drift,
            can_override_safe_mode,
            can_train_on_untrusted_env,
        )
        assert can_ignore_environment_drift()[0] is False
        assert can_override_safe_mode()[0] is False
        assert can_train_on_untrusted_env()[0] is False


# =============================================================================
# G40 TRAINING QUORUM TESTS
# =============================================================================

class TestG40TrainingQuorum:
    """Tests for G40 training quorum governor."""
    
    def test_quorum_not_met_empty(self):
        from impl_v1.phase49.governors.g40_training_quorum import (
            check_quorum,
            QuorumStatus,
        )
        result = check_quorum(tuple())
        assert result.status == QuorumStatus.NOT_MET
        assert result.can_train is False
    
    def test_quorum_met(self):
        from impl_v1.phase49.governors.g40_training_quorum import (
            check_quorum,
            QuorumStatus,
            TrainingDataPoint,
            DataCategory,
        )
        data = tuple([
            TrainingDataPoint(f"D{i}", DataCategory.VERIFIED_BUG, 0.9, "G33", True)
            for i in range(5)
        ] + [
            TrainingDataPoint(f"R{i}", DataCategory.REJECTED_FINDING, 0.9, "G33", True)
            for i in range(3)
        ])
        result = check_quorum(data)
        assert result.status == QuorumStatus.MET
        assert result.can_train is True
    
    def test_calculate_weights(self):
        from impl_v1.phase49.governors.g40_training_quorum import (
            calculate_training_weights,
            TrainingDataPoint,
            DataCategory,
        )
        data = (
            TrainingDataPoint("D1", DataCategory.VERIFIED_BUG, 0.9, "G33", True),
            TrainingDataPoint("R1", DataCategory.REJECTED_FINDING, 0.9, "G33", True),
        )
        weights = calculate_training_weights(data)
        # Rejection should be weighted higher
        assert weights[1][1] > weights[0][1]
    
    def test_filter_low_confidence(self):
        from impl_v1.phase49.governors.g40_training_quorum import (
            filter_low_confidence,
            TrainingDataPoint,
            DataCategory,
        )
        data = (
            TrainingDataPoint("D1", DataCategory.VERIFIED_BUG, 0.5, "G33", True),
            TrainingDataPoint("D2", DataCategory.VERIFIED_BUG, 0.95, "G33", True),
        )
        filtered = filter_low_confidence(data, 0.85)
        assert len(filtered) == 1
    
    def test_guards_return_false(self):
        from impl_v1.phase49.governors.g40_training_quorum import (
            can_learn_from_single_report,
            can_learn_from_low_confidence,
            can_override_quorum,
        )
        assert can_learn_from_single_report()[0] is False
        assert can_learn_from_low_confidence()[0] is False
        assert can_override_quorum()[0] is False


# =============================================================================
# G41 PLATFORM POLICY TESTS
# =============================================================================

class TestG41PlatformPolicy:
    """Tests for G41 platform policy governor."""
    
    def test_get_hackerone_profile(self):
        from impl_v1.phase49.governors.g41_platform_policy import (
            get_platform_profile,
        )
        profile = get_platform_profile("hackerone")
        assert profile is not None
        assert profile.platform_name == "HackerOne"
    
    def test_check_category_allowed(self):
        from impl_v1.phase49.governors.g41_platform_policy import (
            get_platform_profile,
            check_category_allowed,
            TestingCategory,
        )
        profile = get_platform_profile("hackerone")
        assert check_category_allowed(profile, TestingCategory.XSS) is True
    
    def test_check_method_disallowed(self):
        from impl_v1.phase49.governors.g41_platform_policy import (
            get_platform_profile,
            check_method_allowed,
        )
        profile = get_platform_profile("hackerone")
        assert check_method_allowed(profile, "denial_of_service") is False
    
    def test_check_policy_allowed(self):
        from impl_v1.phase49.governors.g41_platform_policy import (
            get_platform_profile,
            check_policy,
            TestingCategory,
        )
        profile = get_platform_profile("hackerone")
        result = check_policy(profile, TestingCategory.XSS, "GET", "https://example.com")
        assert result.action_allowed is True
    
    def test_check_policy_rate_limited(self):
        from impl_v1.phase49.governors.g41_platform_policy import (
            get_platform_profile,
            check_policy,
            TestingCategory,
        )
        profile = get_platform_profile("hackerone")
        result = check_policy(
            profile, TestingCategory.XSS, "GET", "https://example.com",
            current_requests_minute=100
        )
        assert result.action_allowed is False
    
    def test_guards_return_false(self):
        from impl_v1.phase49.governors.g41_platform_policy import (
            can_ignore_platform_policy,
            can_override_rate_limits,
            can_use_disallowed_methods,
        )
        assert can_ignore_platform_policy()[0] is False
        assert can_override_rate_limits()[0] is False
        assert can_use_disallowed_methods()[0] is False


# =============================================================================
# G42 REPORT DIVERSITY TESTS
# =============================================================================

class TestG42ReportDiversity:
    """Tests for G42 report diversity governor."""
    
    def test_create_pattern_pool(self):
        from impl_v1.phase49.governors.g42_report_diversity import (
            create_pattern_pool,
        )
        pool = create_pattern_pool()
        assert len(pool.patterns) == 6
    
    def test_get_available_patterns(self):
        from impl_v1.phase49.governors.g42_report_diversity import (
            create_pattern_pool,
            get_available_patterns,
        )
        pool = create_pattern_pool()
        available = get_available_patterns(pool)
        assert len(available) == 6
    
    def test_select_diverse_pattern(self):
        from impl_v1.phase49.governors.g42_report_diversity import (
            create_pattern_pool,
            select_diverse_pattern,
        )
        pool = create_pattern_pool()
        pattern = select_diverse_pattern(pool)
        assert pattern.pattern_id.startswith("STR-")
    
    def test_calculate_diversity_score(self):
        from impl_v1.phase49.governors.g42_report_diversity import (
            create_pattern_pool,
            calculate_diversity_score,
        )
        pool = create_pattern_pool()
        score = calculate_diversity_score(pool)
        assert score.entropy == 1.0
        assert score.is_diverse is True
    
    def test_update_cooldown(self):
        from impl_v1.phase49.governors.g42_report_diversity import (
            create_pattern_pool,
            update_pattern_cooldown,
            get_available_patterns,
        )
        pool = create_pattern_pool()
        updated = update_pattern_cooldown(pool, "STR-001", cooldown=2)
        available = get_available_patterns(updated)
        assert len(available) == 5
    
    def test_guards_return_false(self):
        from impl_v1.phase49.governors.g42_report_diversity import (
            can_reuse_report_pattern,
            can_force_single_template,
        )
        assert can_reuse_report_pattern()[0] is False
        assert can_force_single_template()[0] is False


# =============================================================================
# G43 AUTO-MODE SAFETY TESTS
# =============================================================================

class TestG43AutoModeSafety:
    """Tests for G43 auto-mode safety governor."""
    
    def test_allowed_actions(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            is_action_allowed,
            AutoAction,
        )
        assert is_action_allowed(AutoAction.VERIFY_BUG) is True
        assert is_action_allowed(AutoAction.GENERATE_REPORT) is True
    
    def test_forbidden_actions(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            is_action_forbidden,
            AutoAction,
        )
        assert is_action_forbidden(AutoAction.EXECUTE_EXPLOIT) is True
        assert is_action_forbidden(AutoAction.SUBMIT_REPORT) is True
    
    def test_check_auto_action_allowed(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            check_auto_action,
            AutoActionRequest,
            AutoAction,
        )
        request = AutoActionRequest("REQ-1", AutoAction.VERIFY_BUG, "target", "ctx")
        result = check_auto_action(request)
        assert result.allowed is True
    
    def test_check_auto_action_forbidden(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            check_auto_action,
            AutoActionRequest,
            AutoAction,
        )
        request = AutoActionRequest("REQ-1", AutoAction.SUBMIT_REPORT, "target", "ctx")
        result = check_auto_action(request)
        assert result.allowed is False
    
    def test_validate_safety(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            validate_auto_mode_safety,
            AutoAction,
        )
        safe, violations = validate_auto_mode_safety((
            AutoAction.VERIFY_BUG,
            AutoAction.GENERATE_REPORT,
        ))
        assert safe is True
        assert len(violations) == 0
    
    def test_validate_safety_violations(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            validate_auto_mode_safety,
            AutoAction,
        )
        safe, violations = validate_auto_mode_safety((
            AutoAction.VERIFY_BUG,
            AutoAction.SUBMIT_REPORT,
        ))
        assert safe is False
        assert len(violations) == 1
    
    def test_guards_return_false(self):
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            can_auto_exploit,
            can_auto_submit,
            can_auto_expand_scope,
            can_auto_override_safety,
        )
        assert can_auto_exploit()[0] is False
        assert can_auto_submit()[0] is False
        assert can_auto_expand_scope()[0] is False
        assert can_auto_override_safety()[0] is False


# =============================================================================
# ALL GUARDS COMPREHENSIVE TEST
# =============================================================================

class TestAllHardeningGuards:
    """Comprehensive test all hardening guards return False."""
    
    def test_all_guards_return_false(self):
        from impl_v1.phase49.governors.g39_environment_fingerprint import (
            can_ignore_environment_drift,
            can_override_safe_mode,
            can_train_on_untrusted_env,
        )
        from impl_v1.phase49.governors.g40_training_quorum import (
            can_learn_from_single_report,
            can_learn_from_low_confidence,
            can_override_quorum,
        )
        from impl_v1.phase49.governors.g41_platform_policy import (
            can_ignore_platform_policy,
            can_override_rate_limits,
            can_use_disallowed_methods,
        )
        from impl_v1.phase49.governors.g42_report_diversity import (
            can_reuse_report_pattern,
            can_force_single_template,
        )
        from impl_v1.phase49.governors.g43_auto_mode_safety import (
            can_auto_exploit,
            can_auto_submit,
            can_auto_expand_scope,
            can_auto_override_safety,
        )
        
        guards = [
            can_ignore_environment_drift,
            can_override_safe_mode,
            can_train_on_untrusted_env,
            can_learn_from_single_report,
            can_learn_from_low_confidence,
            can_override_quorum,
            can_ignore_platform_policy,
            can_override_rate_limits,
            can_use_disallowed_methods,
            can_reuse_report_pattern,
            can_force_single_template,
            can_auto_exploit,
            can_auto_submit,
            can_auto_expand_scope,
            can_auto_override_safety,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result is False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0
