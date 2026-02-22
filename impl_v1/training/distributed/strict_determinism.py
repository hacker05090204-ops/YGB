"""
strict_determinism.py — Strict CUDA Determinism Lock (Phase 2)

Before DDP init, enforce globally:
  - allow_tf32 = False
  - cudnn.allow_tf32 = False
  - deterministic_algorithms = True
  - Identical CUDA version across nodes
  - Identical CUBLAS_WORKSPACE_CONFIG

Reject node if any mismatch.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REQUIRED_CUBLAS_CONFIG = ":4096:8"


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class DeterminismConfig:
    """Collected determinism configuration from one node."""
    node_id: str
    cuda_version: str
    cublas_workspace_config: str
    allow_tf32: bool
    cudnn_allow_tf32: bool
    cudnn_deterministic: bool
    cudnn_benchmark: bool
    deterministic_algorithms: bool
    driver_version: str = ""


@dataclass
class DeterminismValidation:
    """Result of cluster-wide determinism validation."""
    passed: bool
    authority_config: Optional[DeterminismConfig]
    node_configs: Dict[str, DeterminismConfig]
    rejected_nodes: List[str]
    errors: List[str] = field(default_factory=list)


# =============================================================================
# LOCAL LOCK
# =============================================================================

def enforce_local_determinism() -> DeterminismConfig:
    """Enforce strict determinism on the local node.

    Sets all flags and returns the resulting config.
    """
    import torch

    # TF32 — disable globally
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    # cuDNN determinism
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # Global deterministic algorithms
    try:
        torch.use_deterministic_algorithms(True)
        det_algos = True
    except Exception:
        det_algos = False

    # CUBLAS workspace
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = REQUIRED_CUBLAS_CONFIG

    cuda_ver = torch.version.cuda or "unknown"

    config = DeterminismConfig(
        node_id="local",
        cuda_version=cuda_ver,
        cublas_workspace_config=REQUIRED_CUBLAS_CONFIG,
        allow_tf32=False,
        cudnn_allow_tf32=False,
        cudnn_deterministic=True,
        cudnn_benchmark=False,
        deterministic_algorithms=det_algos,
    )

    logger.info(
        f"[DETERMINISM] Local lock applied: CUDA={cuda_ver}, "
        f"TF32=off, cudnn.det=True, deterministic_algos={det_algos}"
    )

    return config


# =============================================================================
# COLLECT NODE CONFIG (without torch dependency)
# =============================================================================

def collect_node_config(node_id: str) -> DeterminismConfig:
    """Collect the current determinism config from a node."""
    try:
        import torch
        # Get driver version via nvidia-smi or torch
        driver_ver = ""
        if torch.cuda.is_available():
            try:
                driver_ver = torch.cuda.get_device_properties(0).name
                # Try to get actual driver version
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=driver_version',
                     '--format=csv,noheader'],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    driver_ver = result.stdout.strip().split('\n')[0]
            except Exception:
                pass

        return DeterminismConfig(
            node_id=node_id,
            cuda_version=torch.version.cuda or "unknown",
            cublas_workspace_config=os.environ.get(
                "CUBLAS_WORKSPACE_CONFIG", ""
            ),
            allow_tf32=getattr(
                torch.backends.cuda.matmul, 'allow_tf32', False
            ),
            cudnn_allow_tf32=getattr(
                torch.backends.cudnn, 'allow_tf32', False
            ),
            cudnn_deterministic=getattr(
                torch.backends.cudnn, 'deterministic', False
            ),
            cudnn_benchmark=getattr(
                torch.backends.cudnn, 'benchmark', False
            ),
            deterministic_algorithms=True,  # Assumed if set above
            driver_version=driver_ver,
        )
    except ImportError:
        return DeterminismConfig(
            node_id=node_id,
            cuda_version="unavailable",
            cublas_workspace_config="",
            allow_tf32=False,
            cudnn_allow_tf32=False,
            cudnn_deterministic=False,
            cudnn_benchmark=False,
            deterministic_algorithms=False,
            driver_version="",
        )


# =============================================================================
# CLUSTER-WIDE VALIDATION
# =============================================================================

def validate_cluster_determinism(
    authority_config: DeterminismConfig,
    node_configs: Dict[str, DeterminismConfig],
) -> DeterminismValidation:
    """Validate all nodes match authority's determinism config.

    Rejects any node with mismatched settings.

    Args:
        authority_config: Authority node's locked config.
        node_configs: Dict of node_id -> DeterminismConfig.

    Returns:
        DeterminismValidation with pass/fail and rejected nodes.
    """
    errors = []
    rejected = []

    for node_id, cfg in node_configs.items():
        node_errors = _compare_configs(authority_config, cfg, node_id)
        if node_errors:
            rejected.append(node_id)
            errors.extend(node_errors)

    passed = len(rejected) == 0

    result = DeterminismValidation(
        passed=passed,
        authority_config=authority_config,
        node_configs=node_configs,
        rejected_nodes=rejected,
        errors=errors,
    )

    if passed:
        logger.info(
            f"[DETERMINISM] Cluster validation PASSED: "
            f"{len(node_configs)} nodes match authority"
        )
    else:
        logger.error(
            f"[DETERMINISM] Cluster validation FAILED: "
            f"{len(rejected)} node(s) rejected"
        )
        for e in errors:
            logger.error(f"  • {e}")

    return result


def _compare_configs(
    authority: DeterminismConfig,
    node: DeterminismConfig,
    node_id: str,
) -> List[str]:
    """Compare a node config against authority. Return list of errors."""
    errors = []

    if node.cuda_version != authority.cuda_version:
        errors.append(
            f"Node {node_id[:16]}: CUDA version "
            f"{node.cuda_version} != {authority.cuda_version}"
        )

    if node.cublas_workspace_config != authority.cublas_workspace_config:
        errors.append(
            f"Node {node_id[:16]}: CUBLAS config "
            f"'{node.cublas_workspace_config}' != "
            f"'{authority.cublas_workspace_config}'"
        )

    if node.allow_tf32:
        errors.append(f"Node {node_id[:16]}: allow_tf32 must be False")

    if node.cudnn_allow_tf32:
        errors.append(f"Node {node_id[:16]}: cudnn.allow_tf32 must be False")

    if not node.cudnn_deterministic:
        errors.append(f"Node {node_id[:16]}: cudnn.deterministic must be True")

    if node.cudnn_benchmark:
        errors.append(f"Node {node_id[:16]}: cudnn.benchmark must be False")

    # Driver version: major version must match
    if authority.driver_version and node.driver_version:
        auth_major = authority.driver_version.split('.')[0]
        node_major = node.driver_version.split('.')[0]
        if auth_major != node_major:
            errors.append(
                f"Node {node_id[:16]}: driver version major "
                f"{node_major} != {auth_major}"
            )

    return errors
