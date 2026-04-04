from impl_v1.phase36.phase36_context import SandboxBoundaryInterface
from impl_v1.phase36.phase36_engine import evaluate_sandbox_boundary
from impl_v1.phase36.phase36_types import SandboxBoundaryType, SandboxCapability, SandboxDecision


def test_phase36_engine_denies_and_escalates_expected_cases():
    assert evaluate_sandbox_boundary(
        SandboxBoundaryInterface("", SandboxBoundaryType.PROCESS, frozenset({SandboxCapability.READ_ONLY}), 1)
    ).reason == "empty boundary_id"
    assert evaluate_sandbox_boundary(
        SandboxBoundaryInterface("id", SandboxBoundaryType.UNKNOWN, frozenset({SandboxCapability.READ_ONLY}), 1)
    ).decision is SandboxDecision.DENY
    assert evaluate_sandbox_boundary(
        SandboxBoundaryInterface("id", SandboxBoundaryType.PROCESS, frozenset({SandboxCapability.EXEC_ALLOWED}), 1)
    ).decision is SandboxDecision.ESCALATE
    assert evaluate_sandbox_boundary(
        SandboxBoundaryInterface("id", SandboxBoundaryType.PROCESS, frozenset({SandboxCapability.READ_ONLY}), 8)
    ).reason == "threat_level 8 exceeds maximum"
    assert evaluate_sandbox_boundary(
        SandboxBoundaryInterface("id", SandboxBoundaryType.CONTAINER, frozenset({SandboxCapability.WRITE_ALLOWED}), 5)
    ).reason == "write capability with elevated threat"
    assert evaluate_sandbox_boundary(
        SandboxBoundaryInterface("id", SandboxBoundaryType.VM, frozenset(), 2)
    ).reason == "no capabilities defined"
    default_result = evaluate_sandbox_boundary(
        SandboxBoundaryInterface("id", SandboxBoundaryType.PROCESS, frozenset({SandboxCapability.READ_ONLY}), 2)
    )
    assert default_result.decision is SandboxDecision.DENY
    assert default_result.reason == "deny by default"
    assert 0.0 <= default_result.threat_score < 1.0
