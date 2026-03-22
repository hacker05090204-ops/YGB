"""impl_v1 Phase-36 Native Sandbox Boundary types."""

from __future__ import annotations

import hashlib
import logging
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger("impl_v1.phase36.types")


def _log_module_sha256(module_file: str) -> str:
    digest = hashlib.sha256(Path(module_file).read_bytes()).hexdigest()
    logger.info("module_sha256", extra={"event": "module_sha256", "module_name": __name__, "module_file": module_file, "sha256": digest})
    return digest


class SandboxBoundaryType(Enum):
    PROCESS = auto()
    CONTAINER = auto()
    VM = auto()
    UNKNOWN = auto()


class SandboxCapability(Enum):
    READ_ONLY = auto()
    WRITE_ALLOWED = auto()
    EXEC_ALLOWED = auto()
    NONE = auto()


class SandboxDecision(Enum):
    ALLOW = auto()
    DENY = auto()
    ESCALATE = auto()


MODULE_SHA256 = _log_module_sha256(__file__)
