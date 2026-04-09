from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.scale = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rms = x.pow(2).mean(dim=-1, keepdim=True).add(self.eps).rsqrt()
        return x * rms * self.scale


class SwiGLUFeedForward(nn.Module):
    def __init__(self, dim: int, hidden_dim: int):
        super().__init__()
        self.gate = nn.Linear(dim, hidden_dim)
        self.value = nn.Linear(dim, hidden_dim)
        self.proj = nn.Linear(hidden_dim, dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(F.silu(self.gate(x)) * self.value(x))


class FlashAttentionMixer(nn.Module):
    def __init__(self, dim: int, num_heads: int = 4, use_flash_attention: bool = True):
        super().__init__()
        if dim % max(1, num_heads) != 0:
            raise ValueError(f"dim={dim} must be divisible by num_heads={num_heads}")
        self.dim = dim
        self.num_heads = max(1, int(num_heads))
        self.head_dim = dim // self.num_heads
        self.use_flash_attention = bool(use_flash_attention)
        self.qkv = nn.Linear(dim, dim * 3)
        self.proj = nn.Linear(dim, dim)

    @property
    def flash_available(self) -> bool:
        return bool(hasattr(F, "scaled_dot_product_attention"))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, tokens, channels = x.shape
        qkv = self.qkv(x).view(batch, tokens, 3, self.num_heads, self.head_dim)
        q, k, v = qkv.unbind(dim=2)
        q = q.permute(0, 2, 1, 3)
        k = k.permute(0, 2, 1, 3)
        v = v.permute(0, 2, 1, 3)

        if self.use_flash_attention and self.flash_available and x.is_cuda:
            attn = F.scaled_dot_product_attention(q, k, v, dropout_p=0.0, is_causal=False)
        else:
            scale = 1.0 / math.sqrt(float(self.head_dim))
            scores = torch.matmul(q, k.transpose(-2, -1)) * scale
            weights = torch.softmax(scores, dim=-1)
            attn = torch.matmul(weights, v)

        attn = attn.permute(0, 2, 1, 3).reshape(batch, tokens, channels)
        return self.proj(attn)


class OptimizedTrainingModel(nn.Module):
    def __init__(
        self,
        *,
        input_dim: int,
        hidden_dim: int,
        num_classes: int,
        attention_heads: int = 4,
        token_dim: int = 32,
        use_flash_attention: bool = True,
        gradient_checkpointing: bool = False,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.gradient_checkpointing = bool(gradient_checkpointing)
        self.token_dim = self._select_token_dim(input_dim=input_dim, requested_dim=token_dim)
        self.num_tokens = max(1, math.ceil(input_dim / self.token_dim))
        self.padded_input_dim = self.num_tokens * self.token_dim

        self.token_proj = nn.Linear(self.token_dim, hidden_dim)
        self.token_dropout = nn.Dropout(dropout)
        self.attn_norm = RMSNorm(hidden_dim)
        self.attn = FlashAttentionMixer(hidden_dim, num_heads=attention_heads, use_flash_attention=use_flash_attention)
        self.attn_dropout = nn.Dropout(dropout)
        self.ffn_norm = RMSNorm(hidden_dim)
        self.ffn = SwiGLUFeedForward(hidden_dim, hidden_dim * 2)
        self.ffn_dropout = nn.Dropout(dropout)
        self.output_norm = RMSNorm(hidden_dim)
        self.output_dropout = nn.Dropout(dropout)
        self.classifier_dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_dim, num_classes)

    @staticmethod
    def _select_token_dim(*, input_dim: int, requested_dim: int) -> int:
        candidates = [requested_dim, 64, 32, 16, 8, 4, 2, 1]
        for candidate in candidates:
            if candidate > 0 and input_dim % candidate == 0:
                return int(candidate)
        return max(1, min(int(requested_dim), int(input_dim)))

    @property
    def flash_attention_enabled(self) -> bool:
        return bool(self.attn.use_flash_attention and self.attn.flash_available)

    def set_gradient_checkpointing(self, enabled: bool) -> None:
        self.gradient_checkpointing = bool(enabled)

    def _mix_tokens(self, tokens: torch.Tensor) -> torch.Tensor:
        tokens = tokens + self.attn_dropout(self.attn(self.attn_norm(tokens)))
        tokens = tokens + self.ffn_dropout(self.ffn(self.ffn_norm(tokens)))
        return self.output_dropout(self.output_norm(tokens))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.size(-1) < self.padded_input_dim:
            x = F.pad(x, (0, self.padded_input_dim - x.size(-1)))
        elif x.size(-1) > self.padded_input_dim:
            x = x[..., : self.padded_input_dim]

        tokens = x.view(x.size(0), self.num_tokens, self.token_dim)
        tokens = self.token_dropout(self.token_proj(tokens))
        if self.gradient_checkpointing and self.training and tokens.requires_grad:
            tokens = checkpoint(self._mix_tokens, tokens, use_reentrant=False)
        else:
            tokens = self._mix_tokens(tokens)
        pooled = self.classifier_dropout(tokens.mean(dim=1))
        return self.classifier(pooled)
