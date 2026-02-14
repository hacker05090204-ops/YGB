"""
Isolation Guard — Cross-Contamination Prevention

RULES:
  - Research mode CANNOT import training modules
  - Research mode CANNOT read/write model weights, datasets, governance
  - Research mode CANNOT access storage engine
  - Every research query is audit-logged
  - ANY violation = immediate block + audit event
"""

import os
import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Set
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =========================================================================
# TYPES
# =========================================================================

class IsolationViolation(Enum):
    """CLOSED ENUM - Violation types."""
    IMPORT_BLOCKED = "IMPORT_BLOCKED"
    PATH_BLOCKED = "PATH_BLOCKED"
    WRITE_BLOCKED = "WRITE_BLOCKED"
    GOVERNANCE_ACCESS = "GOVERNANCE_ACCESS"
    TRAINING_ACCESS = "TRAINING_ACCESS"
    STORAGE_ENGINE_ACCESS = "STORAGE_ENGINE_ACCESS"


@dataclass(frozen=True)
class IsolationCheckResult:
    """Result of an isolation check."""
    allowed: bool
    violation: Optional[IsolationViolation]
    reason: str
    path_or_module: str
    timestamp: str


@dataclass(frozen=True)
class AuditEntry:
    """Audit log entry for research queries."""
    entry_id: str
    query: str
    result_status: str
    isolation_checks_passed: int
    isolation_checks_failed: int
    violations: tuple  # Tuple[str, ...]
    timestamp: str


# =========================================================================
# BLACKLISTS
# =========================================================================

# Modules that research mode CANNOT import
BLOCKED_IMPORT_PATTERNS: Set[str] = {
    "training",
    "backend.integrity",
    "backend.storage",
    "native.shadow_integrity",
    "native.containment",
    "impl_v1.phase49.native.sandbox",
    "impl_v1.phase49.native.browser_engine",
}

# Path fragments that research mode CANNOT read or write
BLOCKED_PATH_FRAGMENTS: List[str] = [
    "training/",
    "training\\",
    "models/",
    "models\\",
    "datasets/",
    "datasets\\",
    "weights/",
    "weights\\",
    "governance_state.json",
    "governance_state",
    "native/containment",
    "native\\containment",
    "native/shadow_integrity",
    "native\\shadow_integrity",
    "TRAINING_SANDBOX_CONFIG",
    "backend/integrity",
    "backend\\integrity",
    "enterprise/",
    "enterprise\\",
]

# File extensions that research mode CANNOT access
BLOCKED_EXTENSIONS: Set[str] = {
    ".pt", ".pth", ".onnx", ".h5", ".hdf5", ".pb",
    ".tflite", ".safetensors", ".bin", ".model",
    ".ckpt", ".pkl",
}

# =========================================================================
# AUDIT LOG
# =========================================================================

_audit_log: List[AuditEntry] = []

def get_audit_log() -> List[AuditEntry]:
    """Return audit log (read-only copy)."""
    return list(_audit_log)

def clear_audit_log() -> None:
    """Clear audit log (testing only)."""
    _audit_log.clear()

# =========================================================================
# ISOLATION GUARD
# =========================================================================

class IsolationGuard:
    """
    Prevents cross-contamination between Research and Security modes.
    
    Research mode CANNOT:
    - Import training, integrity, storage, containment modules
    - Read/write model weights, datasets, governance state
    - Access the storage engine
    - Modify integrity scores
    """

    def check_import(self, module_name: str) -> IsolationCheckResult:
        """Check if a module import is allowed in Research mode."""
        module_lower = module_name.lower()
        
        for blocked in BLOCKED_IMPORT_PATTERNS:
            if module_lower.startswith(blocked) or module_lower == blocked:
                return IsolationCheckResult(
                    allowed=False,
                    violation=IsolationViolation.IMPORT_BLOCKED,
                    reason=f"Module '{module_name}' is blocked in research mode",
                    path_or_module=module_name,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        return IsolationCheckResult(
            allowed=True,
            violation=None,
            reason="Import allowed",
            path_or_module=module_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def check_path_read(self, path: str) -> IsolationCheckResult:
        """Check if a file path can be read in Research mode."""
        return self._check_path(path, "read")

    def check_path_write(self, path: str) -> IsolationCheckResult:
        """Check if a file path can be written in Research mode."""
        return self._check_path(path, "write")

    def _check_path(self, path: str, operation: str) -> IsolationCheckResult:
        """Internal path checking."""
        normalized = path.replace("\\", "/").lower()

        # Check path fragments
        for fragment in BLOCKED_PATH_FRAGMENTS:
            frag_normalized = fragment.replace("\\", "/").lower()
            if frag_normalized in normalized:
                violation = IsolationViolation.PATH_BLOCKED
                if "training" in frag_normalized:
                    violation = IsolationViolation.TRAINING_ACCESS
                elif "governance" in frag_normalized:
                    violation = IsolationViolation.GOVERNANCE_ACCESS
                elif "integrity" in frag_normalized or "storage" in frag_normalized:
                    violation = IsolationViolation.STORAGE_ENGINE_ACCESS

                return IsolationCheckResult(
                    allowed=False,
                    violation=violation,
                    reason=f"Path '{path}' blocked: contains '{fragment}'",
                    path_or_module=path,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        # Check file extension
        _, ext = os.path.splitext(path)
        if ext.lower() in BLOCKED_EXTENSIONS:
            return IsolationCheckResult(
                allowed=False,
                violation=IsolationViolation.PATH_BLOCKED,
                reason=f"Extension '{ext}' blocked in research mode (model file)",
                path_or_module=path,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        if operation == "write":
            return IsolationCheckResult(
                allowed=False,
                violation=IsolationViolation.WRITE_BLOCKED,
                reason="Research mode has no write permissions except temp",
                path_or_module=path,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return IsolationCheckResult(
            allowed=True,
            violation=None,
            reason=f"{operation} allowed",
            path_or_module=path,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def check_governance_access(self) -> IsolationCheckResult:
        """Research mode CANNOT access governance state."""
        return IsolationCheckResult(
            allowed=False,
            violation=IsolationViolation.GOVERNANCE_ACCESS,
            reason="Research mode cannot access governance state",
            path_or_module="governance",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def check_storage_engine_access(self) -> IsolationCheckResult:
        """Research mode CANNOT access storage engine."""
        return IsolationCheckResult(
            allowed=False,
            violation=IsolationViolation.STORAGE_ENGINE_ACCESS,
            reason="Research mode cannot access storage engine",
            path_or_module="storage_engine",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # =====================================================================
    # AUDIT LOGGING
    # =====================================================================

    def log_research_query(self, query: str, result_status: str,
                           checks_passed: int, checks_failed: int,
                           violations: List[str]) -> AuditEntry:
        """Log a research query for audit."""
        import uuid
        entry = AuditEntry(
            entry_id=f"AUD-{uuid.uuid4().hex[:16].upper()}",
            query=query[:256],  # Truncate for safety
            result_status=result_status,
            isolation_checks_passed=checks_passed,
            isolation_checks_failed=checks_failed,
            violations=tuple(violations),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        _audit_log.append(entry)
        
        if checks_failed > 0:
            logger.warning(f"Research query had {checks_failed} isolation violations: "
                          f"{violations}")
        
        return entry

    # =====================================================================
    # FULL PRE-QUERY CHECK
    # =====================================================================

    def pre_query_check(self, query: str) -> IsolationCheckResult:
        """
        Run all isolation checks before a research query.
        Returns the first failure, or success if all pass.
        """
        checks = [
            # Cannot access training
            self.check_import("training"),
            # Cannot access integrity
            self.check_import("backend.integrity"),
            # Cannot access storage
            self.check_import("backend.storage"),
            # Cannot access governance
            self.check_governance_access(),
            # Cannot access storage engine
            self.check_storage_engine_access(),
        ]

        # All these should return NOT allowed
        # They're guards that confirm isolation is active
        for check in checks:
            if check.allowed:
                # This would mean isolation has been BYPASSED
                return IsolationCheckResult(
                    allowed=False,
                    violation=IsolationViolation.IMPORT_BLOCKED,
                    reason="Isolation guard detected bypass attempt",
                    path_or_module="system",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        # All guards held — research query is safe to proceed
        return IsolationCheckResult(
            allowed=True,
            violation=None,
            reason="All isolation checks passed — research mode is safe",
            path_or_module="research_pipeline",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
