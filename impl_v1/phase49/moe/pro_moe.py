from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint as activation_checkpoint

from .expert import SingleExpert
from .moe_architecture import EXPERT_FIELDS, MoEConfig


logger = logging.getLogger("ygb.pro_moe")


def _resolve_quantize_dynamic():
    ao_quantization = getattr(getattr(torch, "ao", None), "quantization", None)
    if ao_quantization is not None and hasattr(ao_quantization, "quantize_dynamic"):
        return ao_quantization.quantize_dynamic
    legacy_quantization = getattr(torch, "quantization", None)
    if legacy_quantization is not None and hasattr(legacy_quantization, "quantize_dynamic"):
        return legacy_quantization.quantize_dynamic
    return None


def _safe_cuda_available() -> bool:
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _safe_cuda_total_memory() -> int:
    if not _safe_cuda_available():
        return 0
    try:
        return int(torch.cuda.get_device_properties(0).total_memory)
    except Exception:
        return 0


def _safe_cuda_device_name() -> str:
    if not _safe_cuda_available():
        return "cpu"
    try:
        return str(torch.cuda.get_device_properties(0).name)
    except Exception:
        return "cuda"


def _normalize_profile(profile: Optional[Any]) -> Dict[str, Any]:
    if profile is None:
        total_memory = _safe_cuda_total_memory()
        total_memory_gb = float(total_memory) / float(1024**3) if total_memory > 0 else 0.0
        small_device = total_memory == 0 or total_memory_gb <= 8.0
        if total_memory >= 16 * 1024**3:
            preferred_dtype = "bfloat16"
            scale_factor = 1.0
            max_experts_in_memory = len(EXPERT_FIELDS)
        elif total_memory >= 8 * 1024**3:
            preferred_dtype = "float16"
            scale_factor = 0.85
            max_experts_in_memory = min(len(EXPERT_FIELDS), 8)
        elif total_memory > 0:
            preferred_dtype = "float16"
            scale_factor = 0.60
            max_experts_in_memory = min(len(EXPERT_FIELDS), 4)
        else:
            preferred_dtype = "float32"
            scale_factor = 0.50
            max_experts_in_memory = 0
        return {
            "selected_device": "cuda" if total_memory > 0 else "cpu",
            "device_name": _safe_cuda_device_name(),
            "cuda_available": total_memory > 0,
            "total_memory_bytes": total_memory,
            "available_memory_bytes": total_memory,
            "is_small_device": small_device,
            "is_low_memory": small_device,
            "prefer_cpu_offload": small_device,
            "prefer_dynamic_int8": total_memory == 0,
            "prefer_gradient_checkpointing": small_device,
            "preferred_dtype": preferred_dtype,
            "scale_factor": scale_factor,
            "max_experts_in_memory": max_experts_in_memory,
        }
    if hasattr(profile, "as_dict") and callable(profile.as_dict):
        normalized = dict(profile.as_dict())
    elif isinstance(profile, dict):
        normalized = dict(profile)
    else:
        normalized = dict(vars(profile))
    normalized.setdefault("selected_device", normalized.get("device_type", "cpu"))
    normalized.setdefault("device_name", normalized.get("selected_device", "cpu"))
    normalized.setdefault("cuda_available", normalized.get("selected_device") == "cuda")
    normalized.setdefault("total_memory_bytes", 0)
    normalized.setdefault("available_memory_bytes", normalized.get("total_memory_bytes", 0))
    normalized.setdefault("is_small_device", True)
    normalized.setdefault("is_low_memory", normalized.get("is_small_device", True))
    normalized.setdefault(
        "prefer_cpu_offload",
        normalized.get("is_low_memory", True) or normalized.get("selected_device") != "cuda",
    )
    normalized.setdefault(
        "prefer_dynamic_int8",
        normalized.get("selected_device") == "cpu",
    )
    normalized.setdefault(
        "prefer_gradient_checkpointing",
        normalized.get("is_low_memory", True),
    )
    normalized.setdefault(
        "preferred_dtype",
        "float16" if normalized.get("selected_device") == "cuda" else "float32",
    )
    normalized.setdefault("scale_factor", 1.0)
    normalized.setdefault("max_experts_in_memory", 0)
    return normalized


def _module_device(module: nn.Module) -> torch.device:
    try:
        parameter = next(module.parameters())
        return parameter.device
    except StopIteration:
        return torch.device("cpu")


def _module_dtype(module: nn.Module) -> torch.dtype:
    try:
        parameter = next(module.parameters())
        return parameter.dtype
    except StopIteration:
        return torch.float32


def _move_module(module: nn.Module, device: torch.device, dtype: Optional[torch.dtype] = None) -> nn.Module:
    if dtype is None:
        return module.to(device=device)
    return module.to(device=device, dtype=dtype)


def _resolve_expert_hidden_dim(config: "ProMoEConfig") -> int:
    explicit_hidden_dim = int(getattr(config, "expert_hidden_dim", 0) or 0)
    if explicit_hidden_dim > 0:
        return explicit_hidden_dim
    return max(1, int(config.d_model) * int(config.expert_hidden_mult))


def _dtype_from_name(name: str) -> torch.dtype:
    normalized = str(name or "float32").strip().lower()
    if normalized in {"bf16", "bfloat16"}:
        return torch.bfloat16
    if normalized in {"fp16", "float16", "half"}:
        return torch.float16
    return torch.float32


@dataclass
class ProMoEConfig:
    d_model: int = 512
    n_experts: int = 23
    top_k: int = 2
    dropout: float = 0.1
    expert_hidden_mult: int = 4
    expert_hidden_dim: int = 0
    expert_depth: int = 1
    expert_n_layers: int = 6
    expert_n_heads: int = 16
    gate_noise: float = 1.0
    aux_loss_coeff: float = 0.01
    router_temperature: float = 1.0
    utilization_ema_decay: float = 0.95
    device_scale_factor: float = 1.0
    max_experts_in_memory: int = 0
    enable_cpu_offload: bool = True
    enable_dynamic_int8: bool = False
    dynamic_offload: bool = True
    preferred_dtype: str = "float32"

    @classmethod
    def from_moe_config(
        cls,
        config: MoEConfig,
        **overrides: Any,
    ) -> "ProMoEConfig":
        payload = {
            "d_model": int(config.d_model),
            "n_experts": int(config.n_experts),
            "top_k": int(config.top_k),
            "dropout": float(config.dropout),
            "expert_hidden_mult": int(config.expert_hidden_mult),
            "expert_hidden_dim": int(getattr(config, "expert_hidden_dim", 0) or 0),
            "expert_depth": int(getattr(config, "expert_depth", 1) or 1),
            "expert_n_layers": int(getattr(config, "expert_n_layers", 6) or 6),
            "expert_n_heads": int(getattr(config, "expert_n_heads", 16) or 16),
            "gate_noise": float(config.gate_noise),
            "aux_loss_coeff": float(config.aux_loss_coeff),
        }
        payload.update(overrides)
        return cls(**payload)


class ProMoERouter(nn.Module):
    """Sparse noisy top-k router with persistent utilization tracking."""

    def __init__(self, config: ProMoEConfig):
        super().__init__()
        if int(config.d_model) <= 0:
            raise ValueError(f"d_model must be positive, got {config.d_model}")
        if int(config.n_experts) <= 0:
            raise ValueError(f"n_experts must be positive, got {config.n_experts}")
        if int(config.top_k) <= 0 or int(config.top_k) > int(config.n_experts):
            raise ValueError(
                f"top_k must be within [1, n_experts], got top_k={config.top_k}, n_experts={config.n_experts}"
            )
        self.config = config
        self.d_model = int(config.d_model)
        self.n_experts = int(config.n_experts)
        self.top_k = int(config.top_k)
        self.noise_scale = float(config.gate_noise)
        self.temperature = max(1e-6, float(getattr(config, "router_temperature", 1.0) or 1.0))
        self.ema_decay = min(0.9999, max(0.0, float(getattr(config, "utilization_ema_decay", 0.95) or 0.95)))
        self.w_gate = nn.Linear(self.d_model, self.n_experts, bias=False)
        self.w_noise = nn.Linear(self.d_model, self.n_experts, bias=False)
        self.register_buffer("selection_ema", torch.zeros(self.n_experts), persistent=False)
        self.register_buffer("probability_ema", torch.zeros(self.n_experts), persistent=False)
        self.register_buffer("dispatch_count", torch.zeros(self.n_experts), persistent=False)
        self.register_buffer("dispatch_steps", torch.zeros((), dtype=torch.long), persistent=False)
        self.last_route_stats: Dict[str, Any] = {}

    def _compute_logits(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.w_gate(x) / self.temperature
        if self.training and self.noise_scale > 0.0:
            noise_std = F.softplus(self.w_noise(x))
            logits = logits + (
                torch.randn_like(logits) * noise_std * self.noise_scale
            )
        return logits

    def _update_utilization(self, gates: torch.Tensor, probabilities: torch.Tensor) -> None:
        with torch.no_grad():
            selection_fraction = gates.mean(dim=0)
            probability_fraction = probabilities.mean(dim=0)
            active_counts = (gates > 0).sum(dim=0).to(self.dispatch_count.dtype)
            decay = self.ema_decay
            self.selection_ema.mul_(decay).add_(selection_fraction.detach() * (1.0 - decay))
            self.probability_ema.mul_(decay).add_(probability_fraction.detach() * (1.0 - decay))
            self.dispatch_count.add_(active_counts.detach())
            self.dispatch_steps.add_(1)
            self.last_route_stats = {
                "selection_fraction": selection_fraction.detach().cpu(),
                "probability_fraction": probability_fraction.detach().cpu(),
                "dispatch_count": self.dispatch_count.detach().cpu(),
                "dispatch_steps": int(self.dispatch_steps.item()),
            }

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        logits = self._compute_logits(x)
        top_k_logits, top_k_indices = torch.topk(logits, self.top_k, dim=-1)
        top_k_weights = F.softmax(top_k_logits, dim=-1)

        gates = torch.zeros_like(logits)
        gates.scatter_(1, top_k_indices, top_k_weights)

        probabilities = F.softmax(logits, dim=-1)
        aux_loss = self.n_experts * torch.sum(gates.mean(dim=0) * probabilities.mean(dim=0))
        self._update_utilization(gates, probabilities)
        return gates, top_k_indices, aux_loss

    def utilization_summary(self) -> Dict[str, Any]:
        return {
            "dispatch_steps": int(self.dispatch_steps.item()),
            "selection_ema": self.selection_ema.detach().cpu().tolist(),
            "probability_ema": self.probability_ema.detach().cpu().tolist(),
            "dispatch_count": self.dispatch_count.detach().cpu().tolist(),
        }


class ProMoELayer(nn.Module):
    """Classifier-oriented sparse Pro-MoE layer with CPU expert offload."""

    def __init__(self, config: ProMoEConfig, profile: Optional[Any] = None):
        super().__init__()
        self.config = config
        self.profile = _normalize_profile(profile)
        self._grad_checkpoint_enabled = False
        self.hidden_dim = _resolve_expert_hidden_dim(config)
        self.expert_depth = max(1, int(getattr(config, "expert_depth", 1) or 1))
        self.expert_n_layers = max(0, int(getattr(config, "expert_n_layers", 6) or 6))
        self.expert_n_heads = max(1, int(getattr(config, "expert_n_heads", 16) or 16))
        self.router = ProMoERouter(config)
        self.experts = nn.ModuleList(
            [
                SingleExpert(
                    input_dim=int(config.d_model),
                    hidden_dim=self.hidden_dim,
                    dropout=float(config.dropout),
                    depth=self.expert_depth,
                    n_layers=self.expert_n_layers,
                    n_heads=self.expert_n_heads,
                )
                for _ in range(int(config.n_experts))
            ]
        )
        self.output_dropout = nn.Dropout(float(config.dropout))
        self.output_norm = nn.LayerNorm(int(config.d_model))
        self.register_buffer("expert_token_count", torch.zeros(int(config.n_experts)), persistent=False)
        self.register_buffer("forward_steps", torch.zeros((), dtype=torch.long), persistent=False)
        self.expert_device_map: Dict[int, str] = {}
        self.resident_experts: set[int] = set()
        self.compute_device = torch.device(
            "cuda"
            if self.profile.get("selected_device") == "cuda" and _safe_cuda_available()
            else "cpu"
        )
        self.configure_for_device_profile(self.profile)

    def _resolve_resident_budget(self, profile: Dict[str, Any]) -> int:
        explicit_budget = int(getattr(self.config, "max_experts_in_memory", 0) or 0)
        if explicit_budget > 0:
            return max(1, min(explicit_budget, int(self.config.n_experts)))
        hinted_budget = int(profile.get("max_experts_in_memory", 0) or 0)
        if hinted_budget > 0:
            return max(1, min(hinted_budget, int(self.config.n_experts)))
        if self.compute_device.type != "cuda":
            return int(self.config.n_experts)
        total_memory_gb = float(profile.get("total_memory_bytes", 0) or 0) / float(1024**3)
        if total_memory_gb >= 16.0:
            return int(self.config.n_experts)
        if total_memory_gb >= 8.0:
            return min(int(self.config.n_experts), 8)
        if total_memory_gb >= 4.0:
            return min(int(self.config.n_experts), 4)
        return 2

    def configure_for_device_profile(self, profile: Optional[Any]) -> None:
        resolved_profile = _normalize_profile(profile)
        self.profile = resolved_profile
        requested_device = str(resolved_profile.get("selected_device", "cpu") or "cpu").lower()
        if requested_device == "cuda" and _safe_cuda_available():
            self.compute_device = torch.device("cuda")
        else:
            self.compute_device = torch.device("cpu")
        self.resident_experts.clear()
        self.expert_device_map.clear()
        budget = self._resolve_resident_budget(resolved_profile)
        cpu_offload = bool(getattr(self.config, "enable_cpu_offload", True)) and self.compute_device.type == "cuda"
        for expert_index, expert in enumerate(self.experts):
            if cpu_offload and expert_index >= budget:
                target_device = torch.device("cpu")
                target_dtype = torch.float32
            else:
                target_device = self.compute_device
                target_dtype = _module_dtype(expert) if target_device.type == "cuda" else torch.float32
                self.resident_experts.add(expert_index)
            _move_module(expert, device=target_device, dtype=target_dtype)
            self.expert_device_map[expert_index] = str(target_device)

    def _rebalance_expert_devices(self, selected_experts: Iterable[int]) -> None:
        if self.compute_device.type != "cuda":
            return
        if not bool(getattr(self.config, "enable_cpu_offload", True)):
            return
        if not bool(getattr(self.config, "dynamic_offload", True)):
            return
        budget = self._resolve_resident_budget(self.profile)
        if budget >= int(self.config.n_experts):
            return
        selection_scores = self.router.selection_ema.detach().cpu()
        top_ranked = torch.argsort(selection_scores, descending=True).tolist()
        preferred = [int(idx) for idx in top_ranked[:budget] if int(idx) < int(self.config.n_experts)]
        for idx in selected_experts:
            resolved_idx = int(idx)
            if resolved_idx not in preferred:
                preferred.append(resolved_idx)
        desired_residents = set(preferred[:budget])
        if not desired_residents:
            desired_residents = set(range(min(budget, int(self.config.n_experts))))
        for expert_index, expert in enumerate(self.experts):
            target_device = self.compute_device if expert_index in desired_residents else torch.device("cpu")
            target_dtype = _module_dtype(expert) if target_device.type == "cuda" else torch.float32
            current_device = _module_device(expert)
            current_dtype = _module_dtype(expert)
            if current_device != target_device or current_dtype != target_dtype:
                _move_module(expert, device=target_device, dtype=target_dtype)
            self.expert_device_map[expert_index] = str(target_device)
        self.resident_experts = desired_residents

    def _run_expert(self, expert: nn.Module, inputs: torch.Tensor, use_checkpoint: bool) -> torch.Tensor:
        expert_device = _module_device(expert)
        expert_dtype = _module_dtype(expert)
        expert_inputs = inputs.to(device=expert_device)
        if expert_inputs.dtype != expert_dtype and expert_inputs.is_floating_point():
            expert_inputs = expert_inputs.to(expert_dtype)
        if use_checkpoint and expert_device == inputs.device:
            return activation_checkpoint(expert, expert_inputs, use_reentrant=False)
        return expert(expert_inputs)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        gates, top_k_indices, aux_loss = self.router(x)
        selected_experts = torch.unique(top_k_indices).detach().cpu().tolist()
        if int(self.forward_steps.item()) % 32 == 0:
            self._rebalance_expert_devices(selected_experts)
        mixed_output = torch.zeros_like(x)
        use_checkpoint = bool(self._grad_checkpoint_enabled) and self.training and x.requires_grad
        with torch.no_grad():
            self.expert_token_count.add_((gates > 0).sum(dim=0).to(self.expert_token_count.dtype))
            self.forward_steps.add_(1)

        for expert_index in selected_experts:
            resolved_expert_index = int(expert_index)
            expert_gate = gates[:, resolved_expert_index]
            token_mask = expert_gate > 0
            if not bool(token_mask.any().item()):
                continue
            expert_inputs = x[token_mask]
            expert = self.experts[resolved_expert_index]
            expert_output = self._run_expert(expert, expert_inputs, use_checkpoint)
            if expert_output.device != x.device:
                expert_output = expert_output.to(x.device)
            if expert_output.dtype != x.dtype and expert_output.is_floating_point():
                expert_output = expert_output.to(x.dtype)
            gate_weights = expert_gate[token_mask].to(device=x.device, dtype=expert_output.dtype)
            mixed_output[token_mask] += gate_weights.unsqueeze(-1) * expert_output

        return self.output_norm(x + self.output_dropout(mixed_output)), aux_loss

    def utilization_summary(self) -> Dict[str, Any]:
        return {
            "expert_token_count": self.expert_token_count.detach().cpu().tolist(),
            "forward_steps": int(self.forward_steps.item()),
            "resident_experts": sorted(int(index) for index in self.resident_experts),
            "expert_device_map": dict(self.expert_device_map),
            **self.router.utilization_summary(),
        }


class ProMoEClassifier(nn.Module):
    """Sparse Pro-MoE classifier with small-device runtime adaptations."""

    def __init__(
        self,
        config: Optional[ProMoEConfig] = None,
        input_dim: int = 256,
        output_dim: Optional[int] = None,
        *,
        n_experts: Optional[int] = None,
        n_classes: Optional[int] = None,
        top_k: Optional[int] = None,
        dropout: float = 0.1,
        device_profile: Optional[Any] = None,
    ):
        super().__init__()
        auto_place = config is None
        self._profile = _normalize_profile(device_profile)
        if config is None:
            resolved_n_experts = int(n_experts or len(EXPERT_FIELDS) or 23)
            config = ProMoEConfig(
                d_model=max(1, int(input_dim)),
                n_experts=resolved_n_experts,
                top_k=min(int(top_k or 2), resolved_n_experts),
                dropout=float(dropout),
                expert_hidden_mult=4,
                enable_cpu_offload=bool(self._profile.get("prefer_cpu_offload", True)),
                enable_dynamic_int8=bool(self._profile.get("prefer_dynamic_int8", False)),
                device_scale_factor=float(self._profile.get("scale_factor", 1.0) or 1.0),
                max_experts_in_memory=int(self._profile.get("max_experts_in_memory", 0) or 0),
                preferred_dtype=str(self._profile.get("preferred_dtype", "float32") or "float32"),
            )
        self.config = config
        self.input_dim = int(input_dim)
        self.output_dim = int(output_dim if output_dim is not None else (n_classes if n_classes is not None else 2))
        self.n_experts = int(config.n_experts)
        self._active_expert: int | None = None
        self._device = torch.device("cpu")
        self._dtype = torch.float32
        self._preferred_device = torch.device(
            "cuda"
            if self._profile.get("selected_device") == "cuda" and _safe_cuda_available()
            else "cpu"
        )
        self._preferred_dtype = _dtype_from_name(str(getattr(config, "preferred_dtype", "float32") or "float32"))
        if self._preferred_device.type != "cuda":
            self._preferred_dtype = torch.float32
        self._use_grad_checkpoint = bool(self._profile.get("prefer_gradient_checkpointing", False))
        self._grad_checkpoint_enabled = False
        self.input_proj = nn.Linear(self.input_dim, int(config.d_model))
        self.input_norm = nn.LayerNorm(int(config.d_model))
        self.moe = ProMoELayer(config, profile=self._profile)
        self.output_norm = nn.LayerNorm(int(config.d_model))
        self.classifier = nn.Linear(int(config.d_model), self.output_dim)
        self.register_buffer("_aux_loss_zero", torch.tensor(0.0), persistent=False)
        self._last_aux_loss = self._aux_loss_zero
        self._small_device_profile = dict(self._profile)
        target_device = self._preferred_device if auto_place else torch.device("cpu")
        target_dtype = self._preferred_dtype if target_device.type == "cuda" else torch.float32
        self.to(device=target_device, dtype=target_dtype)
        self.configure_for_device_profile(self._profile)
        summary = self.parameter_summary()
        logger.info(
            "ProMoEClassifier initialized: total_params=%s | expert_params=%s | shared_params=%s | expert_hidden_dim=%s | experts=%s | top_k=%s | d_model=%s | device=%s | dtype=%s | cpu_offload=%s | dynamic_int8=%s",
            f"{summary['total_params']:,}",
            f"{summary['expert_params']:,}",
            f"{summary['shared_params']:,}",
            self.moe.hidden_dim,
            int(config.n_experts),
            int(config.top_k),
            int(config.d_model),
            self._device,
            self._dtype,
            bool(getattr(config, "enable_cpu_offload", True)),
            bool(getattr(config, "enable_dynamic_int8", False)),
        )

    def to(self, *args, **kwargs):
        module = super().to(*args, **kwargs)
        try:
            parameter = next(module.parameters())
        except StopIteration:
            return module
        self._device = parameter.device
        self._dtype = parameter.dtype
        return module

    def configure_for_device_profile(self, profile: Optional[Any]) -> None:
        resolved_profile = _normalize_profile(profile)
        self._small_device_profile = dict(resolved_profile)
        if "scale_factor" in resolved_profile:
            self.config.device_scale_factor = float(resolved_profile.get("scale_factor", 1.0) or 1.0)
        if "max_experts_in_memory" in resolved_profile:
            self.config.max_experts_in_memory = int(resolved_profile.get("max_experts_in_memory", 0) or 0)
        if "prefer_cpu_offload" in resolved_profile:
            self.config.enable_cpu_offload = bool(resolved_profile.get("prefer_cpu_offload", True))
        if "prefer_dynamic_int8" in resolved_profile:
            self.config.enable_dynamic_int8 = bool(resolved_profile.get("prefer_dynamic_int8", False))
        if "preferred_dtype" in resolved_profile:
            self.config.preferred_dtype = str(resolved_profile.get("preferred_dtype", "float32") or "float32")
            self._preferred_dtype = _dtype_from_name(self.config.preferred_dtype)
        if self._device.type != "cuda":
            self._preferred_dtype = torch.float32
        self._use_grad_checkpoint = bool(resolved_profile.get("prefer_gradient_checkpointing", self._use_grad_checkpoint))
        self.moe.configure_for_device_profile(resolved_profile)

    def set_active_expert(self, expert_id: Optional[int]) -> None:
        if expert_id is None:
            self._active_expert = None
            return
        resolved_expert_id = int(expert_id)
        if not 0 <= resolved_expert_id < self.n_experts:
            raise ValueError(f"expert_id must be in [0, {self.n_experts - 1}], got {resolved_expert_id}")
        self._active_expert = resolved_expert_id

    def gradient_checkpointing_enable(self) -> None:
        self._grad_checkpoint_enabled = True
        self.moe._grad_checkpoint_enabled = True

    def gradient_checkpointing_disable(self) -> None:
        self._grad_checkpoint_enabled = False
        self.moe._grad_checkpoint_enabled = False

    def _run_single_expert(self, hidden: torch.Tensor, expert_index: int) -> torch.Tensor:
        expert = self.moe.experts[int(expert_index)]
        expert_device = _module_device(expert)
        expert_dtype = _module_dtype(expert)
        expert_inputs = hidden.to(device=expert_device)
        if expert_inputs.dtype != expert_dtype and expert_inputs.is_floating_point():
            expert_inputs = expert_inputs.to(expert_dtype)
        if self._grad_checkpoint_enabled and self.training and hidden.requires_grad and expert_device == hidden.device:
            expert_output = activation_checkpoint(expert, expert_inputs, use_reentrant=False)
        else:
            expert_output = expert(expert_inputs)
        return expert_output.to(device=hidden.device, dtype=hidden.dtype)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.to(self._device)
        if x.dtype != self._dtype and x.is_floating_point():
            x = x.to(self._dtype)
        hidden = self.input_proj(x)
        hidden = self.input_norm(hidden)
        if self._active_expert is not None:
            hidden = self._run_single_expert(hidden, self._active_expert)
            aux_loss = self._aux_loss_zero.to(device=hidden.device, dtype=hidden.dtype)
        else:
            hidden, aux_loss = self.moe(hidden)
        self._last_aux_loss = aux_loss
        hidden = self.output_norm(hidden)
        return self.classifier(hidden)

    def parameter_summary(self) -> Dict[str, int]:
        total_params = sum(parameter.numel() for parameter in self.parameters())
        expert_params = sum(
            parameter.numel()
            for expert in self.moe.experts
            for parameter in expert.parameters()
        )
        return {
            "total_params": int(total_params),
            "expert_params": int(expert_params),
            "shared_params": int(total_params - expert_params),
        }

    def utilization_summary(self) -> Dict[str, Any]:
        return self.moe.utilization_summary()

    @property
    def aux_loss(self) -> torch.Tensor:
        return self._last_aux_loss

    def to_dynamic_int8(self) -> nn.Module:
        quantize_dynamic = _resolve_quantize_dynamic()
        if quantize_dynamic is None:
            logger.warning("Dynamic INT8 quantization unavailable in this torch build")
            fallback_model = ProMoEClassifier(
                config=copy.deepcopy(self.config),
                input_dim=self.input_dim,
                output_dim=self.output_dim,
                device_profile=dict(self._small_device_profile),
            ).cpu().float().eval()
            fallback_model.load_state_dict(
                {
                    key: value.detach().cpu().clone()
                    for key, value in self.state_dict().items()
                },
                strict=True,
            )
            fallback_model.set_active_expert(self._active_expert)
            return fallback_model
        quantizable_model = ProMoEClassifier(
            config=copy.deepcopy(self.config),
            input_dim=self.input_dim,
            output_dim=self.output_dim,
            device_profile=dict(self._small_device_profile),
        ).cpu().float().eval()
        quantizable_model.load_state_dict(
            {
                key: value.detach().cpu().clone()
                for key, value in self.state_dict().items()
            },
            strict=True,
        )
        quantizable_model.set_active_expert(self._active_expert)
        quantized_model = quantize_dynamic(
            quantizable_model,
            {nn.Linear},
            dtype=torch.qint8,
        )
        return quantized_model


class ProMoEModel(ProMoEClassifier):
    """Alias kept for external callers expecting a model-named entry point."""


__all__ = [
    "ProMoEConfig",
    "ProMoERouter",
    "ProMoELayer",
    "ProMoEClassifier",
    "ProMoEModel",
]
