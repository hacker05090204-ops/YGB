# G11: Execution Seal
"""
FINAL gate before EXECUTING state.

ALL governors must PASS.
ONE failure = STOP.

This is the last checkpoint before any real execution.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import uuid
from datetime import datetime, UTC


class SealCheckType(Enum):
    """CLOSED ENUM - 11 checks (one per governor)"""
    G01_EXECUTION_STATE = "G01_EXECUTION_STATE"
    G02_BROWSER_TYPES = "G02_BROWSER_TYPES"
    G03_BROWSER_SAFETY = "G03_BROWSER_SAFETY"
    G04_VOICE_READY = "G04_VOICE_READY"
    G05_ASSISTANT_APPROVED = "G05_ASSISTANT_APPROVED"
    G06_AUTONOMY_MODE = "G06_AUTONOMY_MODE"
    G07_CVE_LOADED = "G07_CVE_LOADED"
    G08_LICENSE_VALID = "G08_LICENSE_VALID"
    G09_DEVICE_TRUSTED = "G09_DEVICE_TRUSTED"
    G10_NO_CRITICAL_ALERTS = "G10_NO_CRITICAL_ALERTS"
    G11_FINAL_SEAL = "G11_FINAL_SEAL"


class SealCheckResult(Enum):
    """CLOSED ENUM - 3 results"""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class SealCheckEntry:
    """Single seal check result."""
    check_type: SealCheckType
    result: SealCheckResult
    reason: str
    timestamp: str


@dataclass(frozen=True)
class ExecutionSealResult:
    """Final execution seal result."""
    seal_id: str
    sealed: bool
    all_passed: bool
    checks: tuple  # Tuple[SealCheckEntry, ...]
    failed_checks: tuple  # Tuple[SealCheckType, ...]
    block_reason: Optional[str]
    timestamp: str


def create_check(
    check_type: SealCheckType,
    passed: bool,
    reason: str = "",
) -> SealCheckEntry:
    """Create a seal check entry."""
    return SealCheckEntry(
        check_type=check_type,
        result=SealCheckResult.PASS if passed else SealCheckResult.FAIL,
        reason=reason,
        timestamp=datetime.now(UTC).isoformat(),
    )


def seal_execution_intent(
    execution_state_valid: bool,
    browser_types_valid: bool,
    browser_safety_passed: bool,
    voice_ready: bool,
    assistant_approved: bool,
    autonomy_mode_valid: bool,
    cve_loaded: bool,
    license_valid: bool,
    device_trusted: bool,
    no_critical_alerts: bool,
    human_confirmed: bool = False,
) -> ExecutionSealResult:
    """
    Create final execution seal.
    
    ALL checks must pass for seal to be valid.
    """
    checks = [
        create_check(SealCheckType.G01_EXECUTION_STATE, execution_state_valid,
                     "Execution state valid" if execution_state_valid else "Invalid execution state"),
        create_check(SealCheckType.G02_BROWSER_TYPES, browser_types_valid,
                     "Browser types valid" if browser_types_valid else "Invalid browser config"),
        create_check(SealCheckType.G03_BROWSER_SAFETY, browser_safety_passed,
                     "Browser safety passed" if browser_safety_passed else "Browser safety failed"),
        create_check(SealCheckType.G04_VOICE_READY, voice_ready,
                     "Voice system ready" if voice_ready else "Voice not initialized"),
        create_check(SealCheckType.G05_ASSISTANT_APPROVED, assistant_approved,
                     "Assistant approved" if assistant_approved else "Assistant not approved"),
        create_check(SealCheckType.G06_AUTONOMY_MODE, autonomy_mode_valid,
                     "Autonomy mode valid" if autonomy_mode_valid else "Invalid autonomy mode"),
        create_check(SealCheckType.G07_CVE_LOADED, cve_loaded,
                     "CVE data loaded" if cve_loaded else "CVE data not available"),
        create_check(SealCheckType.G08_LICENSE_VALID, license_valid,
                     "License valid" if license_valid else "License invalid"),
        create_check(SealCheckType.G09_DEVICE_TRUSTED, device_trusted,
                     "Device trusted" if device_trusted else "Device not trusted"),
        create_check(SealCheckType.G10_NO_CRITICAL_ALERTS, no_critical_alerts,
                     "No critical alerts" if no_critical_alerts else "Critical alerts pending"),
        create_check(SealCheckType.G11_FINAL_SEAL, human_confirmed,
                     "Human confirmed" if human_confirmed else "Awaiting human confirmation"),
    ]
    
    # Find failures
    failed = [c.check_type for c in checks if c.result == SealCheckResult.FAIL]
    all_passed = len(failed) == 0
    
    # Build block reason
    block_reason = None
    if not all_passed:
        reasons = [c.reason for c in checks if c.result == SealCheckResult.FAIL]
        block_reason = "; ".join(reasons[:3])  # Limit to first 3 reasons
    
    return ExecutionSealResult(
        seal_id=f"SEAL-{uuid.uuid4().hex[:16].upper()}",
        sealed=all_passed,
        all_passed=all_passed,
        checks=tuple(checks),
        failed_checks=tuple(failed),
        block_reason=block_reason,
        timestamp=datetime.now(UTC).isoformat(),
    )


def validate_seal(seal: ExecutionSealResult) -> Tuple[bool, str]:
    """Validate an execution seal. Returns (valid, reason)."""
    if not seal.sealed:
        return False, seal.block_reason or "Seal not valid"
    
    if not seal.all_passed:
        failed_names = [f.value for f in seal.failed_checks[:3]]
        return False, f"Failed checks: {', '.join(failed_names)}"
    
    return True, "Seal valid - execution authorized"


def can_execute(seal: ExecutionSealResult) -> bool:
    """Simple check if execution is allowed."""
    return seal.sealed and seal.all_passed
