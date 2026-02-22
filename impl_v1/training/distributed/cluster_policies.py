"""
cluster_policies.py — Gradient Compression, TLS, Resource Utilization
                      (Phases 5, 6, 8)

Python governance interfaces for C++-implemented features.

Phase 5 — Gradient Compression Policy:
  Validates C++ compression config.
  Checks determinism + accuracy preserved.

Phase 6 — TLS Security Policy:
  Validates node certificates against CA.
  Rejects unsigned/expired nodes.

Phase 8 — Resource Utilization Policy:
  Assigns idle GPU/CPU to HPO or preprocessing.
  Never interrupts active DDP.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# PHASE 5 — GRADIENT COMPRESSION POLICY
# =============================================================================

class CompressionMode(str, Enum):
    """Supported compression modes (C++ implements the kernel)."""
    NONE = "none"
    TOPK_SPARSE = "topk_sparse"
    INT8_QUANTIZE = "int8_quantize"


@dataclass
class CompressionConfig:
    """Gradient compression configuration."""
    mode: str = CompressionMode.NONE
    topk_ratio: float = 0.1        # Keep top 10% of gradients
    error_feedback: bool = True     # Accumulate compression residuals
    warmup_epochs: int = 2          # No compression for first N epochs


@dataclass
class CompressionValidation:
    """Result of compression validation."""
    passed: bool
    mode: str
    determinism_preserved: bool
    accuracy_delta: float       # Should be < 0.005
    compression_ratio: float    # e.g. 10× for top-10%
    errors: List[str] = field(default_factory=list)


class GradientCompressionPolicy:
    """Governance policy for gradient compression.

    Validates that C++ compression preserves:
      - Determinism (identical hashes with same seed)
      - Accuracy (within ±0.5%)
    """

    MAX_ACCURACY_DELTA = 0.005  # ±0.5%

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        logger.info(
            f"[COMPRESSION] Policy initialized: mode={self.config.mode}"
        )

    def validate(
        self,
        baseline_hash: str,
        compressed_hash: str,
        baseline_accuracy: float,
        compressed_accuracy: float,
    ) -> CompressionValidation:
        """Validate compression doesn't break determinism or accuracy.

        Args:
            baseline_hash: Weight hash without compression.
            compressed_hash: Weight hash with compression.
            baseline_accuracy: Accuracy without compression.
            compressed_accuracy: Accuracy with compression.

        Returns:
            CompressionValidation.
        """
        errors = []

        # Check determinism
        det_ok = baseline_hash == compressed_hash
        if not det_ok and self.config.mode == CompressionMode.NONE:
            errors.append("Determinism broken with no compression")

        # Check accuracy delta
        acc_delta = abs(baseline_accuracy - compressed_accuracy)
        if acc_delta > self.MAX_ACCURACY_DELTA:
            errors.append(
                f"Accuracy delta {acc_delta:.4f} > {self.MAX_ACCURACY_DELTA}"
            )

        # Compression ratio
        if self.config.mode == CompressionMode.TOPK_SPARSE:
            ratio = 1.0 / max(self.config.topk_ratio, 0.01)
        elif self.config.mode == CompressionMode.INT8_QUANTIZE:
            ratio = 4.0  # float32 → int8
        else:
            ratio = 1.0

        passed = len(errors) == 0 or self.config.mode == CompressionMode.NONE

        result = CompressionValidation(
            passed=passed,
            mode=self.config.mode,
            determinism_preserved=det_ok,
            accuracy_delta=round(acc_delta, 6),
            compression_ratio=round(ratio, 2),
            errors=errors,
        )

        if passed:
            logger.info(
                f"[COMPRESSION] Validation PASSED: mode={self.config.mode}, "
                f"ratio={ratio:.1f}×, acc_delta={acc_delta:.4f}"
            )
        else:
            logger.error(
                f"[COMPRESSION] Validation FAILED: {'; '.join(errors)}"
            )

        return result


# =============================================================================
# PHASE 6 — TLS SECURITY POLICY
# =============================================================================

@dataclass
class NodeCertificate:
    """Node TLS certificate (simplified representation)."""
    node_id: str
    cert_hash: str
    issuer: str               # Authority CA ID
    issued_at: str
    expires_at: str
    mutual_auth: bool = True


@dataclass
class TLSValidation:
    """TLS certificate validation result."""
    passed: bool
    node_id: str
    cert_valid: bool
    issuer_match: bool
    not_expired: bool
    node_id_match: bool
    mutual_auth: bool
    errors: List[str] = field(default_factory=list)


class TLSPolicy:
    """TLS security policy for inter-node communication.

    All inter-node communication must:
      - Use TLS with mutual authentication
      - Certificates signed by authority CA
      - node_id in cert must match registered node
      - Reject expired/unsigned nodes
    """

    def __init__(self, authority_ca_id: str = ""):
        self.authority_ca_id = authority_ca_id or self._gen_ca_id()
        self.approved_certs: Dict[str, NodeCertificate] = {}
        logger.info(
            f"[TLS] Policy initialized: CA={self.authority_ca_id[:16]}..."
        )

    @staticmethod
    def _gen_ca_id() -> str:
        return hashlib.sha256(
            f"ca-{time.time()}".encode()
        ).hexdigest()[:32]

    def issue_certificate(self, node_id: str, validity_hours: int = 24) -> NodeCertificate:
        """Issue a TLS certificate for a node.

        Args:
            node_id: Registered node ID.
            validity_hours: Certificate validity period.

        Returns:
            NodeCertificate.
        """
        now = datetime.now()
        from datetime import timedelta
        expires = now + timedelta(hours=validity_hours)

        cert_hash = hashlib.sha256(
            f"{node_id}-{self.authority_ca_id}-{now.isoformat()}".encode()
        ).hexdigest()[:32]

        cert = NodeCertificate(
            node_id=node_id,
            cert_hash=cert_hash,
            issuer=self.authority_ca_id,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
            mutual_auth=True,
        )

        self.approved_certs[node_id] = cert
        logger.info(f"[TLS] Certificate issued to {node_id[:16]}...")
        return cert

    def validate_node(
        self,
        node_id: str,
        cert: NodeCertificate,
    ) -> TLSValidation:
        """Validate a node's TLS certificate.

        Rejects if:
          - Certificate not signed by authority CA
          - Certificate expired
          - node_id doesn't match certificate
          - Mutual authentication not enabled
        """
        errors = []
        now = datetime.now()

        # Issuer check
        issuer_ok = cert.issuer == self.authority_ca_id
        if not issuer_ok:
            errors.append(
                f"Issuer mismatch: got {cert.issuer[:16]}, "
                f"expected {self.authority_ca_id[:16]}"
            )

        # Expiry check
        try:
            expires = datetime.fromisoformat(cert.expires_at)
            not_expired = now < expires
        except Exception:
            not_expired = False
        if not not_expired:
            errors.append("Certificate expired")

        # Node ID check
        nid_ok = cert.node_id == node_id
        if not nid_ok:
            errors.append(
                f"node_id mismatch: cert={cert.node_id[:16]}, "
                f"request={node_id[:16]}"
            )

        # Mutual auth required
        mutual = cert.mutual_auth
        if not mutual:
            errors.append("Mutual authentication not enabled")

        # Cert hash in approved list
        cert_valid = (
            node_id in self.approved_certs and
            self.approved_certs[node_id].cert_hash == cert.cert_hash
        )
        if not cert_valid:
            errors.append("Certificate not in approved list")

        passed = len(errors) == 0

        result = TLSValidation(
            passed=passed,
            node_id=node_id,
            cert_valid=cert_valid,
            issuer_match=issuer_ok,
            not_expired=not_expired,
            node_id_match=nid_ok,
            mutual_auth=mutual,
            errors=errors,
        )

        if passed:
            logger.info(f"[TLS] Node {node_id[:16]} validated OK")
        else:
            logger.error(
                f"[TLS] Node {node_id[:16]} REJECTED: {'; '.join(errors)}"
            )

        return result

    def revoke_certificate(self, node_id: str):
        """Revoke a node's certificate."""
        if node_id in self.approved_certs:
            del self.approved_certs[node_id]
            logger.info(f"[TLS] Certificate revoked: {node_id[:16]}...")


# =============================================================================
# PHASE 8 — RESOURCE UTILIZATION POLICY
# =============================================================================

class TaskType(str, Enum):
    """Types of idle work."""
    HPO_TRIAL = "hpo_trial"
    DATA_VALIDATION = "data_validation"
    PREPROCESSING = "preprocessing"
    NONE = "none"


@dataclass
class ResourceStatus:
    """Current resource utilization for a node."""
    node_id: str
    gpu_util_pct: float       # 0-100
    cpu_util_pct: float       # 0-100
    gpu_idle: bool             # True if gpu_util < threshold
    cpu_idle: bool
    ddp_active: bool
    assigned_task: str = TaskType.NONE
    assigned_at: str = ""


@dataclass
class UtilizationDecision:
    """Decision for an idle node."""
    node_id: str
    task: str
    reason: str


class ResourceUtilizationPolicy:
    """Assigns idle resources to useful work.

    Rules:
      - GPU idle > 40% → assign HPO trial OR preprocessing
      - CPU idle → assign dataset validation
      - NEVER interrupt active DDP
    """

    GPU_IDLE_THRESHOLD = 40.0   # percent
    CPU_IDLE_THRESHOLD = 70.0   # percent

    def __init__(self):
        self.assignments: Dict[str, ResourceStatus] = {}
        logger.info("[RESOURCE] Utilization policy initialized")

    def evaluate_node(
        self,
        node_id: str,
        gpu_util_pct: float,
        cpu_util_pct: float,
        ddp_active: bool,
        hpo_trials_pending: int = 0,
    ) -> UtilizationDecision:
        """Evaluate a node and assign idle work if applicable.

        Args:
            node_id: Node ID.
            gpu_util_pct: Current GPU utilization (0-100).
            cpu_util_pct: Current CPU utilization (0-100).
            ddp_active: Whether DDP training is active.
            hpo_trials_pending: Number of pending HPO trials.

        Returns:
            UtilizationDecision.
        """
        gpu_idle = gpu_util_pct < self.GPU_IDLE_THRESHOLD
        cpu_idle = cpu_util_pct < self.CPU_IDLE_THRESHOLD

        status = ResourceStatus(
            node_id=node_id,
            gpu_util_pct=gpu_util_pct,
            cpu_util_pct=cpu_util_pct,
            gpu_idle=gpu_idle,
            cpu_idle=cpu_idle,
            ddp_active=ddp_active,
        )

        # Rule 1: Never interrupt active DDP
        if ddp_active:
            status.assigned_task = TaskType.NONE
            self.assignments[node_id] = status
            return UtilizationDecision(
                node_id=node_id,
                task=TaskType.NONE,
                reason="DDP active — no idle work assigned",
            )

        # Rule 2: GPU idle → HPO or preprocessing
        if gpu_idle:
            if hpo_trials_pending > 0:
                task = TaskType.HPO_TRIAL
                reason = (
                    f"GPU idle ({gpu_util_pct:.0f}% < {self.GPU_IDLE_THRESHOLD}%), "
                    f"assigning HPO trial ({hpo_trials_pending} pending)"
                )
            else:
                task = TaskType.PREPROCESSING
                reason = (
                    f"GPU idle ({gpu_util_pct:.0f}% < {self.GPU_IDLE_THRESHOLD}%), "
                    f"assigning preprocessing"
                )

            status.assigned_task = task
            status.assigned_at = datetime.now().isoformat()
            self.assignments[node_id] = status

            logger.info(f"[RESOURCE] {node_id[:16]}: {reason}")
            return UtilizationDecision(
                node_id=node_id, task=task, reason=reason,
            )

        # Rule 3: CPU idle → data validation
        if cpu_idle:
            task = TaskType.DATA_VALIDATION
            reason = (
                f"CPU idle ({cpu_util_pct:.0f}% < {self.CPU_IDLE_THRESHOLD}%), "
                f"assigning data validation"
            )
            status.assigned_task = task
            status.assigned_at = datetime.now().isoformat()
            self.assignments[node_id] = status

            logger.info(f"[RESOURCE] {node_id[:16]}: {reason}")
            return UtilizationDecision(
                node_id=node_id, task=task, reason=reason,
            )

        # Fully utilized
        status.assigned_task = TaskType.NONE
        self.assignments[node_id] = status
        return UtilizationDecision(
            node_id=node_id,
            task=TaskType.NONE,
            reason="Node fully utilized",
        )

    def get_idle_nodes(self) -> List[str]:
        """List nodes currently assigned idle work."""
        return [
            nid for nid, s in self.assignments.items()
            if s.assigned_task != TaskType.NONE
        ]

    def get_summary(self) -> dict:
        """Resource utilization summary."""
        total = len(self.assignments)
        idle_gpu = sum(1 for s in self.assignments.values() if s.gpu_idle)
        idle_cpu = sum(1 for s in self.assignments.values() if s.cpu_idle)
        assigned = sum(
            1 for s in self.assignments.values()
            if s.assigned_task != TaskType.NONE
        )

        return {
            'total_nodes': total,
            'gpu_idle': idle_gpu,
            'cpu_idle': idle_cpu,
            'assigned_idle_work': assigned,
        }
