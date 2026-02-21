"""
device_selector.py — Unified GPU Auto-Detection & Activation

Priority order:
  1. CUDA (dedicated GPU preferred over integrated)
  2. MPS (macOS Apple Silicon)
  3. CPU (fallback)

If multiple CUDA GPUs detected:
  - Logs availability for DDP enablement
  - Prefers dedicated GPU (highest memory) over integrated

Deterministic: Seeds locked per device.
"""

import os
import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DEVICE INFO
# =============================================================================

@dataclass
class DeviceSelection:
    """Selected compute device info."""
    device_type: str        # "cuda", "mps", "cpu"
    device_name: str        # e.g. "NVIDIA GeForce RTX 2050"
    gpu_count: int          # Total CUDA GPUs available
    selected_gpu_index: int # Which GPU index selected (-1 for CPU/MPS)
    vram_total_mb: float    # VRAM in MB (0 for CPU)
    compute_capability: str # e.g. "8.6" (empty for non-CUDA)
    ddp_available: bool     # True if multi-GPU DDP possible
    mps_available: bool     # True if MPS backend available


# =============================================================================
# DETECTION
# =============================================================================

def _detect_cuda() -> Optional[DeviceSelection]:
    """Detect CUDA GPUs, prefer dedicated over integrated."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None

        gpu_count = torch.cuda.device_count()
        if gpu_count == 0:
            return None

        # Find the GPU with the most VRAM (dedicated > integrated)
        best_idx = 0
        best_mem = 0

        for i in range(gpu_count):
            props = torch.cuda.get_device_properties(i)
            if props.total_mem > best_mem:
                best_mem = props.total_mem
                best_idx = i

        props = torch.cuda.get_device_properties(best_idx)
        cc = f"{props.major}.{props.minor}"

        return DeviceSelection(
            device_type="cuda",
            device_name=props.name,
            gpu_count=gpu_count,
            selected_gpu_index=best_idx,
            vram_total_mb=props.total_mem / (1024 * 1024),
            compute_capability=cc,
            ddp_available=gpu_count > 1,
            mps_available=False,
        )
    except ImportError:
        return None


def _detect_mps() -> Optional[DeviceSelection]:
    """Detect Apple MPS backend (macOS)."""
    try:
        import torch
        if not hasattr(torch.backends, 'mps') or not torch.backends.mps.is_available():
            return None

        return DeviceSelection(
            device_type="mps",
            device_name="Apple MPS",
            gpu_count=0,
            selected_gpu_index=-1,
            vram_total_mb=0,
            compute_capability="",
            ddp_available=False,
            mps_available=True,
        )
    except ImportError:
        return None


def _fallback_cpu() -> DeviceSelection:
    """CPU fallback."""
    return DeviceSelection(
        device_type="cpu",
        device_name="CPU",
        gpu_count=0,
        selected_gpu_index=-1,
        vram_total_mb=0,
        compute_capability="",
        ddp_available=False,
        mps_available=False,
    )


# =============================================================================
# PUBLIC API
# =============================================================================

def select_device() -> DeviceSelection:
    """Auto-detect and select the best compute device.

    Priority: CUDA (dedicated) > MPS > CPU

    Returns:
        DeviceSelection with device info.
    """
    # Try CUDA first
    cuda = _detect_cuda()
    if cuda:
        logger.info(
            f"[DEVICE] Selected CUDA: {cuda.device_name} "
            f"(GPU {cuda.selected_gpu_index}/{cuda.gpu_count}, "
            f"VRAM={cuda.vram_total_mb:.0f}MB, CC={cuda.compute_capability})"
        )
        if cuda.ddp_available:
            logger.info(f"[DEVICE] Multi-GPU DDP available ({cuda.gpu_count} GPUs)")
        return cuda

    # Try MPS
    mps = _detect_mps()
    if mps:
        logger.info("[DEVICE] Selected MPS (Apple Silicon)")
        return mps

    # Fallback
    logger.warning("[DEVICE] No GPU available — falling back to CPU")
    return _fallback_cpu()


def get_torch_device(selection: DeviceSelection = None):
    """Get a torch.device from selection.

    Args:
        selection: DeviceSelection. If None, auto-detects.

    Returns:
        torch.device object.
    """
    try:
        import torch
    except ImportError:
        raise RuntimeError("PyTorch not installed")

    if selection is None:
        selection = select_device()

    if selection.device_type == "cuda":
        return torch.device(f"cuda:{selection.selected_gpu_index}")
    elif selection.device_type == "mps":
        return torch.device("mps")
    else:
        return torch.device("cpu")


def apply_deterministic_settings(seed: int = 42) -> dict:
    """Apply deterministic settings for reproducibility.

    Args:
        seed: Base random seed.

    Returns:
        Dict of applied settings.
    """
    results = {}

    try:
        import torch

        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        results["cublas_workspace"] = True

        torch.manual_seed(seed)
        results["manual_seed"] = seed

        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        results["cudnn_deterministic"] = True
        results["cudnn_benchmark"] = False

        try:
            torch.use_deterministic_algorithms(True)
            results["deterministic_algorithms"] = True
        except Exception:
            results["deterministic_algorithms"] = False

    except ImportError:
        results["pytorch_available"] = False

    return results


def get_device_log(selection: DeviceSelection = None) -> dict:
    """Get device info as JSON-serializable dict for telemetry.

    Args:
        selection: DeviceSelection. If None, auto-detects.

    Returns:
        Dict with device_type, gpu_count, etc.
    """
    if selection is None:
        selection = select_device()
    return asdict(selection)
