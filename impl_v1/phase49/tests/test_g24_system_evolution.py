# test_g24_system_evolution.py
"""Tests for G24 System Evolution & Stability Governor."""

import pytest

from impl_v1.phase49.governors.g24_system_evolution import (
    PythonVersionStatus,
    DependencyStatus,
    UpdateDecision,
    SystemMode,
    HealthStatus,
    RollbackDecision,
    SUPPORTED_PYTHON_VERSIONS,
    DEPRECATED_PYTHON_VERSIONS,
    PythonVersionCheck,
    DependencyHash,
    DependencyCheck,
    UpdatePolicy,
    UpdateCheck,
    GovernorHealth,
    SystemHealthCheck,
    RollbackCheck,
    get_current_python_version,
    check_python_version_status,
    check_python_version_upgrade,
    create_dependency_hash,
    check_dependency_stability,
    create_update_policy,
    check_update_policy,
    check_governor_health,
    check_system_health,
    check_rollback_availability,
    can_evolution_governor_execute,
    can_evolution_governor_modify,
    can_evolution_governor_approve,
)


class TestPythonVersionStatus:
    """Tests for PythonVersionStatus enum."""
    
    def test_has_supported(self):
        assert PythonVersionStatus.SUPPORTED.value == "SUPPORTED"
    
    def test_has_deprecated(self):
        assert PythonVersionStatus.DEPRECATED.value == "DEPRECATED"
    
    def test_has_unsupported(self):
        assert PythonVersionStatus.UNSUPPORTED.value == "UNSUPPORTED"
    
    def test_has_future(self):
        assert PythonVersionStatus.FUTURE.value == "FUTURE"


class TestUpdateDecision:
    """Tests for UpdateDecision enum."""
    
    def test_has_allow(self):
        assert UpdateDecision.ALLOW.value == "ALLOW"
    
    def test_has_hold(self):
        assert UpdateDecision.HOLD.value == "HOLD"
    
    def test_has_block(self):
        assert UpdateDecision.BLOCK.value == "BLOCK"
    
    def test_has_simulate_only(self):
        assert UpdateDecision.SIMULATE_ONLY.value == "SIMULATE_ONLY"


class TestSupportedVersions:
    """Tests for supported Python versions."""
    
    def test_3_10_supported(self):
        assert (3, 10) in SUPPORTED_PYTHON_VERSIONS
    
    def test_3_11_supported(self):
        assert (3, 11) in SUPPORTED_PYTHON_VERSIONS
    
    def test_3_12_supported(self):
        assert (3, 12) in SUPPORTED_PYTHON_VERSIONS
    
    def test_3_13_supported(self):
        assert (3, 13) in SUPPORTED_PYTHON_VERSIONS
    
    def test_3_8_deprecated(self):
        assert (3, 8) in DEPRECATED_PYTHON_VERSIONS
    
    def test_3_9_deprecated(self):
        assert (3, 9) in DEPRECATED_PYTHON_VERSIONS


class TestCheckPythonVersionStatus:
    """Tests for check_python_version_status function."""
    
    def test_supported_version(self):
        status = check_python_version_status((3, 12))
        assert status == PythonVersionStatus.SUPPORTED
    
    def test_deprecated_version(self):
        status = check_python_version_status((3, 9))
        assert status == PythonVersionStatus.DEPRECATED
    
    def test_unsupported_version(self):
        status = check_python_version_status((3, 7))
        assert status == PythonVersionStatus.UNSUPPORTED
    
    def test_future_version(self):
        status = check_python_version_status((3, 14))
        assert status == PythonVersionStatus.FUTURE


class TestCheckPythonVersionUpgrade:
    """Tests for check_python_version_upgrade function."""
    
    def test_no_target_returns_current(self):
        result = check_python_version_upgrade()
        assert isinstance(result, PythonVersionCheck)
        assert result.target_version is None
    
    def test_supported_target_allows(self):
        result = check_python_version_upgrade((3, 12, 0))
        assert result.decision == UpdateDecision.ALLOW
    
    def test_unsupported_target_blocks(self):
        result = check_python_version_upgrade((3, 7, 0))
        assert result.decision == UpdateDecision.BLOCK
        assert "UNSUPPORTED" in result.reason
    
    def test_deprecated_target_holds(self):
        result = check_python_version_upgrade((3, 9, 0))
        assert result.decision == UpdateDecision.HOLD
        assert "DEPRECATED" in result.reason
    
    def test_future_target_simulates(self):
        result = check_python_version_upgrade((3, 15, 0))
        assert result.decision == UpdateDecision.SIMULATE_ONLY
        assert "FUTURE" in result.reason


class TestCreateDependencyHash:
    """Tests for create_dependency_hash function."""
    
    def test_creates_hash(self):
        packages = {"pytest": "7.0.0", "requests": "2.28.0"}
        result = create_dependency_hash(packages)
        assert isinstance(result, DependencyHash)
    
    def test_hash_has_package_count(self):
        packages = {"a": "1.0", "b": "2.0", "c": "3.0"}
        result = create_dependency_hash(packages)
        assert result.package_count == 3
    
    def test_same_packages_same_hash(self):
        packages = {"pytest": "7.0.0", "requests": "2.28.0"}
        hash1 = create_dependency_hash(packages)
        hash2 = create_dependency_hash(packages)
        assert hash1.combined_hash == hash2.combined_hash
    
    def test_different_packages_different_hash(self):
        hash1 = create_dependency_hash({"a": "1.0"})
        hash2 = create_dependency_hash({"a": "2.0"})
        assert hash1.combined_hash != hash2.combined_hash


class TestCheckDependencyStability:
    """Tests for check_dependency_stability function."""
    
    def test_no_changes_stable(self):
        packages = {"pytest": "7.0.0"}
        result = check_dependency_stability(packages, packages)
        assert result.status == DependencyStatus.STABLE
        assert result.decision == UpdateDecision.ALLOW
    
    def test_minor_change(self):
        current = {"pytest": "7.0.0"}
        target = {"pytest": "7.1.0"}
        result = check_dependency_stability(current, target)
        assert result.status == DependencyStatus.MINOR_CHANGE
        assert result.decision == UpdateDecision.ALLOW
    
    def test_major_change_breaking(self):
        current = {"pytest": "7.0.0"}
        target = {"pytest": "8.0.0"}
        result = check_dependency_stability(current, target)
        assert result.status == DependencyStatus.BREAKING_CHANGE
        assert result.decision == UpdateDecision.SIMULATE_ONLY
    
    def test_removed_package_breaking(self):
        current = {"pytest": "7.0.0", "requests": "2.0.0"}
        target = {"pytest": "7.0.0"}
        result = check_dependency_stability(current, target)
        assert result.status == DependencyStatus.BREAKING_CHANGE
        assert "requests" in str(result.breaking_packages)


class TestCreateUpdatePolicy:
    """Tests for create_update_policy function."""
    
    def test_creates_policy(self):
        policy = create_update_policy()
        assert isinstance(policy, UpdatePolicy)
    
    def test_requires_signed(self):
        policy = create_update_policy()
        assert policy.require_signed == True
    
    def test_requires_compatible(self):
        policy = create_update_policy()
        assert policy.require_compatible == True
    
    def test_requires_tested(self):
        policy = create_update_policy()
        assert policy.require_tested == True
    
    def test_requires_approved(self):
        policy = create_update_policy()
        assert policy.require_approved == True
    
    def test_auto_update_never_allowed(self):
        policy = create_update_policy()
        assert policy.auto_update_allowed == False


class TestCheckUpdatePolicy:
    """Tests for check_update_policy function."""
    
    def test_all_met_allows(self):
        policy = create_update_policy()
        result = check_update_policy(policy, True, True, True, True)
        assert result.decision == UpdateDecision.ALLOW
        assert len(result.missing_requirements) == 0
    
    def test_missing_approval_holds(self):
        policy = create_update_policy()
        result = check_update_policy(policy, True, True, True, False)
        assert result.decision == UpdateDecision.HOLD
        assert "APPROVAL" in result.missing_requirements
    
    def test_missing_signature_blocks(self):
        policy = create_update_policy()
        result = check_update_policy(policy, False, True, True, True)
        assert result.decision == UpdateDecision.BLOCK
        assert "SIGNATURE" in result.missing_requirements
    
    def test_missing_multiple_blocks(self):
        policy = create_update_policy()
        result = check_update_policy(policy, False, False, True, True)
        assert result.decision == UpdateDecision.BLOCK
        assert len(result.missing_requirements) == 2


class TestCheckGovernorHealth:
    """Tests for check_governor_health function."""
    
    def test_healthy_governor(self):
        result = check_governor_health("G01", True, True, True)
        assert result.status == HealthStatus.HEALTHY
        assert len(result.anomalies) == 0
    
    def test_guard_not_blocking_critical(self):
        result = check_governor_health("G01", False, True, True)
        assert result.status == HealthStatus.CRITICAL
        assert "GUARD_NOT_BLOCKING" in result.anomalies
    
    def test_no_tests_degraded(self):
        result = check_governor_health("G01", True, False, True)
        assert result.status == HealthStatus.DEGRADED
        assert "NO_TESTS" in result.anomalies
    
    def test_tests_failing_degraded(self):
        result = check_governor_health("G01", True, True, False)
        assert result.status == HealthStatus.DEGRADED
        assert "TESTS_FAILING" in result.anomalies


class TestCheckSystemHealth:
    """Tests for check_system_health function."""
    
    def test_all_healthy_normal_mode(self):
        governors = [
            check_governor_health(f"G{i}", True, True, True)
            for i in range(1, 4)
        ]
        result = check_system_health(governors, "hash1", "hash1", 100, 100)
        assert result.overall_status == HealthStatus.HEALTHY
        assert result.recommended_mode == SystemMode.NORMAL
    
    def test_critical_governor_safe_mode(self):
        governors = [
            check_governor_health("G01", False, True, True),  # Critical
            check_governor_health("G02", True, True, True),
        ]
        result = check_system_health(governors, "hash1", "hash1", 100, 100)
        assert result.overall_status == HealthStatus.CRITICAL
        assert result.recommended_mode == SystemMode.SAFE_MODE
    
    def test_drift_detected_safe_mode(self):
        governors = [check_governor_health("G01", True, True, True)]
        result = check_system_health(governors, "hash1", "hash2", 100, 100)
        assert result.drift_detected == True
        assert result.recommended_mode == SystemMode.SAFE_MODE
    
    def test_test_regression_safe_mode(self):
        governors = [check_governor_health("G01", True, True, True)]
        result = check_system_health(governors, "hash1", "hash1", 100, 90)
        assert result.test_regression_detected == True
        assert result.recommended_mode == SystemMode.SAFE_MODE


class TestCheckRollbackAvailability:
    """Tests for check_rollback_availability function."""
    
    def test_no_backup_unavailable(self):
        result = check_rollback_availability(False, None, None, None)
        assert result.decision == RollbackDecision.UNAVAILABLE
        assert result.rollback_available == False
    
    def test_bad_integrity_unavailable(self):
        result = check_rollback_availability(True, "1.0.0", "hash1", "hash2")
        assert result.decision == RollbackDecision.UNAVAILABLE
        assert result.integrity_verified == False
    
    def test_good_backup_requires_confirmation(self):
        result = check_rollback_availability(True, "1.0.0", "hash1", "hash1")
        assert result.decision == RollbackDecision.REQUIRES_CONFIRMATION
        assert result.requires_human == True
        assert result.rollback_available == True
    
    def test_always_requires_human(self):
        result = check_rollback_availability(True, "1.0.0", "hash1", "hash1")
        assert result.requires_human == True


class TestCanEvolutionGovernorExecute:
    """Tests for can_evolution_governor_execute guard."""
    
    def test_cannot_execute(self):
        can_exec, reason = can_evolution_governor_execute()
        assert can_exec == False
        assert "DECISION ONLY" in reason


class TestCanEvolutionGovernorModify:
    """Tests for can_evolution_governor_modify guard."""
    
    def test_cannot_modify(self):
        can_mod, reason = can_evolution_governor_modify()
        assert can_mod == False
        assert "read-only" in reason.lower()


class TestCanEvolutionGovernorApprove:
    """Tests for can_evolution_governor_approve guard."""
    
    def test_cannot_approve(self):
        can_approve, reason = can_evolution_governor_approve()
        assert can_approve == False
        assert "human" in reason.lower()


class TestGuardsAlwaysFalse:
    """Tests that ALL guards always return False."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_evolution_governor_execute,
            can_evolution_governor_modify,
            can_evolution_governor_approve,
        ]
        
        for guard in guards:
            result, _ = guard()
            assert result == False, f"{guard.__name__} must return False"
