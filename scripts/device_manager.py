"""Device detection helpers for training, voice, and background workers.

This module preserves the original Phase 2 interface via [`get_config()`](scripts/device_manager.py:221)
and [`print_config()`](scripts/device_manager.py:257) while also exposing the richer runtime API
required by later phases via [`DeviceConfiguration`](scripts/device_manager.py:26) and
[`resolve_device_configuration()`](scripts/device_manager.py:109).
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("ygb.device_manager")

AUTO_DEVICE = "auto"
DEFAULT_MIXED_PRECISION = "auto"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_TORCH_UNSET = object()


@dataclass(frozen=True)
class DeviceConfiguration:
    requested_device: str
    selected_device: str
    torch_device: str
    device_name: str
    accelerator: str
    distributed_backend: str
    mixed_precision: str
    amp_enabled: bool
    bf16_supported: bool
    pin_memory: bool
    non_blocking: bool
    supports_distributed_training: bool
    is_colab: bool
    torch_available: bool
    torch_version: str
    cuda_available: bool
    mps_available: bool
    gpu_count: int
    total_memory_gb: float
    cuda_version: str
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeviceConfig:
    device: str
    device_name: str
    vram_gb: float
    batch_size: int
    precision: str
    gradient_checkpointing: bool
    use_amp: bool
    num_workers: int
    pin_memory: bool
    max_model_params: int
    is_colab: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_truthy(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in _TRUTHY_VALUES


def _detect_colab() -> bool:
    return (
        _env_truthy("YGB_COLAB")
        or "COLAB_GPU" in os.environ
        or "/content" in os.getcwd().replace("\\", "/")
    )


def _load_torch_module(torch_module: Any) -> Any | None:
    if torch_module is _TORCH_UNSET:
        try:
            import torch as imported_torch  # type: ignore

            return imported_torch
        except ImportError:
            return None
    return torch_module


def _safe_cuda_available(torch_module: Any | None) -> bool:
    try:
        return bool(torch_module and torch_module.cuda.is_available())
    except Exception:
        return False


def _safe_mps_available(torch_module: Any | None) -> bool:
    try:
        backends = getattr(torch_module, "backends", None)
        mps_backend = getattr(backends, "mps", None)
        return bool(mps_backend and mps_backend.is_available())
    except Exception:
        return False


def _safe_gpu_count(torch_module: Any | None, cuda_available: bool) -> int:
    if not cuda_available:
        return 0
    try:
        return int(torch_module.cuda.device_count())
    except Exception:
        return 1


def _normalize_requested_device(preferred_device: str | None) -> str:
    normalized = str(preferred_device or AUTO_DEVICE).strip().lower()
    return normalized or AUTO_DEVICE


def resolve_device_configuration(
    preferred_device: str | None = AUTO_DEVICE,
    *,
    mixed_precision: str | None = DEFAULT_MIXED_PRECISION,
    torch_module: Any = _TORCH_UNSET,
    configure_runtime: bool = True,
) -> DeviceConfiguration:
    """Resolve runtime device configuration with graceful CPU fallback."""

    del configure_runtime  # Runtime tuning is optional; resolution is what callers need here.

    requested_device = _normalize_requested_device(preferred_device)
    requested_precision = str(mixed_precision or DEFAULT_MIXED_PRECISION).strip().lower() or DEFAULT_MIXED_PRECISION
    is_colab = _detect_colab()
    torch_runtime = _load_torch_module(torch_module)
    torch_available = torch_runtime is not None
    torch_version = str(getattr(torch_runtime, "__version__", "")) if torch_available else ""
    cuda_available = _safe_cuda_available(torch_runtime)
    mps_available = _safe_mps_available(torch_runtime)
    gpu_count = _safe_gpu_count(torch_runtime, cuda_available)
    force_cpu = _env_truthy("YGB_FORCE_CPU")

    selected_device = "cpu"
    fallback_reason = ""

    if force_cpu:
        selected_device = "cpu"
        fallback_reason = "YGB_FORCE_CPU requested CPU fallback"
    elif requested_device in {"cpu"}:
        selected_device = "cpu"
    elif requested_device in {"cuda", "gpu"}:
        if cuda_available:
            selected_device = "cuda"
        else:
            selected_device = "cpu"
            fallback_reason = "preferred cuda unavailable; falling back to cpu"
    elif requested_device == "mps":
        if mps_available:
            selected_device = "mps"
        else:
            selected_device = "cpu"
            fallback_reason = "preferred mps unavailable; falling back to cpu"
    else:
        if cuda_available:
            selected_device = "cuda"
        elif mps_available:
            selected_device = "mps"
        else:
            selected_device = "cpu"

    total_memory_gb = 0.0
    device_name = "CPU"
    cuda_version = str(getattr(getattr(torch_runtime, "version", None), "cuda", "") or "")
    bf16_supported = False

    if selected_device == "cuda" and torch_available:
        try:
            props = torch_runtime.cuda.get_device_properties(0)
            total_memory_gb = float(getattr(props, "total_memory", 0.0) or 0.0) / (1024**3)
            device_name = str(getattr(props, "name", "CUDA GPU") or "CUDA GPU")
        except Exception:
            total_memory_gb = 0.0
            try:
                device_name = str(torch_runtime.cuda.get_device_name(0) or "CUDA GPU")
            except Exception:
                device_name = "CUDA GPU"
        try:
            bf16_supported = bool(torch_runtime.cuda.is_bf16_supported())
        except Exception:
            bf16_supported = False
    elif selected_device == "mps":
        device_name = "Apple Silicon"
    else:
        cpu_count = os.cpu_count() or 1
        device_name = f"CPU ({cpu_count} cores)"

    if selected_device == "cuda":
        if requested_precision in {"auto", ""}:
            resolved_precision = "bf16" if bf16_supported else "fp16"
        elif requested_precision in {"bf16", "fp16", "fp32"}:
            resolved_precision = requested_precision
        else:
            resolved_precision = "bf16" if bf16_supported else "fp16"
        amp_enabled = resolved_precision in {"bf16", "fp16"}
        torch_device = "cuda:0"
        distributed_backend = "nccl"
        pin_memory = True
        non_blocking = True
        supports_distributed_training = True
    elif selected_device == "mps":
        resolved_precision = "fp32"
        amp_enabled = False
        torch_device = "mps"
        distributed_backend = "gloo"
        pin_memory = False
        non_blocking = False
        supports_distributed_training = False
    else:
        resolved_precision = "fp32"
        amp_enabled = False
        torch_device = "cpu"
        distributed_backend = "gloo"
        pin_memory = False
        non_blocking = False
        supports_distributed_training = False

    configuration = DeviceConfiguration(
        requested_device=requested_device,
        selected_device=selected_device,
        torch_device=torch_device,
        device_name=device_name,
        accelerator=selected_device,
        distributed_backend=distributed_backend,
        mixed_precision=resolved_precision,
        amp_enabled=amp_enabled,
        bf16_supported=bf16_supported,
        pin_memory=pin_memory,
        non_blocking=non_blocking,
        supports_distributed_training=supports_distributed_training,
        is_colab=is_colab,
        torch_available=torch_available,
        torch_version=torch_version,
        cuda_available=cuda_available,
        mps_available=mps_available,
        gpu_count=gpu_count,
        total_memory_gb=round(total_memory_gb, 3),
        cuda_version=cuda_version,
        fallback_reason=fallback_reason,
    )

    logger.info(
        "Resolved device configuration requested=%s selected=%s precision=%s fallback=%s",
        configuration.requested_device,
        configuration.selected_device,
        configuration.mixed_precision,
        configuration.fallback_reason or "none",
    )
    return configuration


def _legacy_batch_size(selected_device: str, total_memory_gb: float) -> int:
    if selected_device == "cuda":
        if total_memory_gb >= 40:
            return 128
        if total_memory_gb >= 16:
            return 32
        if total_memory_gb >= 8:
            return 16
        if total_memory_gb >= 4:
            return 8
        return 4
    if selected_device == "mps":
        return 16
    return 8


def _legacy_max_params(selected_device: str, total_memory_gb: float) -> int:
    if selected_device == "cuda":
        if total_memory_gb >= 40:
            return 10_000_000_000
        if total_memory_gb >= 16:
            return 3_000_000_000
        if total_memory_gb >= 8:
            return 1_000_000_000
        if total_memory_gb >= 4:
            return 500_000_000
        return 130_000_000
    if selected_device == "mps":
        return 500_000_000
    return 130_000_000


def get_config(target_params: int = 130_430_000) -> DeviceConfig:
    """Legacy Phase 2 interface preserved for older scripts and docs."""

    runtime = resolve_device_configuration(configure_runtime=False)
    batch_size = _legacy_batch_size(runtime.selected_device, runtime.total_memory_gb)
    max_params = _legacy_max_params(runtime.selected_device, runtime.total_memory_gb)
    gradient_checkpointing = runtime.selected_device != "cuda" or runtime.total_memory_gb < 16 or target_params > 1_000_000_000
    cpu_count = os.cpu_count() or 1
    num_workers = min(4, cpu_count) if runtime.selected_device == "cuda" else max(1, cpu_count // 2)
    notes = runtime.fallback_reason or (
        f"{runtime.selected_device.upper()} runtime"
        if runtime.selected_device != "cpu"
        else "CPU fallback — training will be slow"
    )
    return DeviceConfig(
        device=runtime.selected_device,
        device_name=runtime.device_name,
        vram_gb=runtime.total_memory_gb if runtime.selected_device == "cuda" else 0.0,
        batch_size=batch_size,
        precision=runtime.mixed_precision,
        gradient_checkpointing=gradient_checkpointing,
        use_amp=runtime.amp_enabled,
        num_workers=num_workers,
        pin_memory=runtime.pin_memory,
        max_model_params=max_params,
        is_colab=runtime.is_colab,
        notes=notes,
    )


def print_config(config: DeviceConfig | DeviceConfiguration) -> None:
    """Print device configuration in a readable format."""

    if isinstance(config, DeviceConfiguration):
        device_name = config.device_name
        vram_gb = config.total_memory_gb if config.selected_device == "cuda" else 0.0
        batch_size = _legacy_batch_size(config.selected_device, config.total_memory_gb)
        precision = config.mixed_precision
        gradient_checkpointing = config.selected_device != "cuda" or config.total_memory_gb < 16
        max_model_params = _legacy_max_params(config.selected_device, config.total_memory_gb)
        is_colab = config.is_colab
        notes = config.fallback_reason or f"{config.selected_device.upper()} runtime"
    else:
        device_name = config.device_name
        vram_gb = config.vram_gb
        batch_size = config.batch_size
        precision = config.precision
        gradient_checkpointing = config.gradient_checkpointing
        max_model_params = config.max_model_params
        is_colab = config.is_colab
        notes = config.notes

    print("\n" + "=" * 50)
    print("YBG DEVICE CONFIGURATION")
    print("=" * 50)
    print(f"  Device:   {device_name}")
    print(f"  VRAM:     {vram_gb:.1f}GB")
    print(f"  Batch:    {batch_size}")
    print(f"  Precision:{precision}")
    print(f"  GradCkpt: {gradient_checkpointing}")
    print(f"  MaxModel: {max_model_params/1e9:.1f}B params")
    print(f"  Colab:    {is_colab}")
    print(f"  Notes:    {notes}")
    print("=" * 50 + "\n")


__all__ = [
    "AUTO_DEVICE",
    "DEFAULT_MIXED_PRECISION",
    "DeviceConfig",
    "DeviceConfiguration",
    "get_config",
    "print_config",
    "resolve_device_configuration",
]


if __name__ == "__main__":
    print_config(get_config())
