"""Simplified expert for orchestrator's 130M target.
This is a NEW implementation alongside the existing expert.py"""

import torch
import torch.nn as nn
from typing import Optional


class SimpleExpert130M(nn.Module):
    """One expert in the MoE ensemble.
    130.43M parameters per expert.
    Designed for CVE/vulnerability intelligence classification.
    Architecture: transformer encoder + classification head."""
    
    def __init__(
        self,
        input_dim: int = 267,      # 256 base + 11 domain features
        hidden_dim: int = 2048,    # large hidden for 130M target
        n_layers: int = 6,
        n_heads: int = 16,
        dropout: float = 0.1,
        n_classes: int = 5,        # CRITICAL/HIGH/MEDIUM/LOW/INFO
        max_seq_len: int = 512,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        
        # Input projection
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.input_norm = nn.LayerNorm(hidden_dim)
        
        # Transformer encoder layers
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=n_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            norm_first=True,   # pre-norm for stability
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=n_layers,
        )
        
        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 4, n_classes),
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, input_dim) or (batch, seq_len, input_dim)
        if x.dim() == 2:
            x = x.unsqueeze(1)  # add seq dim: (batch, 1, input_dim)
        
        x = self.input_proj(x)
        x = self.input_norm(x)
        x = self.transformer(x)
        x = x.mean(dim=1)   # pool over sequence
        return self.classifier(x)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
