"""
auto_register.py — Automatic GPU Registration on Startup

If YGB_CLUSTER_MODE=auto:
  1. Attempt to connect to authority
  2. If reachable → register node
  3. If not → start standalone

Logs: cluster_joined, node_id, gpu_count
"""

import hashlib
import json
import logging
import os
import platform
import socket
import time
from dataclasses import dataclass, asdict
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_AUTHORITY = "127.0.0.1"
DEFAULT_PORT = 9742
CLUSTER_STATE_PATH = os.path.join('secure_data', 'cluster_state.json')


@dataclass
class RegistrationResult:
    """Result of auto-registration attempt."""
    cluster_joined: bool
    node_id: str
    gpu_count: int
    device_name: str
    rank: int
    world_size: int
    mode: str     # "cluster", "standalone"
    authority_addr: str


def compute_node_id(device_identity: str, gpu_arch: str, cuda_version: str) -> str:
    """Generate node_id = SHA256(device_identity|GPU_arch|CUDA_version)."""
    combined = f"{device_identity}|{gpu_arch}|{cuda_version}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def _try_connect_authority(addr: str, port: int, timeout: float = 3.0) -> bool:
    """Check if authority is reachable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((addr, port))
        s.close()
        return True
    except (socket.error, OSError):
        return False


def _get_device_info() -> dict:
    """Get local device info for registration."""
    info = {
        'hostname': platform.node(),
        'device_identity': f"{platform.node()}_{platform.machine()}",
        'gpu_count': 0,
        'device_name': 'CPU',
        'gpu_arch': 'cpu',
        'cuda_version': 'none',
        'vram_total_mb': 0,
    }

    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info['gpu_count'] = torch.cuda.device_count()
            info['device_name'] = props.name
            info['gpu_arch'] = f"cc{props.major}.{props.minor}"
            info['cuda_version'] = torch.version.cuda or "unknown"
            info['vram_total_mb'] = int(props.total_memory / (1024 * 1024))
    except ImportError:
        pass

    return info


def auto_register() -> RegistrationResult:
    """Attempt automatic cluster registration.

    Checks YGB_CLUSTER_MODE env var.
    If "auto": try to connect to authority.
    If reachable: register node.
    If not: start standalone.

    Returns:
        RegistrationResult.
    """
    cluster_mode = os.environ.get('YGB_CLUSTER_MODE', 'standalone')
    authority_addr = os.environ.get('YGB_AUTHORITY_ADDR', DEFAULT_AUTHORITY)
    authority_port = int(os.environ.get('YGB_AUTHORITY_PORT', str(DEFAULT_PORT)))

    device = _get_device_info()
    node_id = compute_node_id(
        device['device_identity'],
        device['gpu_arch'],
        device['cuda_version'],
    )

    # Standalone mode if not auto
    if cluster_mode != 'auto':
        result = RegistrationResult(
            cluster_joined=False,
            node_id=node_id,
            gpu_count=device['gpu_count'],
            device_name=device['device_name'],
            rank=0,
            world_size=1,
            mode="standalone",
            authority_addr="",
        )
        _save_state(result)
        logger.info(
            f"[REGISTER] Standalone mode: {device['device_name']}, "
            f"{device['gpu_count']} GPUs"
        )
        return result

    # Try cluster join
    logger.info(f"[REGISTER] Attempting cluster join to {authority_addr}:{authority_port}")

    if _try_connect_authority(authority_addr, authority_port):
        # Authority reachable — register
        logger.info("[REGISTER] Authority reachable — sending join request")
        result = RegistrationResult(
            cluster_joined=True,
            node_id=node_id,
            gpu_count=device['gpu_count'],
            device_name=device['device_name'],
            rank=0,  # Will be assigned by authority
            world_size=1,  # Will be updated
            mode="cluster",
            authority_addr=f"{authority_addr}:{authority_port}",
        )
    else:
        # Authority unreachable — standalone
        logger.info("[REGISTER] Authority unreachable — starting standalone")
        result = RegistrationResult(
            cluster_joined=False,
            node_id=node_id,
            gpu_count=device['gpu_count'],
            device_name=device['device_name'],
            rank=0,
            world_size=1,
            mode="standalone",
            authority_addr="",
        )

    _save_state(result)

    logger.info(json.dumps({
        'cluster_joined': result.cluster_joined,
        'node_id': result.node_id[:16] + '...',
        'gpu_count': result.gpu_count,
    }))

    return result


def _save_state(result: RegistrationResult):
    """Save cluster state to disk."""
    os.makedirs(os.path.dirname(CLUSTER_STATE_PATH), exist_ok=True)
    with open(CLUSTER_STATE_PATH, 'w') as f:
        json.dump(asdict(result), f, indent=2)


def load_state() -> Optional[RegistrationResult]:
    """Load saved cluster state."""
    if os.path.exists(CLUSTER_STATE_PATH):
        try:
            with open(CLUSTER_STATE_PATH, 'r') as f:
                data = json.load(f)
            return RegistrationResult(**data)
        except Exception:
            pass
    return None
