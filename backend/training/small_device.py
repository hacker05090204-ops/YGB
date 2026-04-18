from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import torch
import torch.nn as nn


@dataclass(frozen=True)
class DeviceProfile:
    selected_device: str
    device_name: str
    cuda_available: bool
    total_memory_bytes: int
    available_memory_bytes: int
    is_small_device: bool
    is_low_memory: bool
    prefer_cpu_offload: bool
    prefer_dynamic_int8: bool
    prefer_gradient_checkpointing: bool
    preferred_dtype: str
    scale_factor: float
    max_experts_in_memory: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_cuda_available(torch_module) -> bool:
    try:
        return bool(torch_module.cuda.is_available())
    except Exception:
        return False


def _safe_cuda_total_memory(torch_module) -> int:
    if not _safe_cuda_available(torch_module):
        return 0
    try:
        return int(torch_module.cuda.get_device_properties(0).total_memory)
    except Exception:
        return 0


def _safe_available_cuda_memory(torch_module) -> int:
    if not _safe_cuda_available(torch_module):
        return 0
    try:
        if hasattr(torch_module.cuda, "mem_get_info"):
            free_bytes, _total_bytes = torch_module.cuda.mem_get_info()
            return int(free_bytes)
    except Exception:
        pass
    try:
        total_memory = float(torch_module.cuda.get_device_properties(0).total_memory)
        allocated = float(torch_module.cuda.memory_allocated(0))
        return max(0, int(total_memory - allocated))
    except Exception:
        return 0


def _safe_bf16_supported(torch_module) -> bool:
    try:
        return bool(
            _safe_cuda_available(torch_module)
            and hasattr(torch_module.cuda, "is_bf16_supported")
            and torch_module.cuda.is_bf16_supported()
        )
    except Exception:
        return False


def _safe_device_name(torch_module) -> str:
    if not _safe_cuda_available(torch_module):
        return "cpu"
    try:
        return str(torch_module.cuda.get_device_properties(0).name)
    except Exception:
        return "cuda"


def profile_device(
    *,
    torch_module=torch,
    requested_device: Optional[Any] = None,
) -> DeviceProfile:
    requested = str(getattr(requested_device, "type", requested_device) or "auto").lower()
    cuda_available = _safe_cuda_available(torch_module)
    total_memory_bytes = _safe_cuda_total_memory(torch_module)
    available_memory_bytes = _safe_available_cuda_memory(torch_module)
    if requested == "cpu":
        selected_device = "cpu"
    elif requested == "cuda":
        selected_device = "cuda" if cuda_available else "cpu"
    else:
        selected_device = "cuda" if cuda_available else "cpu"

    total_memory_gb = float(total_memory_bytes) / float(1024**3) if total_memory_bytes > 0 else 0.0
    if selected_device == "cpu":
        preferred_dtype = "float32"
        scale_factor = 0.50 if total_memory_gb <= 8.0 else 0.75
        max_experts_in_memory = 0
        prefer_dynamic_int8 = True
        prefer_cpu_offload = True
        prefer_gradient_checkpointing = True
        is_small_device = True
    elif total_memory_gb >= 16.0:
        preferred_dtype = "bfloat16" if _safe_bf16_supported(torch_module) else "float16"
        scale_factor = 1.0
        max_experts_in_memory = 23
        prefer_dynamic_int8 = False
        prefer_cpu_offload = False
        prefer_gradient_checkpointing = False
        is_small_device = False
    elif total_memory_gb >= 8.0:
        preferred_dtype = "float16"
        scale_factor = 0.85
        max_experts_in_memory = 8
        prefer_dynamic_int8 = False
        prefer_cpu_offload = False
        prefer_gradient_checkpointing = False
        is_small_device = False
    elif total_memory_gb >= 4.0:
        preferred_dtype = "float16"
        scale_factor = 0.60
        max_experts_in_memory = 4
        prefer_dynamic_int8 = False
        prefer_cpu_offload = True
        prefer_gradient_checkpointing = True
        is_small_device = True
    else:
        preferred_dtype = "float16" if selected_device == "cuda" else "float32"
        scale_factor = 0.50
        max_experts_in_memory = 2 if selected_device == "cuda" else 0
        prefer_dynamic_int8 = selected_device == "cpu"
        prefer_cpu_offload = True
        prefer_gradient_checkpointing = True
        is_small_device = True

    return DeviceProfile(
        selected_device=selected_device,
        device_name=_safe_device_name(torch_module) if selected_device == "cuda" else "cpu",
        cuda_available=cuda_available,
        total_memory_bytes=int(total_memory_bytes),
        available_memory_bytes=int(available_memory_bytes),
        is_small_device=bool(is_small_device),
        is_low_memory=bool(is_small_device),
        prefer_cpu_offload=bool(prefer_cpu_offload),
        prefer_dynamic_int8=bool(prefer_dynamic_int8),
        prefer_gradient_checkpointing=bool(prefer_gradient_checkpointing),
        preferred_dtype=preferred_dtype,
        scale_factor=float(scale_factor),
        max_experts_in_memory=int(max_experts_in_memory),
    )


def _dtype_from_name(name: str) -> torch.dtype:
    normalized = str(name or "float32").strip().lower()
    if normalized in {"bf16", "bfloat16"}:
        return torch.bfloat16
    if normalized in {"fp16", "float16", "half"}:
        return torch.float16
    return torch.float32


def prepare_model_for_small_device(
    model: nn.Module,
    *,
    profile: Optional[DeviceProfile] = None,
    device: Optional[Any] = None,
    for_training: bool = True,
    enable_dynamic_int8: Optional[bool] = None,
) -> nn.Module:
    resolved_profile = profile or profile_device(requested_device=device)
    target_device_name = str(getattr(device, "type", device) or resolved_profile.selected_device).lower()
    if target_device_name == "cuda" and not resolved_profile.cuda_available:
        target_device_name = "cpu"
    target_device = torch.device(target_device_name)
    target_dtype = _dtype_from_name(resolved_profile.preferred_dtype)
    if target_device.type != "cuda":
        target_dtype = torch.float32

    model = model.to(device=target_device, dtype=target_dtype)
    setattr(model, "_small_device_profile", resolved_profile.as_dict())
    setattr(model, "_prepared_for_small_device", True)

    if hasattr(model, "configure_for_device_profile"):
        model.configure_for_device_profile(resolved_profile)

    if resolved_profile.prefer_gradient_checkpointing and hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()

    use_dynamic_int8 = bool(
        resolved_profile.prefer_dynamic_int8 if enable_dynamic_int8 is None else enable_dynamic_int8
    )
    if not for_training and target_device.type == "cpu" and use_dynamic_int8:
        if hasattr(model, "to_dynamic_int8"):
            quantized_model = model.to_dynamic_int8()
            setattr(quantized_model, "_small_device_profile", resolved_profile.as_dict())
            setattr(quantized_model, "_prepared_for_small_device", True)
            return quantized_model
    return model


prepare_model_for_low_memory = prepare_model_for_small_device


__all__ = [
    "DeviceProfile",
    "profile_device",
    "prepare_model_for_small_device",
    "prepare_model_for_low_memory",
]
