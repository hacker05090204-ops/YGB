from __future__ import annotations

from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


class MoERouter(nn.Module):
    """Input-dependent noisy top-k router for classifier MoE dispatch."""

    def __init__(
        self,
        d_model: int,
        n_experts: int,
        top_k: int = 2,
        noise_scale: float = 1.0,
    ):
        super().__init__()
        if int(d_model) <= 0:
            raise ValueError(f"d_model must be positive, got {d_model}")
        if int(n_experts) <= 0:
            raise ValueError(f"n_experts must be positive, got {n_experts}")
        if int(top_k) <= 0 or int(top_k) > int(n_experts):
            raise ValueError(
                f"top_k must be within [1, n_experts], got top_k={top_k}, n_experts={n_experts}"
            )

        self.d_model = int(d_model)
        self.n_experts = int(n_experts)
        self.top_k = int(top_k)
        self.noise_scale = float(noise_scale)
        self.w_gate = nn.Linear(self.d_model, self.n_experts, bias=False)
        self.w_noise = nn.Linear(self.d_model, self.n_experts, bias=False)

    def _compute_logits(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.w_gate(x)
        if self.training and self.noise_scale > 0.0:
            noise_std = F.softplus(self.w_noise(x))
            logits = logits + (
                torch.randn_like(logits) * noise_std * self.noise_scale
            )
        return logits

    def forward(
        self, x: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        logits = self._compute_logits(x)
        top_k_logits, top_k_indices = torch.topk(logits, self.top_k, dim=-1)
        top_k_weights = F.softmax(top_k_logits, dim=-1)

        gates = torch.zeros_like(logits)
        gates.scatter_(1, top_k_indices, top_k_weights)

        full_probabilities = F.softmax(logits, dim=-1)
        expert_importance = gates.mean(dim=0)
        expert_probability = full_probabilities.mean(dim=0)
        aux_loss = self.n_experts * torch.sum(expert_importance * expert_probability)
        return gates, top_k_indices, aux_loss


NoisyTopKGate = MoERouter
