"""
node_registration.py — Python Governance for Cluster Node Approval

Governance-only layer:
  - Approve/reject node registrations
  - Manage cluster registry
  - Validate device certificates

Never executes training — only governance.
"""

import hashlib
import json
import logging
import os
import platform
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REGISTRY_PATH = os.path.join('secure_data', 'cluster_registry.json')


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class NodeRecord:
    """Registered cluster node."""
    node_id: str
    device_identity: str
    gpu_arch: str
    cuda_version: str
    hmac_version: str
    dataset_hash: str
    model_version: str
    gpu_count: int
    approved: bool
    registered_at: str
    last_heartbeat: str = ""


@dataclass
class ClusterState:
    """Current cluster state."""
    authority_node: str = ""
    total_nodes: int = 0
    total_gpus: int = 0
    world_size: int = 0
    nodes: Dict[str, NodeRecord] = field(default_factory=dict)


# =============================================================================
# NODE ID GENERATION (mirrors C++)
# =============================================================================

def compute_node_id(
    device_identity: str,
    gpu_arch: str,
    cuda_version: str,
) -> str:
    """Generate node_id = SHA256(device_identity + GPU_arch + CUDA_version)."""
    combined = f"{device_identity}|{gpu_arch}|{cuda_version}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def get_local_device_identity() -> dict:
    """Get local device identity for registration."""
    identity = {
        'hostname': platform.node(),
        'platform': platform.system(),
        'arch': platform.machine(),
        'python': platform.python_version(),
    }

    try:
        import torch
        identity['cuda_available'] = torch.cuda.is_available()
        if torch.cuda.is_available():
            identity['gpu_count'] = torch.cuda.device_count()
            props = torch.cuda.get_device_properties(0)
            identity['gpu_name'] = props.name
            identity['gpu_arch'] = f"cc{props.major}.{props.minor}"
            identity['cuda_version'] = torch.version.cuda or "unknown"
            identity['vram_mb'] = props.total_memory / (1024 * 1024)
        else:
            identity['gpu_count'] = 0
            identity['gpu_name'] = 'CPU'
            identity['gpu_arch'] = 'cpu'
            identity['cuda_version'] = 'none'
    except ImportError:
        identity['cuda_available'] = False
        identity['gpu_count'] = 0

    return identity


# =============================================================================
# CLUSTER REGISTRY
# =============================================================================

class ClusterRegistry:
    """Manage cluster node registrations (governance only)."""

    def __init__(self, path: str = REGISTRY_PATH):
        self._path = path
        self._state = ClusterState()
        self._authority_dataset_hash: str = ""
        self._authority_model_version: str = ""
        self._authority_gpu_arch: str = ""
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, 'r') as f:
                    data = json.load(f)
                self._state.authority_node = data.get('authority_node', '')
                for nid, ndata in data.get('nodes', {}).items():
                    self._state.nodes[nid] = NodeRecord(**ndata)
                self._update_counts()
            except Exception as e:
                logger.error(f"[CLUSTER] Failed to load registry: {e}")

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {
            'authority_node': self._state.authority_node,
            'nodes': {nid: asdict(n) for nid, n in self._state.nodes.items()},
        }
        with open(self._path, 'w') as f:
            json.dump(data, f, indent=2)

    def _update_counts(self):
        approved = [n for n in self._state.nodes.values() if n.approved]
        self._state.total_nodes = len(approved)
        self._state.total_gpus = sum(n.gpu_count for n in approved)
        self._state.world_size = self._state.total_gpus

    def set_authority(self, dataset_hash: str, model_version: str, gpu_arch: str):
        """Set authority's reference values for validation."""
        self._authority_dataset_hash = dataset_hash
        self._authority_model_version = model_version
        self._authority_gpu_arch = gpu_arch

    def register_node(
        self,
        device_identity: str,
        gpu_arch: str,
        cuda_version: str,
        hmac_version: str,
        dataset_hash: str,
        model_version: str,
        gpu_count: int,
    ) -> Tuple[bool, str, str]:
        """Register a node in the cluster.

        Returns:
            Tuple of (approved, node_id, reason).
        """
        node_id = compute_node_id(device_identity, gpu_arch, cuda_version)

        # Validate dataset hash
        if self._authority_dataset_hash and dataset_hash != self._authority_dataset_hash:
            logger.warning(f"[CLUSTER] REJECTED {node_id[:16]}: dataset hash mismatch")
            return False, node_id, "dataset_hash_mismatch"

        # Validate model version
        if self._authority_model_version and model_version != self._authority_model_version:
            logger.warning(f"[CLUSTER] REJECTED {node_id[:16]}: model version mismatch")
            return False, node_id, "model_version_mismatch"

        # Validate GPU arch
        if self._authority_gpu_arch and gpu_arch != self._authority_gpu_arch:
            logger.warning(f"[CLUSTER] REJECTED {node_id[:16]}: GPU arch incompatible")
            return False, node_id, "gpu_arch_incompatible"

        # Approved
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        record = NodeRecord(
            node_id=node_id,
            device_identity=device_identity,
            gpu_arch=gpu_arch,
            cuda_version=cuda_version,
            hmac_version=hmac_version,
            dataset_hash=dataset_hash,
            model_version=model_version,
            gpu_count=gpu_count,
            approved=True,
            registered_at=now,
            last_heartbeat=now,
        )

        self._state.nodes[node_id] = record
        if not self._state.authority_node:
            self._state.authority_node = node_id

        self._update_counts()
        self._save()

        logger.info(
            f"[CLUSTER] APPROVED: {node_id[:16]}... "
            f"({device_identity}, {gpu_count} GPUs)"
        )
        return True, node_id, "approved"

    def remove_node(self, node_id: str) -> bool:
        if node_id in self._state.nodes:
            del self._state.nodes[node_id]
            self._update_counts()
            self._save()
            return True
        return False

    def get_cluster_info(self) -> dict:
        """Get cluster state as JSON-serializable dict."""
        return {
            'authority_node': self._state.authority_node,
            'cluster_nodes': self._state.total_nodes,
            'total_gpu_count': self._state.total_gpus,
            'world_size': self._state.world_size,
            'nodes': [asdict(n) for n in self._state.nodes.values() if n.approved],
        }
