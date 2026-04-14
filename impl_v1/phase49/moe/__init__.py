from __future__ import annotations

import logging
from typing import Dict, Tuple

import torch
import torch.nn as nn

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

        for expert_index, expert in enumerate(self.experts):
            expert_gate = gates[:, expert_index]
            token_mask = expert_gate > 0
            if not bool(token_mask.any()):
                continue

            expert_output = expert(x[token_mask])
            mixed_output[token_mask] += (
                expert_gate[token_mask].unsqueeze(-1) * expert_output
            )

        return self.output_norm(x + self.output_dropout(mixed_output)), aux_loss


class MoEClassifier(nn.Module):
    """Classifier-oriented sparse MoE model used by the training controller."""

    def __init__(self, config: MoEConfig, input_dim: int = 256, output_dim: int = 2):
        nn.Module.__init__(self)
        self.config = config
        self.input_dim = int(input_dim)
        self.output_dim = int(output_dim)

        self.input_proj = nn.Linear(self.input_dim, int(config.d_model))
        self.input_norm = nn.LayerNorm(int(config.d_model))
        self.moe = _SparseMoEClassifierLayer(config)
        self.output_norm = nn.LayerNorm(int(config.d_model))
        self.classifier = nn.Linear(int(config.d_model), self.output_dim)
        self.register_buffer("_aux_loss_zero", torch.tensor(0.0), persistent=False)
        self._last_aux_loss = self._aux_loss_zero

        summary = self.parameter_summary()
        logger.info(
            "MoEClassifier initialized: total_params=%s | expert_params=%s | shared_params=%s | expert_hidden_dim=%s | expert_depth=%s | expert_n_layers=%s | expert_n_heads=%s | experts=%s | top_k=%s | d_model=%s",
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
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = self.input_proj(x)
        hidden = self.input_norm(hidden)
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
