"""Simplified MoE for orchestrator - 130M per expert target"""

import torch
import torch.nn as nn
from .simple_expert import SimpleExpert130M, count_params
from .simple_router import SimpleRouter
import logging

logger = logging.getLogger("ygb.simple_moe")

N_EXPERTS = 23
TARGET_PARAMS_PER_EXPERT = 130_430_000  # 130.43M


class SimpleMoEClassifier(nn.Module):
    """Mixture of Experts classifier for YBG - Orchestrator version.
    23 experts × 130.43M params = ~3B total.
    Each expert specializes in different vulnerability fields."""
    
    FIELD_NAMES = [
        "web_xss", "web_sqli", "web_csrf", "web_ssrf", "web_idor",
        "web_auth_bypass", "api_rest", "api_graphql", "api_broken_auth",
        "mobile_android", "mobile_ios", "mobile_apk",
        "cloud_aws", "cloud_azure", "cloud_gcp",
        "blockchain_smart_contract", "iot_firmware", "iot_hardware",
        "network_rce", "network_overflow", "crypto_weak",
        "supply_chain", "general_vuln",
    ]
    
    def __init__(
        self,
        n_experts: int = N_EXPERTS,
        input_dim: int = 267,
        hidden_dim: int = 2048,
        n_layers: int = 6,
        n_heads: int = 16,
        n_classes: int = 5,
        top_k: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.n_experts = n_experts
        self.top_k = top_k
        self.input_dim = input_dim
        
        self.router = SimpleRouter(input_dim, n_experts, top_k)
        self.experts = nn.ModuleList([
            SimpleExpert130M(input_dim, hidden_dim, n_layers, n_heads, dropout, n_classes)
            for _ in range(n_experts)
        ])
        
        total = count_params(self)
        per_expert = count_params(self.experts[0])
        logger.info(
            "SimpleMoE: %d experts × %dM = %dM total params",
            n_experts, per_expert//1_000_000, total//1_000_000
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.shape[0]
        top_k_indices, top_k_weights, _ = self.router(x)
        
        # Aggregate expert outputs
        output = torch.zeros(
            batch_size, self.experts[0].classifier[-1].out_features,
            device=x.device, dtype=x.dtype
        )
        
        for k in range(self.top_k):
            expert_indices = top_k_indices[:, k]
            weights = top_k_weights[:, k].unsqueeze(1)
            
            for i in range(batch_size):
                expert_idx = expert_indices[i].item()
                expert_out = self.experts[expert_idx](x[i:i+1])
                output[i] += weights[i] * expert_out[0]
        
        return output
    
    def get_expert_params(self) -> int:
        return count_params(self.experts[0])
    
    def set_active_expert(self, expert_id: int):
        """For single-expert training mode."""
        assert 0 <= expert_id < self.n_experts
        self._active_expert = expert_id
    
    @property
    def field_names(self):
        return self.FIELD_NAMES[:self.n_experts]
