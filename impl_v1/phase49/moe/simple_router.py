"""Simplified router for orchestrator's MoE"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class SimpleRouter(nn.Module):
    """Learned gating network. Routes each input to top-K experts.
    Uses real input features — NOT random routing."""
    
    def __init__(self, input_dim: int = 267, n_experts: int = 23, top_k: int = 2):
        super().__init__()
        self.n_experts = n_experts
        self.top_k = top_k
        
        self.gate = nn.Sequential(
            nn.Linear(input_dim, 512),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(512, n_experts),
        )
    
    def forward(self, x: torch.Tensor):
        # x: (batch, input_dim)
        if x.dim() > 2:
            x_flat = x.mean(dim=1)  # pool if sequence
        else:
            x_flat = x
        
        logits = self.gate(x_flat)
        
        # Top-K routing with load balancing
        top_k_logits, top_k_indices = torch.topk(logits, self.top_k, dim=-1)
        top_k_weights = F.softmax(top_k_logits, dim=-1)
        
        return top_k_indices, top_k_weights, logits
