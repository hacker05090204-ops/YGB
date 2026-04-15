"""
Auto-detect hardware and expose both legacy training config helpers and the
newer runtime device-selection contract used by voice/context-paging flows.

Same file works on Google Colab, local CUDA, Apple MPS, and CPU-only hosts.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("ygb.device_manager")

AUTO_DEVICE = "auto"
DEFAULT_MIXED_PRECISION = "auto"
_SUPPORTED_MIXED_PRECISION = {DEFAULT_MIXED_PRECISION, "bf16", "fp16", "fp32"}
_TORCH_SENTINEL = object()


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _is_colab_runtime() -> bool:
    return _env_flag("YGB_COLAB") or "COLAB_GPU" in os.environ or "/content" in os.getcwd()


def _detect_platform_name() -> str:
    if _is_colab_runtime():
        return "Google Colab"
    if "LIGHTNING_CLOUD_PROJECT_ID" in os.environ or "LIGHTNING_STUDIO_ID" in os.environ:
        return "Lightning.ai"
    if "KAGGLE_KERNEL_RUN_TYPE" in os.environ:
        return "Kaggle"
    if "PAPERSPACE_NOTEBOOK_REPO_ID" in os.environ:
        return "Paperspace"
    return "Unknown"


def _resolve_torch_module(torch_module: Any) -> Any | None:
    if torch_module is not _TORCH_SENTINEL:
        return torch_module
    try:
        import torch  # type: ignore

        return torch
    except ImportError:
        return None


def _safe_cuda_available(torch_module: Any | None) -> bool:
    try:
        return bool(torch_module is not None and torch_module.cuda.is_available())
    except Exception:
        return False


def _safe_mps_available(torch_module: Any | None) -> bool:
    try:
        return bool(
            torch_module is not None
            and getattr(getattr(torch_module, "backends", None), "mps", None) is not None
            and torch_module.backends.mps.is_available()
        )
    except Exception:
        return False


def _safe_gpu_count(torch_module: Any | None, cuda_available: bool) -> int:
    if not cuda_available or torch_module is None:
        return 0
    try:
        return int(torch_module.cuda.device_count())
    except Exception:
        return 0


def _safe_cuda_properties(torch_module: Any | None, cuda_available: bool) -> Any | None:
    if not cuda_available or torch_module is None:
        return None
    try:
        return torch_module.cuda.get_device_properties(0)
    except Exception:
        return None


def _safe_bf16_supported(torch_module: Any | None, cuda_available: bool) -> bool:
    if not cuda_available or torch_module is None or not hasattr(torch_module.cuda, "is_bf16_supported"):
        return False
    try:
        return bool(torch_module.cuda.is_bf16_supported())
    except Exception:
        return False


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


@dataclass
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


def resolve_device_configuration(
    preferred_device: str | None = AUTO_DEVICE,
    *,
    mixed_precision: str | None = DEFAULT_MIXED_PRECISION,
    torch_module: Any = _TORCH_SENTINEL,
    configure_runtime: bool = True,
) -> DeviceConfiguration:
    requested_device = str(preferred_device or AUTO_DEVICE).strip().lower() or AUTO_DEVICE
    if requested_device not in {AUTO_DEVICE, "cuda", "cpu", "mps"}:
        raise ValueError(f"Unsupported preferred_device: {preferred_device!r}")

    requested_precision = str(mixed_precision or DEFAULT_MIXED_PRECISION).strip().lower() or DEFAULT_MIXED_PRECISION
    if requested_precision not in _SUPPORTED_MIXED_PRECISION:
        raise ValueError(f"Unsupported mixed_precision: {mixed_precision!r}")

    torch_runtime = _resolve_torch_module(torch_module)
    torch_available = torch_runtime is not None
    torch_version = str(getattr(torch_runtime, "__version__", "") or "") if torch_available else ""
    cuda_available = _safe_cuda_available(torch_runtime)
    mps_available = _safe_mps_available(torch_runtime)
    gpu_count = _safe_gpu_count(torch_runtime, cuda_available)
    properties = _safe_cuda_properties(torch_runtime, cuda_available)
    bf16_supported = _safe_bf16_supported(torch_runtime, cuda_available)
    total_memory_gb = (
        float(getattr(properties, "total_memory", 0.0) or 0.0) / float(1024**3)
        if properties is not None
        else 0.0
    )
    cuda_version = str(getattr(getattr(torch_runtime, "version", None), "cuda", "") or "")

    fallback_reasons: list[str] = []
    if _env_flag("YGB_FORCE_CPU"):
        selected_device = "cpu"
        fallback_reasons.append("YGB_FORCE_CPU override")
    elif requested_device == AUTO_DEVICE:
        if cuda_available:
            selected_device = "cuda"
        elif mps_available:
            selected_device = "mps"
        else:
            selected_device = "cpu"
    elif requested_device == "cuda":
        if cuda_available:
            selected_device = "cuda"
        elif mps_available:
            selected_device = "mps"
            fallback_reasons.append("preferred cuda unavailable; using mps")
        else:
            selected_device = "cpu"
            fallback_reasons.append("preferred cuda unavailable; using cpu")
    elif requested_device == "mps":
        if mps_available:
            selected_device = "mps"
        elif cuda_available:
            selected_device = "cuda"
            fallback_reasons.append("preferred mps unavailable; using cuda")
        else:
            selected_device = "cpu"
            fallback_reasons.append("preferred mps unavailable; using cpu")
    else:
        selected_device = "cpu"

    resolved_precision = "fp32"
    if selected_device == "cuda":
        if requested_precision == DEFAULT_MIXED_PRECISION:
            resolved_precision = "bf16" if bf16_supported else "fp16"
        elif requested_precision == "bf16" and not bf16_supported:
            resolved_precision = "fp16"
            fallback_reasons.append("bf16 unsupported on selected cuda device; using fp16")
        else:
            resolved_precision = requested_precision
    elif requested_precision not in {DEFAULT_MIXED_PRECISION, "fp32"}:
        fallback_reasons.append(f"{selected_device} does not use {requested_precision}; using fp32")

    amp_enabled = selected_device == "cuda" and resolved_precision in {"bf16", "fp16"}
    if selected_device == "cuda":
        device_name = str(getattr(properties, "name", "CUDA GPU") or "CUDA GPU")
    elif selected_device == "mps":
        device_name = "Apple Silicon (MPS)"
    else:
        device_name = f"CPU ({os.cpu_count() or 1} cores)"

    configuration = DeviceConfiguration(
        requested_device=requested_device,
        selected_device=selected_device,
        torch_device="cuda:0" if selected_device == "cuda" else selected_device,
        device_name=device_name,
        accelerator=selected_device,
        distributed_backend="nccl" if selected_device == "cuda" else "gloo",
        mixed_precision=resolved_precision,
        amp_enabled=amp_enabled,
        bf16_supported=bf16_supported,
        pin_memory=selected_device == "cuda",
        non_blocking=selected_device == "cuda",
        supports_distributed_training=selected_device == "cuda",
        is_colab=_is_colab_runtime(),
        torch_available=torch_available,
        torch_version=torch_version,
        cuda_available=cuda_available,
        mps_available=mps_available,
        gpu_count=gpu_count,
        total_memory_gb=round(total_memory_gb, 2),
        cuda_version=cuda_version,
        fallback_reason="; ".join(reason for reason in fallback_reasons if reason),
    )

    if configure_runtime and torch_runtime is not None and selected_device == "cuda":
        try:
            if hasattr(getattr(torch_runtime, "backends", None), "cuda") and hasattr(torch_runtime.backends.cuda, "matmul"):
                torch_runtime.backends.cuda.matmul.allow_tf32 = True
            if hasattr(getattr(torch_runtime, "backends", None), "cudnn"):
                torch_runtime.backends.cudnn.allow_tf32 = True
        except Exception:
            logger.debug("Skipping optional CUDA runtime tuning", exc_info=True)

    return configuration


def get_config(target_params: int = 130_430_000) -> DeviceConfig:
    """Return the legacy training config shape expected by older scripts."""
    resolved = resolve_device_configuration(configure_runtime=False)
    platform_name = _detect_platform_name()

    if resolved.selected_device == "cuda":
        vram_gb = resolved.total_memory_gb
        if vram_gb >= 80:
            batch_size = 256
            grad_ckpt = False
            max_params = 20_000_000_000
            profile = "A100-80GB"
        elif vram_gb >= 40:
            batch_size = 128
            grad_ckpt = False
            max_params = 10_000_000_000
            profile = "A100-40GB"
        elif vram_gb >= 24:
            batch_size = 64
            grad_ckpt = False
            max_params = 5_000_000_000
            profile = "A10G-24GB"
        elif vram_gb >= 16:
            batch_size = 32
            grad_ckpt = target_params > 1_000_000_000
            max_params = 3_000_000_000
            profile = "T4/V100/P100-16GB"
        elif vram_gb >= 12:
            batch_size = 16
            grad_ckpt = True
            max_params = 1_500_000_000
            profile = "K80-12GB"
        else:
            batch_size = 8
            grad_ckpt = True
            max_params = 500_000_000
            profile = f"GPU-{vram_gb:.0f}GB"
        notes_parts = [platform_name if platform_name != "Unknown" else "Cloud GPU", profile]
    else:
        batch_size = 8
        grad_ckpt = True
        max_params = 130_000_000
        notes_parts = [
            f"{platform_name} {resolved.selected_device.upper()} fallback"
            if platform_name != "Unknown"
            else f"{resolved.selected_device.upper()} fallback"
        ]

    if resolved.fallback_reason:
        notes_parts.append(resolved.fallback_reason)

    config = DeviceConfig(
        device=resolved.selected_device,
        device_name=resolved.device_name,
        vram_gb=resolved.total_memory_gb,
        batch_size=batch_size,
        precision=resolved.mixed_precision,
        gradient_checkpointing=grad_ckpt,
        use_amp=resolved.amp_enabled,
        num_workers=min(4, os.cpu_count() or 1) if resolved.selected_device == "cuda" else max(1, (os.cpu_count() or 1) // 2),
        pin_memory=resolved.pin_memory,
        max_model_params=max_params,
        is_colab=resolved.is_colab,
        notes=" | ".join(notes_parts),
    )

    logger.info(
        "Device: %s | VRAM: %.1fGB | Batch: %d | Precision: %s | GradCkpt: %s | MaxParams: %dM",
        config.device_name,
        config.vram_gb,
        config.batch_size,
        config.precision,
        config.gradient_checkpointing,
        config.max_model_params // 1_000_000,
    )
    return config


def print_config(config: DeviceConfig) -> None:
    print("\n" + "=" * 50)
    print("YBG DEVICE CONFIGURATION")
    print("=" * 50)
    print(f"  Device:   {config.device_name}")
    print(f"  VRAM:     {config.vram_gb:.1f}GB")
    print(f"  Batch:    {config.batch_size}")
    print(f"  Precision:{config.precision}")
    print(f"  GradCkpt: {config.gradient_checkpointing}")
    print(f"  MaxModel: {config.max_model_params / 1e9:.1f}B params")
    print(f"  Colab:    {config.is_colab}")
    print(f"  Notes:    {config.notes}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    cfg = get_config()
    print_config(cfg)
