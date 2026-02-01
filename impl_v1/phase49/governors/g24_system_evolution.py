# G24: System Evolution & Stability Governor
"""
GOVERNANCE-ONLY layer for future-proofing and stability.

This governor DECIDES but NEVER EXECUTES.

RESPONSIBILITIES:
1. Python version governance
2. Dependency stability governance
3. Update policy governance
4. Self-stability checks
5. Rollback governance

ABSOLUTE GUARANTEES:
- Can NEVER execute code
- Can NEVER trigger browser
- Can NEVER modify system state
- Can NEVER approve execution
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Tuple, Dict, FrozenSet
import uuid
from datetime import datetime, UTC
import hashlib
import sys


class PythonVersionStatus(Enum):
    """CLOSED ENUM - Python version compatibility"""
    SUPPORTED = "SUPPORTED"
    DEPRECATED = "DEPRECATED"
    UNSUPPORTED = "UNSUPPORTED"
    FUTURE = "FUTURE"


class DependencyStatus(Enum):
    """CLOSED ENUM - Dependency check status"""
    STABLE = "STABLE"
    MINOR_CHANGE = "MINOR_CHANGE"
    BREAKING_CHANGE = "BREAKING_CHANGE"
    UNKNOWN = "UNKNOWN"


class UpdateDecision(Enum):
    """CLOSED ENUM - Update decisions"""
    ALLOW = "ALLOW"
    HOLD = "HOLD"
    BLOCK = "BLOCK"
    SIMULATE_ONLY = "SIMULATE_ONLY"


class SystemMode(Enum):
    """CLOSED ENUM - System operating modes"""
    NORMAL = "NORMAL"
    SAFE_MODE = "SAFE_MODE"
    MAINTENANCE = "MAINTENANCE"


class HealthStatus(Enum):
    """CLOSED ENUM - Health check status"""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class RollbackDecision(Enum):
    """CLOSED ENUM - Rollback decisions"""
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"


# Supported Python version matrix
SUPPORTED_PYTHON_VERSIONS: FrozenSet[Tuple[int, int]] = frozenset([
    (3, 10),
    (3, 11),
    (3, 12),
    (3, 13),
])

DEPRECATED_PYTHON_VERSIONS: FrozenSet[Tuple[int, int]] = frozenset([
    (3, 8),
    (3, 9),
])


@dataclass(frozen=True)
class PythonVersionCheck:
    """Result of Python version check."""
    check_id: str
    current_version: Tuple[int, int, int]
    target_version: Optional[Tuple[int, int, int]]
    status: PythonVersionStatus
    decision: UpdateDecision
    reason: str
    timestamp: str


@dataclass(frozen=True)
class DependencyHash:
    """Hash of dependency set."""
    hash_id: str
    package_count: int
    combined_hash: str
    timestamp: str


@dataclass(frozen=True)
class DependencyCheck:
    """Result of dependency stability check."""
    check_id: str
    current_hash: DependencyHash
    target_hash: Optional[DependencyHash]
    status: DependencyStatus
    breaking_packages: tuple  # Tuple[str, ...]
    decision: UpdateDecision
    reason: str


@dataclass(frozen=True)
class UpdatePolicy:
    """Update policy configuration."""
    policy_id: str
    require_signed: bool
    require_compatible: bool
    require_tested: bool
    require_approved: bool
    auto_update_allowed: bool  # ALWAYS False


@dataclass(frozen=True)
class UpdateCheck:
    """Result of update policy check."""
    check_id: str
    is_signed: bool
    is_compatible: bool
    is_tested: bool
    is_approved: bool
    decision: UpdateDecision
    missing_requirements: tuple  # Tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class GovernorHealth:
    """Health status of a single governor."""
    governor_id: str
    governor_name: str
    status: HealthStatus
    last_check: str
    anomalies: tuple  # Tuple[str, ...]


@dataclass(frozen=True)
class SystemHealthCheck:
    """Overall system health check."""
    check_id: str
    governors_checked: int
    healthy_count: int
    degraded_count: int
    critical_count: int
    overall_status: HealthStatus
    recommended_mode: SystemMode
    drift_detected: bool
    test_regression_detected: bool
    timestamp: str


@dataclass(frozen=True)
class RollbackCheck:
    """Rollback availability check."""
    check_id: str
    rollback_available: bool
    integrity_verified: bool
    previous_version: Optional[str]
    decision: RollbackDecision
    requires_human: bool
    reason: str


# ============================================================
# PYTHON VERSION GOVERNANCE
# ============================================================

def get_current_python_version() -> Tuple[int, int, int]:
    """Get current Python version."""
    return (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)


def check_python_version_status(version: Tuple[int, int]) -> PythonVersionStatus:
    """Check if a Python version is supported."""
    if version in SUPPORTED_PYTHON_VERSIONS:
        return PythonVersionStatus.SUPPORTED
    elif version in DEPRECATED_PYTHON_VERSIONS:
        return PythonVersionStatus.DEPRECATED
    elif version[0] >= 3 and version[1] > 13:
        return PythonVersionStatus.FUTURE
    else:
        return PythonVersionStatus.UNSUPPORTED


def check_python_version_upgrade(
    target_version: Optional[Tuple[int, int, int]] = None,
) -> PythonVersionCheck:
    """
    Check Python version upgrade compatibility.
    
    If incompatible, BLOCKS update.
    """
    current = get_current_python_version()
    current_major_minor = (current[0], current[1])
    current_status = check_python_version_status(current_major_minor)
    
    if target_version is None:
        return PythonVersionCheck(
            check_id=f"PYC-{uuid.uuid4().hex[:16].upper()}",
            current_version=current,
            target_version=None,
            status=current_status,
            decision=UpdateDecision.ALLOW if current_status == PythonVersionStatus.SUPPORTED else UpdateDecision.HOLD,
            reason=f"Current version {current} is {current_status.value}",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    target_major_minor = (target_version[0], target_version[1])
    target_status = check_python_version_status(target_major_minor)
    
    # Decision logic
    if target_status == PythonVersionStatus.UNSUPPORTED:
        decision = UpdateDecision.BLOCK
        reason = f"Target version {target_version} is UNSUPPORTED"
    elif target_status == PythonVersionStatus.DEPRECATED:
        decision = UpdateDecision.HOLD
        reason = f"Target version {target_version} is DEPRECATED - requires human approval"
    elif target_status == PythonVersionStatus.FUTURE:
        decision = UpdateDecision.SIMULATE_ONLY
        reason = f"Target version {target_version} is FUTURE - simulation only"
    else:
        decision = UpdateDecision.ALLOW
        reason = f"Target version {target_version} is SUPPORTED"
    
    return PythonVersionCheck(
        check_id=f"PYC-{uuid.uuid4().hex[:16].upper()}",
        current_version=current,
        target_version=target_version,
        status=target_status,
        decision=decision,
        reason=reason,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ============================================================
# DEPENDENCY STABILITY GOVERNANCE
# ============================================================

def create_dependency_hash(packages: Dict[str, str]) -> DependencyHash:
    """Create a hash of the dependency set."""
    # Sort packages for deterministic hashing
    sorted_items = sorted(packages.items())
    combined = "|".join(f"{k}={v}" for k, v in sorted_items)
    hash_value = hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    return DependencyHash(
        hash_id=f"DEP-{uuid.uuid4().hex[:16].upper()}",
        package_count=len(packages),
        combined_hash=hash_value,
        timestamp=datetime.now(UTC).isoformat(),
    )


def check_dependency_stability(
    current_packages: Dict[str, str],
    target_packages: Dict[str, str],
) -> DependencyCheck:
    """
    Check dependency stability between versions.
    
    Detects breaking changes and recommends decision.
    """
    current_hash = create_dependency_hash(current_packages)
    target_hash = create_dependency_hash(target_packages)
    
    # Detect changes
    breaking = []
    
    for pkg, current_ver in current_packages.items():
        if pkg not in target_packages:
            breaking.append(f"{pkg}: REMOVED")
        else:
            target_ver = target_packages[pkg]
            # Major version change = breaking
            try:
                current_major = int(current_ver.split(".")[0])
                target_major = int(target_ver.split(".")[0])
                if target_major != current_major:
                    breaking.append(f"{pkg}: {current_ver} -> {target_ver} (major change)")
            except (ValueError, IndexError):
                pass
    
    # New packages are not breaking
    
    if len(breaking) == 0:
        if current_hash.combined_hash == target_hash.combined_hash:
            status = DependencyStatus.STABLE
            decision = UpdateDecision.ALLOW
            reason = "No dependency changes"
        else:
            status = DependencyStatus.MINOR_CHANGE
            decision = UpdateDecision.ALLOW
            reason = "Minor dependency changes detected"
    else:
        status = DependencyStatus.BREAKING_CHANGE
        decision = UpdateDecision.SIMULATE_ONLY
        reason = f"Breaking changes: {', '.join(breaking)}"
    
    return DependencyCheck(
        check_id=f"DSC-{uuid.uuid4().hex[:16].upper()}",
        current_hash=current_hash,
        target_hash=target_hash,
        status=status,
        breaking_packages=tuple(breaking),
        decision=decision,
        reason=reason,
    )


# ============================================================
# UPDATE POLICY GOVERNANCE
# ============================================================

def create_update_policy() -> UpdatePolicy:
    """Create strict update policy (auto-update NEVER allowed)."""
    return UpdatePolicy(
        policy_id=f"POL-{uuid.uuid4().hex[:16].upper()}",
        require_signed=True,
        require_compatible=True,
        require_tested=True,
        require_approved=True,
        auto_update_allowed=False,  # NEVER
    )


def check_update_policy(
    policy: UpdatePolicy,
    is_signed: bool,
    is_compatible: bool,
    is_tested: bool,
    is_approved: bool,
) -> UpdateCheck:
    """
    Check if update meets policy requirements.
    
    Auto-update is NEVER forced.
    """
    missing = []
    
    if policy.require_signed and not is_signed:
        missing.append("SIGNATURE")
    if policy.require_compatible and not is_compatible:
        missing.append("COMPATIBILITY")
    if policy.require_tested and not is_tested:
        missing.append("TESTING")
    if policy.require_approved and not is_approved:
        missing.append("APPROVAL")
    
    if len(missing) == 0:
        decision = UpdateDecision.ALLOW
        reason = "All policy requirements met"
    elif "APPROVAL" in missing and len(missing) == 1:
        decision = UpdateDecision.HOLD
        reason = "Waiting for human approval"
    else:
        decision = UpdateDecision.BLOCK
        reason = f"Missing: {', '.join(missing)}"
    
    return UpdateCheck(
        check_id=f"UPC-{uuid.uuid4().hex[:16].upper()}",
        is_signed=is_signed,
        is_compatible=is_compatible,
        is_tested=is_tested,
        is_approved=is_approved,
        decision=decision,
        missing_requirements=tuple(missing),
        reason=reason,
    )


# ============================================================
# SELF-STABILITY CHECKS
# ============================================================

def check_governor_health(
    governor_name: str,
    guard_returns_false: bool,
    has_tests: bool,
    tests_pass: bool,
) -> GovernorHealth:
    """Check health of a single governor."""
    anomalies = []
    
    if not guard_returns_false:
        anomalies.append("GUARD_NOT_BLOCKING")
    if not has_tests:
        anomalies.append("NO_TESTS")
    if not tests_pass:
        anomalies.append("TESTS_FAILING")
    
    if len(anomalies) == 0:
        status = HealthStatus.HEALTHY
    elif "GUARD_NOT_BLOCKING" in anomalies:
        status = HealthStatus.CRITICAL
    else:
        status = HealthStatus.DEGRADED
    
    return GovernorHealth(
        governor_id=f"GOV-{uuid.uuid4().hex[:8].upper()}",
        governor_name=governor_name,
        status=status,
        last_check=datetime.now(UTC).isoformat(),
        anomalies=tuple(anomalies),
    )


def check_system_health(
    governor_healths: List[GovernorHealth],
    config_hash: str,
    code_hash: str,
    previous_test_count: int,
    current_test_count: int,
) -> SystemHealthCheck:
    """
    Check overall system health.
    
    Any anomaly → SAFE_MODE recommendation.
    """
    healthy = sum(1 for g in governor_healths if g.status == HealthStatus.HEALTHY)
    degraded = sum(1 for g in governor_healths if g.status == HealthStatus.DEGRADED)
    critical = sum(1 for g in governor_healths if g.status == HealthStatus.CRITICAL)
    
    drift_detected = config_hash != code_hash
    test_regression = current_test_count < previous_test_count
    
    if critical > 0:
        overall = HealthStatus.CRITICAL
        mode = SystemMode.SAFE_MODE
    elif degraded > 0 or drift_detected or test_regression:
        overall = HealthStatus.DEGRADED
        mode = SystemMode.SAFE_MODE
    else:
        overall = HealthStatus.HEALTHY
        mode = SystemMode.NORMAL
    
    return SystemHealthCheck(
        check_id=f"SHC-{uuid.uuid4().hex[:16].upper()}",
        governors_checked=len(governor_healths),
        healthy_count=healthy,
        degraded_count=degraded,
        critical_count=critical,
        overall_status=overall,
        recommended_mode=mode,
        drift_detected=drift_detected,
        test_regression_detected=test_regression,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ============================================================
# ROLLBACK GOVERNANCE
# ============================================================

def check_rollback_availability(
    has_backup: bool,
    backup_version: Optional[str],
    integrity_hash: Optional[str],
    expected_hash: Optional[str],
) -> RollbackCheck:
    """
    Check if rollback is available and safe.
    
    Rollback ALWAYS requires human confirmation.
    """
    if not has_backup:
        return RollbackCheck(
            check_id=f"RBC-{uuid.uuid4().hex[:16].upper()}",
            rollback_available=False,
            integrity_verified=False,
            previous_version=None,
            decision=RollbackDecision.UNAVAILABLE,
            requires_human=True,
            reason="No backup available",
        )
    
    integrity_ok = integrity_hash == expected_hash if (integrity_hash and expected_hash) else False
    
    if not integrity_ok:
        return RollbackCheck(
            check_id=f"RBC-{uuid.uuid4().hex[:16].upper()}",
            rollback_available=True,
            integrity_verified=False,
            previous_version=backup_version,
            decision=RollbackDecision.UNAVAILABLE,
            requires_human=True,
            reason="Backup integrity verification failed",
        )
    
    return RollbackCheck(
        check_id=f"RBC-{uuid.uuid4().hex[:16].upper()}",
        rollback_available=True,
        integrity_verified=True,
        previous_version=backup_version,
        decision=RollbackDecision.REQUIRES_CONFIRMATION,
        requires_human=True,
        reason="Rollback available - requires human confirmation",
    )


# ============================================================
# CRITICAL SECURITY GUARDS
# ============================================================

def can_evolution_governor_execute() -> Tuple[bool, str]:
    """
    Check if evolution governor can execute.
    
    ALWAYS returns (False, reason).
    """
    return False, "Evolution governor is DECISION ONLY - no execution authority"


def can_evolution_governor_modify() -> Tuple[bool, str]:
    """
    Check if evolution governor can modify system state.
    
    ALWAYS returns (False, reason).
    """
    return False, "Evolution governor cannot modify system state - read-only"


def can_evolution_governor_approve() -> Tuple[bool, str]:
    """
    Check if evolution governor can approve execution.
    
    ALWAYS returns (False, reason).
    """
    return False, "Evolution governor cannot approve execution - human decision required"
