"""impl_v1 Phase-36 Native Sandbox Boundary context."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from .phase36_types import SandboxBoundaryType, SandboxCapability, SandboxDecision

logger = logging.getLogger("impl_v1.phase36.context")


def _log_module_sha256(module_file: str) -> str:
    digest = hashlib.sha256(Path(module_file).read_bytes()).hexdigest()
    logger.info("module_sha256", extra={"event": "module_sha256", "module_name": __name__, "module_file": module_file, "sha256": digest})
    return digest


@dataclass(frozen=True)
class SandboxBoundaryInterface:
    boundary_id: str
    boundary_type: SandboxBoundaryType
    allowed_capabilities: frozenset[SandboxCapability]
    threat_level: int


@dataclass(frozen=True)
class SandboxEvaluationResult:
    decision: SandboxDecision
    reason: str
    threat_score: float


MODULE_SHA256 = _log_module_sha256(__file__)
