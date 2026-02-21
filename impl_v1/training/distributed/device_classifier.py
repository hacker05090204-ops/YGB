"""
device_classifier.py — Heterogeneous Device Classification

On startup:
  Detect: CUDA / MPS / CPU

Assign role:
  CUDA node  → DDP cluster member (NCCL all-reduce)
  MPS node   → Independent shard worker (FedAvg merge)
  CPU node   → Validation worker only (no training)

Plug-and-play: RTX 3050, RTX 2050, Mac M1 — zero manual config.
"""

import logging
import os
import platform
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DeviceClassification:
    """Device classification result."""
    backend: str           # "cuda", "mps", "cpu"
    role: str              # "ddp_member", "shard_worker", "validation_only"
    device_name: str
    compute_capability: str
    gpu_count: int
    vram_total_mb: float
    cuda_version: str
    mps_available: bool
    can_train: bool
    ddp_eligible: bool


def classify_device() -> DeviceClassification:
    """Classify the local device and assign a cluster role.

    Returns:
        DeviceClassification with role assignment.
    """
    backend = "cpu"
    role = "validation_only"
    device_name = f"CPU ({platform.processor() or platform.machine()})"
    cc = "N/A"
    gpu_count = 0
    vram_total = 0.0
    cuda_ver = "N/A"
    mps_avail = False
    can_train = False
    ddp_eligible = False

    try:
        import torch

        # Check CUDA first (highest priority)
        if torch.cuda.is_available():
            backend = "cuda"
            gpu_count = torch.cuda.device_count()
            props = torch.cuda.get_device_properties(0)
            device_name = props.name
            cc = f"{props.major}.{props.minor}"
            vram_total = props.total_memory / (1024 ** 2)
            cuda_ver = torch.version.cuda or "unknown"
            can_train = True
            ddp_eligible = True
            role = "ddp_member"

        # Check MPS (Apple Silicon)
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            backend = "mps"
            device_name = "Apple Silicon (MPS)"
            cc = "apple_m"
            mps_avail = True
            can_train = True
            ddp_eligible = False  # MPS excluded from NCCL DDP
            role = "shard_worker"

        # CPU fallback
        else:
            role = "validation_only"
            can_train = False

    except ImportError:
        pass

    result = DeviceClassification(
        backend=backend,
        role=role,
        device_name=device_name,
        compute_capability=cc,
        gpu_count=gpu_count,
        vram_total_mb=vram_total,
        cuda_version=cuda_ver,
        mps_available=mps_avail,
        can_train=can_train,
        ddp_eligible=ddp_eligible,
    )

    logger.info(
        f"[CLASSIFY] {device_name}: backend={backend}, role={role}, "
        f"train={can_train}, ddp={ddp_eligible}"
    )

    return result


def get_training_device():
    """Get the appropriate torch.device based on classification."""
    try:
        import torch
    except ImportError:
        return None

    cls = classify_device()

    if cls.backend == "cuda":
        return torch.device("cuda")
    elif cls.backend == "mps":
        return torch.device("mps")
    else:
        return torch.device("cpu")
