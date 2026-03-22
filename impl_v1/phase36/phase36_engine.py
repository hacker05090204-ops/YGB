"""impl_v1 Phase-36 Native Sandbox Boundary engine."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .phase36_context import SandboxBoundaryInterface, SandboxEvaluationResult
from .phase36_types import SandboxBoundaryType, SandboxCapability, SandboxDecision

logger = logging.getLogger("impl_v1.phase36.engine")


def _log_module_sha256(module_file: str) -> str:
    digest = hashlib.sha256(Path(module_file).read_bytes()).hexdigest()
    logger.info("module_sha256", extra={"event": "module_sha256", "module_name": __name__, "module_file": module_file, "sha256": digest})
    return digest


def _threat_score(threat_level: int) -> float:
    return min(max(float(threat_level) / 10.0, 0.0), 0.99)


def evaluate_sandbox_boundary(interface: SandboxBoundaryInterface) -> SandboxEvaluationResult:
    score = _threat_score(interface.threat_level)
    if not interface.boundary_id:
        return SandboxEvaluationResult(SandboxDecision.DENY, "empty boundary_id", score)
    if interface.boundary_type is SandboxBoundaryType.UNKNOWN:
        return SandboxEvaluationResult(SandboxDecision.DENY, "unknown boundary type", score)
    if SandboxCapability.EXEC_ALLOWED in interface.allowed_capabilities:
        return SandboxEvaluationResult(SandboxDecision.ESCALATE, "exec capability requires human", score)
    if interface.threat_level > 7:
        return SandboxEvaluationResult(
            SandboxDecision.DENY,
            f"threat_level {interface.threat_level} exceeds maximum",
            score,
        )
    if SandboxCapability.WRITE_ALLOWED in interface.allowed_capabilities and interface.threat_level > 4:
        return SandboxEvaluationResult(SandboxDecision.ESCALATE, "write capability with elevated threat", score)
    if not interface.allowed_capabilities:
        return SandboxEvaluationResult(SandboxDecision.DENY, "no capabilities defined", score)
    return SandboxEvaluationResult(SandboxDecision.DENY, "deny by default", score)


MODULE_SHA256 = _log_module_sha256(__file__)
