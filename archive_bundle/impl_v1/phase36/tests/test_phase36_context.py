import dataclasses

import pytest

from impl_v1.phase36.phase36_context import SandboxBoundaryInterface, SandboxEvaluationResult
from impl_v1.phase36.phase36_types import SandboxBoundaryType, SandboxCapability, SandboxDecision


def test_phase36_context_is_frozen():
    interface = SandboxBoundaryInterface(
        boundary_id="sandbox-1",
        boundary_type=SandboxBoundaryType.PROCESS,
        allowed_capabilities=frozenset({SandboxCapability.READ_ONLY}),
        threat_level=3,
    )
    result = SandboxEvaluationResult(
        decision=SandboxDecision.DENY,
        reason="deny by default",
        threat_score=0.3,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        interface.boundary_id = "mutated"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "changed"
