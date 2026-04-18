from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
from torch.utils.checkpoint import checkpoint as activation_checkpoint

from .expert import SingleExpert
from .moe_architecture import (
    MoEConfig,
    MoEModel,
    MoELayer,
    ExpertFFN,
    MoETransformerBlock,
    ExpertOffloader,
    EXPERT_FIELDS,
    create_moe_config_small,
    create_moe_config_medium,
    create_moe_config_large,
    create_moe_model,
    detect_vram_budget,
    compute_expert_budget,
    run_smoke_test,
)
from .router import MoERouter, NoisyTopKGate
from .pro_moe import (
    ProMoEClassifier,
    ProMoEConfig,
    ProMoELayer,
    ProMoEModel,
    ProMoERouter,
)
from .simple_moe import SimpleMoEClassifier
from .simple_expert import SimpleExpert130M, count_params
from .simple_router import SimpleRouter


logger = logging.getLogger("ygb.moe")


def _resolve_expert_hidden_dim(config: MoEConfig) -> int:
    explicit_hidden_dim = int(getattr(config, "expert_hidden_dim", 0) or 0)
    if explicit_hidden_dim > 0:
        return explicit_hidden_dim
    return max(1, int(config.d_model) * int(config.expert_hidden_mult))


class _SparseMoEClassifierLayer(nn.Module):
    """Single sparse MoE block for classifier-style feature inputs."""

    def __init__(self, config: MoEConfig):
        super().__init__()
        self.config = config
        self._grad_checkpoint_enabled = False
        self.hidden_dim = _resolve_expert_hidden_dim(config)
        self.expert_depth = max(1, int(getattr(config, "expert_depth", 1) or 1))
        self.expert_n_layers = max(0, int(getattr(config, "expert_n_layers", 6) or 6))
        self.expert_n_heads = max(1, int(getattr(config, "expert_n_heads", 16) or 16))
        
        self.router = MoERouter(
            d_model=int(config.d_model),
            n_experts=int(config.n_experts),
            top_k=int(config.top_k),
            noise_scale=float(config.gate_noise),
        )
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

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        gates, _top_k_indices, aux_loss = self.router(x)
        mixed_output = torch.zeros_like(x)
        use_checkpoint = bool(self._grad_checkpoint_enabled) and self.training and x.requires_grad

        for expert_index, expert in enumerate(self.experts):
            expert_gate = gates[:, expert_index]
            token_mask = expert_gate > 0
            if not bool(token_mask.any()):
                continue

            expert_inputs = x[token_mask]
            if use_checkpoint:
                expert_output = activation_checkpoint(
                    expert,
                    expert_inputs,
                    use_reentrant=False,
                )
            else:
                expert_output = expert(expert_inputs)
            mixed_output[token_mask] += (
                expert_gate[token_mask].unsqueeze(-1) * expert_output
            )

        return self.output_norm(x + self.output_dropout(mixed_output)), aux_loss


class MoEClassifier(nn.Module):
    """Classifier-oriented sparse MoE model used by the training controller."""

    def __init__(
        self,
        config: Optional[MoEConfig] = None,
        input_dim: int = 256,
        output_dim: Optional[int] = None,
        *,
        n_experts: Optional[int] = None,
        n_classes: Optional[int] = None,
        top_k: Optional[int] = None,
        dropout: float = 0.1,
    ):
        nn.Module.__init__(self)
        auto_place = config is None
        if config is None:
            resolved_n_experts = int(n_experts or len(EXPERT_FIELDS) or 23)
            config = MoEConfig(
                d_model=max(1, int(input_dim)),
                n_experts=resolved_n_experts,
                top_k=min(int(top_k or 2), resolved_n_experts),
                dropout=float(dropout),
                expert_hidden_mult=4,
            )
        self.config = config
        self.input_dim = int(input_dim)
        self.output_dim = int(output_dim if output_dim is not None else (n_classes if n_classes is not None else 2))
        self.n_experts = int(config.n_experts)
        self._active_expert: int | None = None
        self._device = torch.device("cpu")
        self._dtype = torch.float32
        self._preferred_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._preferred_dtype = torch.float32
        self._use_grad_checkpoint = False
        self._grad_checkpoint_enabled = False
        if self._preferred_device.type == "cuda":
            total_vram = float(torch.cuda.get_device_properties(0).total_memory)
            if total_vram >= 40e9:
                self._preferred_dtype = torch.bfloat16
            elif total_vram >= 16e9:
                self._preferred_dtype = torch.float16
            else:
                self._preferred_dtype = torch.float16
                self._use_grad_checkpoint = True

        self.input_proj = nn.Linear(self.input_dim, int(config.d_model))
        self.input_norm = nn.LayerNorm(int(config.d_model))
        self.moe = _SparseMoEClassifierLayer(config)
        self.output_norm = nn.LayerNorm(int(config.d_model))
        self.classifier = nn.Linear(int(config.d_model), self.output_dim)
        self.register_buffer("_aux_loss_zero", torch.tensor(0.0), persistent=False)
        self._last_aux_loss = self._aux_loss_zero
        target_device = self._preferred_device if auto_place else torch.device("cpu")
        target_dtype = self._preferred_dtype if target_device.type == "cuda" else torch.float32
        self.to(device=target_device, dtype=target_dtype)

        summary = self.parameter_summary()
        logger.info(
            "MoEClassifier initialized: total_params=%s | expert_params=%s | shared_params=%s | expert_hidden_dim=%s | expert_depth=%s | expert_n_layers=%s | expert_n_heads=%s | experts=%s | top_k=%s | d_model=%s | device=%s | dtype=%s | grad_checkpoint=%s",
            f"{summary['total_params']:,}",
            f"{summary['expert_params']:,}",
            f"{summary['shared_params']:,}",
            self.moe.hidden_dim,
            self.moe.expert_depth,
            self.moe.expert_n_layers,
            self.moe.expert_n_heads,
            int(config.n_experts),
            int(config.top_k),
            int(config.d_model),
            self._device,
            self._dtype,
            self._use_grad_checkpoint,
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

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        device = self._device
        x = x.to(device)
        if x.dtype != self._dtype:
            x = x.to(self._dtype)
        hidden = self.input_proj(x)
        hidden = self.input_norm(hidden)
        if self._active_expert is not None:
            expert = self.moe.experts[self._active_expert]
            if self._grad_checkpoint_enabled and self.training and hidden.requires_grad:
                hidden = activation_checkpoint(
                    expert,
                    hidden,
                    use_reentrant=False,
                )
            else:
                hidden = expert(hidden)
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

    @property
    def aux_loss(self) -> torch.Tensor:
        return self._last_aux_loss


MoEBugClassifier = MoEClassifier


__all__ = [
    "MoEConfig",
    "MoEModel",
    "MoELayer",
    "MoEBugClassifier",
    "MoEClassifier",
    "ProMoEClassifier",
    "ProMoEConfig",
    "ProMoELayer",
    "ProMoEModel",
    "ProMoERouter",
    "SimpleMoEClassifier",
    "SimpleExpert130M",
    "SimpleRouter",
    "count_params",
    "SingleExpert",
    "MoERouter",
    "NoisyTopKGate",
    "ExpertFFN",
    "MoETransformerBlock",
    "ExpertOffloader",
    "EXPERT_FIELDS",
    "create_moe_config_small",
    "create_moe_config_medium",
    "create_moe_config_large",
    "create_moe_model",
    "detect_vram_budget",
    "compute_expert_budget",
    "run_smoke_test",
]
