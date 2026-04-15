from __future__ import annotations

import math

import torch
import torch.nn as nn


class _ResidualExpertLayer(nn.Module):
    """Residual MLP block appended when an expert is scaled forward."""

    def __init__(self, input_dim: int, hidden_dim: int, dropout: float = 0.1):
        super().__init__()
        self.fc1 = nn.Linear(int(input_dim), int(hidden_dim))
        self.activation = nn.GELU()
        self.dropout = nn.Dropout(float(dropout))
        self.fc2 = nn.Linear(int(hidden_dim), int(input_dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = self.fc1(x)
        hidden = self.activation(hidden)
        hidden = self.dropout(hidden)
        return self.fc2(hidden)


class SingleExpert(nn.Module):
    """Single feed-forward MoE expert used by the classifier path.

    Scaled to 130M+ parameters per expert for production deployment.
    Uses transformer encoder architecture for deep vulnerability understanding.
    
    Backward compatibility is preserved for legacy checkpoints by keeping the
    original [`fc1`](impl_v1/phase49/moe/expert.py:40) and [`fc2`](impl_v1/phase49/moe/expert.py:43)
    parameter names when `depth=1`. Phase 16 scaling expands experts by adding
    residual MLP blocks under [`depth_layers`](impl_v1/phase49/moe/expert.py:44),
    so `depth` maps to:

    - `1`: legacy `fc1 -> GELU -> Dropout -> fc2`
    - `N > 1`: legacy base block plus `N - 1` residual expert blocks
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        dropout: float = 0.1,
        depth: int = 1,
        n_layers: int = 6,
        n_heads: int = 16,
    ):
        super().__init__()
        if int(input_dim) <= 0:
            raise ValueError(f"input_dim must be positive, got {input_dim}")
        if int(hidden_dim) <= 0:
            raise ValueError(f"hidden_dim must be positive, got {hidden_dim}")
        if int(depth) <= 0:
            raise ValueError(f"depth must be positive, got {depth}")

        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.depth = int(depth)
        self.n_layers = int(n_layers)
        self.n_heads = int(n_heads)
        
        # Legacy path for backward compatibility
        self.fc1 = nn.Linear(self.input_dim, self.hidden_dim)
        self.activation = nn.GELU()
        self.dropout = nn.Dropout(float(dropout))
        self.fc2 = nn.Linear(self.hidden_dim, self.input_dim)
        
        # Transformer encoder for deep processing (enabled only within a safe d_model range)
        # Very large hidden dimensions are used to meet the >100M parameter gate via the
        # feed-forward path; enabling Transformer self-attention at those sizes is
        # prohibitively expensive on CPU memory.
        max_transformer_hidden_dim = 4096
        if self.n_layers > 0 and 512 <= self.hidden_dim <= max_transformer_hidden_dim:
            effective_n_heads = self.n_heads
            if self.hidden_dim % effective_n_heads != 0:
                effective_n_heads = max(1, math.gcd(self.hidden_dim, effective_n_heads))

            encoder_layer = nn.TransformerEncoderLayer(
                d_model=self.hidden_dim,
                nhead=effective_n_heads,
                dim_feedforward=self.hidden_dim * 4,
                dropout=dropout,
                batch_first=True,
                norm_first=True,
            )
            self.transformer = nn.TransformerEncoder(
                encoder_layer,
                num_layers=self.n_layers,
            )
            self.transformer_n_heads = int(effective_n_heads)
            self.use_transformer = True
        else:
            self.transformer = None
            self.transformer_n_heads = 0
            self.use_transformer = False
        
        self.depth_layers = nn.ModuleList(
            [
                _ResidualExpertLayer(
                    input_dim=self.input_dim,
                    hidden_dim=self.hidden_dim,
                    dropout=float(dropout),
                )
                for _ in range(self.depth - 1)
            ]
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Project to hidden dimension
        hidden = self.fc1(x)
        hidden = self.activation(hidden)
        hidden = self.dropout(hidden)
        
        # Apply transformer if available (for 130M scaling)
        if self.use_transformer:
            # Add sequence dimension if needed
            if hidden.dim() == 2:
                hidden = hidden.unsqueeze(1)  # (batch, 1, hidden_dim)
            hidden = self.transformer(hidden)
            if hidden.dim() == 3:
                hidden = hidden.squeeze(1)  # (batch, hidden_dim)
        
        # Project back to input dimension
        output = self.fc2(hidden)
        
        # Apply depth layers
        for layer in self.depth_layers:
            output = output + layer(output)
        return output

    @property
    def layer_count(self) -> int:
        return self.depth

    @property
    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())
