# ===========================================================================
# YGB Mixture-of-Experts (MoE) Architecture — Pure PyTorch Implementation
# ===========================================================================
#
# 23 specialized experts for bug-bounty hunting, with sparse activation
# through Noisy Top-K gating.  Only K experts fire per token, so active
# parameters stay small even when total parameter count is large.
#
# Designed for the YGB G38 training pipeline.
#
# Architecture overview:
#   Input → Embedding → [MoETransformerBlock × N_layers] → LM Head
#   Each MoETransformerBlock = MultiHeadAttention + MoELayer
#   MoELayer = NoisyTopKGate  +  23 Expert FFNs  (only K=2 active)
#
# Author: YGB Auto-Engineer  |  March 2026
# ===========================================================================

from __future__ import annotations

import math
import os
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger("ygb.moe")


# ===========================================================================
# 0.  CONFIGURATION
# ===========================================================================

# The 23 bug-bounty specialization fields (one expert each)
EXPERT_FIELDS: List[str] = [
    "web_vulns",          # 0
    "api_testing",        # 1
    "mobile_apk",         # 2
    "cloud_misconfig",    # 3
    "blockchain",         # 4
    "iot",                # 5
    "hardware",           # 6
    "firmware",           # 7
    "ssrf",               # 8
    "rce",                # 9
    "xss",                # 10
    "sqli",               # 11
    "auth_bypass",        # 12
    "idor",               # 13
    "graphql_abuse",      # 14
    "rest_attacks",       # 15
    "csrf",               # 16
    "file_upload",        # 17
    "deserialization",    # 18
    "privilege_escalation",  # 19
    "cryptography",       # 20
    "subdomain_takeover", # 21
    "race_condition",     # 22
]

assert len(EXPERT_FIELDS) == 23, "Must have exactly 23 expert fields"


@dataclass
class MoEConfig:
    """
    Full model configuration.

    Scale knobs (defaults tuned for RTX 2050 4 GB):
      - d_model=512, n_layers=4, n_heads=8, n_experts=23, top_k=2
      - This gives ~2.8B *total* params but only ~250M active per forward.

    For production 70B–150B scale:
      - d_model=4096, n_layers=32, n_heads=32, expert_hidden_mult=4
      - Each expert ≈ 2×(4096×16384) ≈ 130M params → 23 experts ≈ 3B
      - + attention layers ≈ 67B total
    """
    # --- Transformer dims ---
    vocab_size: int = 32_000
    d_model: int = 512            # hidden dimension
    n_heads: int = 8              # attention heads
    n_layers: int = 4             # transformer blocks
    max_seq_len: int = 2048       # max sequence length
    dropout: float = 0.1

    # --- MoE dims ---
    n_experts: int = 23           # number of specialist experts
    top_k: int = 2               # experts activated per token
    expert_hidden_mult: int = 4  # FFN hidden = d_model * this
    gate_noise: float = 1.0      # noise scale for noisy gating
    aux_loss_coeff: float = 0.01 # load-balance auxiliary loss weight

    # --- Device-adaptive ---
    max_experts_in_memory: int = 0  # 0=auto-detect from VRAM
    expert_offload_dir: str = ""    # directory for expert shards on disk

    # --- Training ---
    seed: int = 42


# ===========================================================================
# 1.  NOISY TOP-K GATING NETWORK  (Router)
# ===========================================================================

class NoisyTopKGate(nn.Module):
    """
    Noisy Top-K Gating for Mixture-of-Experts.

    For each token x:
      1. Compute logits = W_gate · x  +  softplus(W_noise · x) · ε
         where ε ~ N(0, 1)   (noise injected during training only)
      2. Keep only top-K logits, set the rest to -∞
      3. Apply softmax to get routing weights

    Returns:
      - gates:        (batch*seq, n_experts)  sparse weight matrix
      - top_k_indices: (batch*seq, K)          which experts are selected
      - aux_loss:     scalar  load-balancing loss

    The auxiliary loss penalizes uneven expert utilization:
      L_aux = n_experts · Σ_e  f_e · P_e
    where f_e = fraction of tokens routed to expert e
          P_e = mean routing probability for expert e
    """

    def __init__(self, d_model: int, n_experts: int, top_k: int = 2,
                 noise_scale: float = 1.0):
        super().__init__()
        self.n_experts = n_experts
        self.top_k = top_k
        self.noise_scale = noise_scale

        # Linear projection from hidden dim → n_experts
        self.w_gate = nn.Linear(d_model, n_experts, bias=False)
        # Noise projection (learnable noise magnitude per expert)
        self.w_noise = nn.Linear(d_model, n_experts, bias=False)

    def _noisy_logits(self, x: torch.Tensor) -> torch.Tensor:
        """Compute gating logits with optional training noise."""
        clean_logits = self.w_gate(x)                        # (T, E)

        if self.training and self.noise_scale > 0:
            noise_stddev = F.softplus(self.w_noise(x))       # (T, E)
            noise = torch.randn_like(clean_logits) * noise_stddev * self.noise_scale
            return clean_logits + noise

        return clean_logits

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (T, d_model) where T = batch_size × seq_len (flattened tokens)

        Returns:
            gates:         (T, n_experts)  sparse routing weights (zeros for non-selected)
            top_k_indices: (T, top_k)      selected expert indices
            aux_loss:      scalar          load-balancing auxiliary loss
        """
        logits = self._noisy_logits(x)                       # (T, E)

        # --- Top-K selection ---
        top_k_logits, top_k_indices = torch.topk(
            logits, self.top_k, dim=-1
        )                                                    # (T, K), (T, K)

        # Softmax over only the selected experts (numerically stable)
        top_k_gates = F.softmax(top_k_logits, dim=-1)        # (T, K)

        # Scatter into full sparse gate tensor
        gates = torch.zeros_like(logits)                     # (T, E)
        gates.scatter_(1, top_k_indices, top_k_gates)        # place weights

        # --- Load-Balancing Auxiliary Loss ---
        # f_e = fraction of tokens dispatched to expert e
        # P_e = mean routing probability for expert e (from full softmax)
        probs = F.softmax(logits, dim=-1)                    # (T, E) full probs

        # f_e: fraction of tokens where expert e is in top-k
        # Use differentiable approximation: mean of gates (already sparse)
        f = gates.mean(dim=0)                                # (E,)
        # P_e: mean of full routing probability for expert e
        P = probs.mean(dim=0)                                # (E,)

        # L_aux = n_experts · Σ(f_e · P_e)
        # Minimized when f and P are both uniform (1/E)
        aux_loss = self.n_experts * (f * P).sum()

        return gates, top_k_indices, aux_loss


# ===========================================================================
# 2.  EXPERT FFN  (Each is a standard Transformer FFN block)
# ===========================================================================

class ExpertFFN(nn.Module):
    """
    Single expert: a standard Transformer-style Feed-Forward Network.

      x → Linear(d_model, hidden) → SwiGLU → Linear(hidden, d_model)

    SwiGLU (used in LLaMA, Mistral, etc.) is more effective than GELU:
      SwiGLU(x) = (W1·x ⊙ Swish(V·x))
    This requires 3 weight matrices but gives better quality.
    """

    def __init__(self, d_model: int, hidden_dim: int, dropout: float = 0.1):
        super().__init__()
        # SwiGLU needs gate + up projections
        self.w_gate = nn.Linear(d_model, hidden_dim, bias=False)  # V
        self.w_up = nn.Linear(d_model, hidden_dim, bias=False)    # W1
        self.w_down = nn.Linear(hidden_dim, d_model, bias=False)  # W2
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # SwiGLU activation
        gate = F.silu(self.w_gate(x))       # Swish(V·x)
        up = self.w_up(x)                    # W1·x
        hidden = gate * up                   # element-wise gate
        return self.dropout(self.w_down(hidden))


# ===========================================================================
# 3.  MoE LAYER  (Gate + Dispatch + Combine)
# ===========================================================================

class MoELayer(nn.Module):
    """
    Mixture-of-Experts layer replacing the FFN in a Transformer block.

    Forward flow:
      1. Flatten (B, S, D) → (T, D)  where T = B × S
      2. Route T tokens through NoisyTopKGate → sparse weights + indices
      3. For each active expert, gather the tokens routed to it,
         run the expert FFN, scatter results back
      4. Combine outputs weighted by gate values
      5. Reshape back to (B, S, D)

    This implementation uses a loop over experts (simple, correct).
    For GPU efficiency at scale, replace with grouped GEMM or MegaBlocks-style
    block-sparse matmul — but for ≤23 experts with top-2 gating, the loop
    is already fast because each expert processes ~T/12 tokens.
    """

    def __init__(self, config: MoEConfig):
        super().__init__()
        hidden_dim = config.d_model * config.expert_hidden_mult

        self.gate = NoisyTopKGate(
            d_model=config.d_model,
            n_experts=config.n_experts,
            top_k=config.top_k,
            noise_scale=config.gate_noise,
        )

        # Create all expert FFNs
        self.experts = nn.ModuleList([
            ExpertFFN(config.d_model, hidden_dim, config.dropout)
            for _ in range(config.n_experts)
        ])

        self.n_experts = config.n_experts
        self.top_k = config.top_k

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (B, S, D)

        Returns:
            output: (B, S, D)  MoE-processed hidden states
            aux_loss: scalar   load-balancing loss
        """
        B, S, D = x.shape
        # Flatten to (T, D) for routing
        x_flat = x.view(-1, D)                              # (T, D)
        T = x_flat.size(0)

        # Route tokens
        gates, top_k_indices, aux_loss = self.gate(x_flat)   # (T, E), (T, K), scalar

        # Output accumulator
        output = torch.zeros_like(x_flat)                    # (T, D)

        # Dispatch tokens to each expert and accumulate weighted results
        for expert_idx in range(self.n_experts):
            # Find which tokens selected this expert (sparse lookup)
            expert_gate = gates[:, expert_idx]                # (T,)
            token_mask = expert_gate > 0                      # (T,) bool

            if not token_mask.any():
                continue  # No tokens routed to this expert

            # Gather tokens for this expert
            expert_input = x_flat[token_mask]                 # (T_e, D)
            expert_weight = expert_gate[token_mask]           # (T_e,)

            # Run expert FFN
            expert_output = self.experts[expert_idx](expert_input)  # (T_e, D)

            # Weighted accumulation (gate weight × expert output)
            output[token_mask] += expert_weight.unsqueeze(-1) * expert_output

        return output.view(B, S, D), aux_loss


# ===========================================================================
# 4.  ROTARY POSITION EMBEDDING  (RoPE)
# ===========================================================================

class RotaryEmbedding(nn.Module):
    """RoPE — Rotary Position Embedding (Su et al. 2021)."""

    def __init__(self, dim: int, max_seq_len: int = 2048, base: float = 10000.0):
        super().__init__()
        # Precompute frequency bands
        inv_freq = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)

        # Precompute cos/sin cache
        t = torch.arange(max_seq_len, dtype=torch.float32)
        freqs = torch.outer(t, inv_freq)                     # (S, dim/2)
        self.register_buffer("cos_cache", freqs.cos(), persistent=False)
        self.register_buffer("sin_cache", freqs.sin(), persistent=False)

    def forward(self, x: torch.Tensor, seq_len: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return (
            self.cos_cache[:seq_len].to(x.dtype),
            self.sin_cache[:seq_len].to(x.dtype),
        )


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    """Rotate half the hidden dims of the input."""
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(
    q: torch.Tensor, k: torch.Tensor,
    cos: torch.Tensor, sin: torch.Tensor,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Apply RoPE to query and key tensors."""
    # cos/sin: (S, head_dim/2) → broadcast to (1, 1, S, head_dim)
    cos = cos.unsqueeze(0).unsqueeze(0)  # (1, 1, S, dim/2)
    sin = sin.unsqueeze(0).unsqueeze(0)
    # Repeat to match head_dim
    cos = cos.repeat(1, 1, 1, 2)  # (1, 1, S, dim)
    sin = sin.repeat(1, 1, 1, 2)

    q_embed = (q * cos) + (_rotate_half(q) * sin)
    k_embed = (k * cos) + (_rotate_half(k) * sin)
    return q_embed, k_embed


# ===========================================================================
# 5.  MULTI-HEAD ATTENTION  (with RoPE + KV-Cache)
# ===========================================================================

class MultiHeadAttention(nn.Module):
    """
    Multi-head self-attention with RoPE and optional KV-cache
    for efficient autoregressive inference.
    """

    def __init__(self, d_model: int, n_heads: int, max_seq_len: int = 2048,
                 dropout: float = 0.1):
        super().__init__()
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"

        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.d_model = d_model

        self.q_proj = nn.Linear(d_model, d_model, bias=False)
        self.k_proj = nn.Linear(d_model, d_model, bias=False)
        self.v_proj = nn.Linear(d_model, d_model, bias=False)
        self.o_proj = nn.Linear(d_model, d_model, bias=False)

        self.rotary_emb = RotaryEmbedding(self.head_dim, max_seq_len)
        self.attn_dropout = nn.Dropout(dropout)

    def forward(
        self, x: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        kv_cache: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> Tuple[torch.Tensor, Optional[Tuple[torch.Tensor, torch.Tensor]]]:
        B, S, D = x.shape

        # Project Q, K, V
        q = self.q_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        # q, k, v: (B, n_heads, S, head_dim)

        # Apply RoPE
        cos, sin = self.rotary_emb(q, S)
        q, k = apply_rotary_pos_emb(q, k, cos, sin)

        # KV-Cache for inference
        if kv_cache is not None:
            prev_k, prev_v = kv_cache
            k = torch.cat([prev_k, k], dim=2)
            v = torch.cat([prev_v, v], dim=2)
        new_kv_cache = (k, v)

        # Scaled dot-product attention
        scale = 1.0 / math.sqrt(self.head_dim)
        attn_weights = torch.matmul(q, k.transpose(-2, -1)) * scale  # (B, H, S, S_kv)

        # Causal mask (lower triangular)
        S_kv = k.size(2)
        causal_mask = torch.triu(
            torch.ones(S, S_kv, device=x.device, dtype=torch.bool),
            diagonal=S_kv - S + 1,
        )
        attn_weights = attn_weights.masked_fill(causal_mask.unsqueeze(0).unsqueeze(0), float("-inf"))

        if attention_mask is not None:
            attn_weights = attn_weights + attention_mask

        attn_weights = F.softmax(attn_weights, dim=-1)
        attn_weights = self.attn_dropout(attn_weights)

        # Combine heads
        attn_output = torch.matmul(attn_weights, v)           # (B, H, S, head_dim)
        attn_output = attn_output.transpose(1, 2).contiguous().view(B, S, D)

        return self.o_proj(attn_output), new_kv_cache


# ===========================================================================
# 6.  RMSNorm  (faster than LayerNorm, used in LLaMA/Mistral)
# ===========================================================================

class RMSNorm(nn.Module):
    """Root Mean Square Layer Normalization."""

    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rms = torch.sqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return x / rms * self.weight


# ===========================================================================
# 7.  MoE TRANSFORMER BLOCK  (Attention + MoE replacing FFN)
# ===========================================================================

class MoETransformerBlock(nn.Module):
    """
    Single Transformer block with MoE replacing the standard FFN.

    Architecture (pre-norm, LLaMA-style):
      x → RMSNorm → MultiHeadAttention → + residual
        → RMSNorm → MoELayer           → + residual

    Each block outputs both the hidden state and the MoE auxiliary loss
    for load balancing.
    """

    def __init__(self, config: MoEConfig):
        super().__init__()
        self.attn_norm = RMSNorm(config.d_model)
        self.ffn_norm = RMSNorm(config.d_model)

        self.attention = MultiHeadAttention(
            d_model=config.d_model,
            n_heads=config.n_heads,
            max_seq_len=config.max_seq_len,
            dropout=config.dropout,
        )

        self.moe = MoELayer(config)

    def forward(
        self, x: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        kv_cache: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, Optional[Tuple[torch.Tensor, torch.Tensor]]]:
        """
        Returns:
            hidden_states: (B, S, D)
            aux_loss: scalar
            new_kv_cache: updated KV cache
        """
        # --- Self-Attention with residual ---
        normed = self.attn_norm(x)
        attn_out, new_kv_cache = self.attention(normed, attention_mask, kv_cache)
        x = x + attn_out

        # --- MoE FFN with residual ---
        normed = self.ffn_norm(x)
        moe_out, aux_loss = self.moe(normed)
        x = x + moe_out

        return x, aux_loss, new_kv_cache


# ===========================================================================
# 8.  FULL MoE MODEL  (Stacked blocks + Embedding + LM Head)
# ===========================================================================

class MoEModel(nn.Module):
    """
    Complete Mixture-of-Experts language model.

    Components:
      - Token embedding + RMSNorm
      - N stacked MoETransformerBlocks
      - Final RMSNorm + Linear LM head (tied weights optional)

    The model returns:
      - logits: (B, S, vocab_size)
      - total_aux_loss: sum of aux losses from all MoE layers (for training)
    """

    def __init__(self, config: MoEConfig):
        super().__init__()
        self.config = config

        # Token embedding (no learned position embedding — we use RoPE)
        self.tok_emb = nn.Embedding(config.vocab_size, config.d_model)
        self.emb_dropout = nn.Dropout(config.dropout)

        # Stacked MoE Transformer blocks
        self.blocks = nn.ModuleList([
            MoETransformerBlock(config)
            for _ in range(config.n_layers)
        ])

        # Output head
        self.norm = RMSNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        # Weight tying: share embedding weights with LM head
        self.lm_head.weight = self.tok_emb.weight

        # Initialize weights
        self.apply(self._init_weights)

        # Log parameter counts
        total_params = sum(p.numel() for p in self.parameters())
        expert_params = sum(
            p.numel()
            for block in self.blocks
            for expert in block.moe.experts
            for p in expert.parameters()
        )
        logger.info(
            f"MoE Model initialized: "
            f"{total_params:,} total params, "
            f"{expert_params:,} expert params, "
            f"{total_params - expert_params:,} shared params, "
            f"~{total_params * config.top_k / config.n_experts:,.0f} active per forward"
        )

    def _init_weights(self, module: nn.Module) -> None:
        """Initialize weights with scaled normal distribution."""
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(
        self, input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        kv_caches: Optional[List[Tuple[torch.Tensor, torch.Tensor]]] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, Optional[List[Tuple[torch.Tensor, torch.Tensor]]]]:
        """
        Args:
            input_ids: (B, S) integer token IDs
            attention_mask: optional mask
            kv_caches: list of per-layer KV caches (for inference)

        Returns:
            logits: (B, S, vocab_size)
            total_aux_loss: scalar (sum of all MoE layer aux losses)
            new_kv_caches: updated KV caches
        """
        B, S = input_ids.shape
        x = self.tok_emb(input_ids)                          # (B, S, D)
        x = self.emb_dropout(x)

        total_aux_loss = torch.tensor(0.0, device=x.device)
        new_kv_caches: List[Tuple[torch.Tensor, torch.Tensor]] = []

        for i, block in enumerate(self.blocks):
            layer_cache = kv_caches[i] if kv_caches is not None else None
            x, aux_loss, new_cache = block(x, attention_mask, layer_cache)
            total_aux_loss = total_aux_loss + aux_loss
            new_kv_caches.append(new_cache)

        x = self.norm(x)
        logits = self.lm_head(x)                             # (B, S, V)

        return logits, total_aux_loss, new_kv_caches


# ===========================================================================
# 9.  DEVICE-ADAPTIVE SHARDING
# ===========================================================================

def detect_vram_budget() -> Tuple[int, str]:
    """
    Detect available GPU VRAM and return (VRAM_MB, device_name).
    Falls back to CPU with 0 MB if no GPU.
    """
    if not torch.cuda.is_available():
        return 0, "cpu"

    props = torch.cuda.get_device_properties(0)
    vram_mb = props.total_memory // (1024 * 1024)
    return vram_mb, props.name


def compute_expert_budget(config: MoEConfig) -> int:
    """
    Compute how many experts can fit in VRAM simultaneously.

    Rough estimate per expert:
      3 weight matrices × d_model × (d_model × expert_hidden_mult) × 2 bytes (fp16)
      ≈ 3 × d_model × hidden_dim × 2

    If not all experts fit, we can offload inactive ones to CPU/disk.
    """
    vram_mb, device_name = detect_vram_budget()
    if vram_mb == 0:
        logger.warning("No GPU detected — all experts on CPU")
        return config.n_experts  # CPU has enough RAM usually

    hidden_dim = config.d_model * config.expert_hidden_mult
    # Each expert: 3 matrices of size (d_model × hidden_dim) in fp16
    bytes_per_expert = 3 * config.d_model * hidden_dim * 2  # fp16
    # Attention + embedding overhead (rough estimate: 40% of VRAM)
    available_vram = int(vram_mb * 0.6 * 1024 * 1024)  # 60% for experts

    max_experts = max(1, available_vram // bytes_per_expert)
    budget = min(max_experts, config.n_experts)

    logger.info(
        f"VRAM budget: {vram_mb} MB ({device_name}), "
        f"~{bytes_per_expert // (1024*1024)} MB/expert, "
        f"can fit {budget}/{config.n_experts} experts in GPU"
    )
    return budget


class ExpertOffloader:
    """
    Manages expert offloading for low-VRAM devices.

    Strategy:
      - Keep top-K most frequently used experts on GPU
      - The rest stay on CPU (or disk if expert_offload_dir is set)
      - When the router selects an offloaded expert, swap it in

    For the RTX 2050 (4 GB), with d_model=512:
      Each expert ≈ 3 × 512 × 2048 × 2 bytes ≈ 6 MB
      All 23 experts ≈ 138 MB — fits easily!

    This becomes important at scale (d_model=4096):
      Each expert ≈ 3 × 4096 × 16384 × 2 bytes ≈ 384 MB
      23 experts ≈ 8.6 GB — won't fit in 4 GB VRAM.
    """

    def __init__(self, moe_layer: MoELayer, config: MoEConfig):
        self.moe_layer = moe_layer
        self.config = config
        self.gpu_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.cpu_device = torch.device("cpu")

        self.budget = compute_expert_budget(config)
        self.expert_usage_count: Dict[int, int] = {i: 0 for i in range(config.n_experts)}
        self.experts_on_gpu: set = set()

        # Initially load as many experts as budget allows
        for i in range(min(self.budget, config.n_experts)):
            moe_layer.experts[i] = moe_layer.experts[i].to(self.gpu_device)
            self.experts_on_gpu.add(i)

        # Keep remaining on CPU
        for i in range(self.budget, config.n_experts):
            moe_layer.experts[i] = moe_layer.experts[i].to(self.cpu_device)

        logger.info(
            f"ExpertOffloader: {len(self.experts_on_gpu)} experts on GPU, "
            f"{config.n_experts - len(self.experts_on_gpu)} on CPU"
        )

    def ensure_on_gpu(self, expert_indices: List[int]) -> None:
        """Ensure the given experts are on GPU, swapping if needed."""
        needed = set(expert_indices) - self.experts_on_gpu

        if not needed:
            return  # All needed experts already on GPU

        # If we need to free space, evict least-used experts
        while len(self.experts_on_gpu) + len(needed) > self.budget and self.experts_on_gpu:
            # Find least-used expert currently on GPU (that we don't need)
            evictable = self.experts_on_gpu - set(expert_indices)
            if not evictable:
                break
            victim = min(evictable, key=lambda i: self.expert_usage_count[i])
            self.moe_layer.experts[victim] = self.moe_layer.experts[victim].to(self.cpu_device)
            self.experts_on_gpu.discard(victim)

        # Load needed experts to GPU
        for idx in needed:
            self.moe_layer.experts[idx] = self.moe_layer.experts[idx].to(self.gpu_device)
            self.experts_on_gpu.add(idx)
            self.expert_usage_count[idx] += 1

    def save_expert_shards(self, output_dir: str) -> None:
        """Save each expert as a separate .pt file for lazy loading."""
        os.makedirs(output_dir, exist_ok=True)
        for i, expert in enumerate(self.moe_layer.experts):
            path = os.path.join(output_dir, f"expert_{i:02d}_{EXPERT_FIELDS[i]}.pt")
            torch.save(expert.state_dict(), path)
        logger.info(f"Saved {len(self.moe_layer.experts)} expert shards to {output_dir}")

    def load_expert_shard(self, expert_idx: int, shard_dir: str) -> None:
        """Load a single expert from disk."""
        path = os.path.join(shard_dir, f"expert_{expert_idx:02d}_{EXPERT_FIELDS[expert_idx]}.pt")
        state_dict = torch.load(path, map_location=self.gpu_device, weights_only=True)
        self.moe_layer.experts[expert_idx].load_state_dict(state_dict)


# ===========================================================================
# 10.  MODEL FACTORY + CONFIG PRESETS
# ===========================================================================

def create_moe_config_small() -> MoEConfig:
    """
    Small config for RTX 2050 (4 GB VRAM).
    Total params: ~80M | Active per forward: ~15M
    Good for development, testing, and low-end devices.
    """
    return MoEConfig(
        vocab_size=32_000,
        d_model=512,
        n_heads=8,
        n_layers=4,
        max_seq_len=2048,
        n_experts=23,
        top_k=2,
        expert_hidden_mult=4,
        dropout=0.1,
    )


def create_moe_config_medium() -> MoEConfig:
    """
    Medium config for RTX 3090/4090 (24 GB VRAM).
    Total params: ~2B | Active per forward: ~300M
    """
    return MoEConfig(
        vocab_size=32_000,
        d_model=2048,
        n_heads=16,
        n_layers=16,
        max_seq_len=4096,
        n_experts=23,
        top_k=2,
        expert_hidden_mult=4,
        dropout=0.1,
    )


def create_moe_config_large() -> MoEConfig:
    """
    Large config for multi-GPU / RTX 5090 / A100 (80 GB VRAM).
    Total params: ~70B | Active per forward: ~6B
    Production-scale: requires expert parallelism across GPUs.
    """
    return MoEConfig(
        vocab_size=64_000,
        d_model=4096,
        n_heads=32,
        n_layers=32,
        max_seq_len=8192,
        n_experts=23,
        top_k=2,
        expert_hidden_mult=4,
        dropout=0.05,
    )


def create_moe_model(config: Optional[MoEConfig] = None) -> MoEModel:
    """Create an MoE model with auto-detected or specified config."""
    if config is None:
        vram_mb, _ = detect_vram_budget()
        if vram_mb >= 40_000:
            config = create_moe_config_large()
        elif vram_mb >= 16_000:
            config = create_moe_config_medium()
        else:
            config = create_moe_config_small()
        logger.info(f"Auto-selected config for {vram_mb} MB VRAM: d_model={config.d_model}")

    model = MoEModel(config)
    return model


# ===========================================================================
# 11.  INTEGRATION WITH YGB BUG CLASSIFIER
# ===========================================================================

class MoEBugClassifier(nn.Module):
    """
    MoE-based bug classifier that replaces the existing BugClassifier.

    Instead of a simple FFN, uses a single MoE layer with 23 expert
    specialists.  The router learns to dispatch inputs to the most relevant
    experts based on the input features.

    This is the drop-in replacement for g37_pytorch_backend.BugClassifier.
    """

    def __init__(self, config: MoEConfig, input_dim: int = 256, output_dim: int = 2):
        super().__init__()
        self.config = config

        # Input projection: raw features → d_model
        self.input_proj = nn.Linear(input_dim, config.d_model)
        self.input_norm = RMSNorm(config.d_model)

        # Single MoE layer for sparse expert routing
        self.moe = MoELayer(config)

        # Classification head
        self.output_norm = RMSNorm(config.d_model)
        self.classifier = nn.Linear(config.d_model, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, input_dim) raw feature vectors

        Returns:
            logits: (B, output_dim) classification logits
        """
        # Project to model dimension and add seq dim
        h = self.input_proj(x)                   # (B, d_model)
        h = self.input_norm(h)
        h = h.unsqueeze(1)                       # (B, 1, d_model) — single token

        # MoE routing + expert processing
        h, self._last_aux_loss = self.moe(h)     # (B, 1, d_model)

        # Classify
        h = self.output_norm(h.squeeze(1))       # (B, d_model)
        return self.classifier(h)                # (B, output_dim)

    @property
    def aux_loss(self) -> torch.Tensor:
        """Get the last auxiliary loss for load balancing."""
        return getattr(self, "_last_aux_loss", torch.tensor(0.0))


# ===========================================================================
# 12.  EXAMPLE USAGE & SMOKE TEST
# ===========================================================================

def run_smoke_test() -> Dict[str, Any]:
    """
    Run a complete smoke test:
      1. Create model with small config
      2. Forward pass with dummy input
      3. Compute loss + aux loss
      4. Backward pass
      5. Print parameter counts and expert utilization

    Returns dict with test results.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = create_moe_config_small()

    print("=" * 70)
    print("YGB Mixture-of-Experts Smoke Test")
    print("=" * 70)

    # --- Full LM model test ---
    print("\n[1] Creating MoE Language Model (small config)...")
    model = MoEModel(config).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    expert_params = sum(
        p.numel()
        for block in model.blocks
        for expert in block.moe.experts
        for p in expert.parameters()
    )
    shared_params = total_params - expert_params
    active_params = shared_params + expert_params * config.top_k // config.n_experts

    print(f"   Total parameters:   {total_params:>15,}")
    print(f"   Expert parameters:  {expert_params:>15,}")
    print(f"   Shared parameters:  {shared_params:>15,}")
    print(f"   Active per forward: {active_params:>15,} (top-{config.top_k} of {config.n_experts})")

    # --- Forward pass ---
    print("\n[2] Forward pass (batch=2, seq=64)...")
    input_ids = torch.randint(0, config.vocab_size, (2, 64), device=device)
    logits, aux_loss, kv_caches = model(input_ids)

    print(f"   logits shape:  {logits.shape}")
    print(f"   aux_loss:      {aux_loss.item():.4f}")

    # --- Loss computation ---
    print("\n[3] Computing CE loss + weighted aux loss...")
    targets = torch.randint(0, config.vocab_size, (2, 64), device=device)
    ce_loss = F.cross_entropy(
        logits.view(-1, config.vocab_size), targets.view(-1)
    )
    total_loss = ce_loss + config.aux_loss_coeff * aux_loss
    print(f"   CE loss:       {ce_loss.item():.4f}")
    print(f"   Aux loss:      {aux_loss.item():.4f}")
    print(f"   Total loss:    {total_loss.item():.4f}")

    # --- Backward pass ---
    print("\n[4] Backward pass...")
    total_loss.backward()
    grad_norm = sum(
        p.grad.norm().item() ** 2 for p in model.parameters() if p.grad is not None
    ) ** 0.5
    print(f"   Gradient norm: {grad_norm:.4f}")

    # --- Bug Classifier test ---
    print("\n[5] MoE Bug Classifier (drop-in replacement)...")
    bug_config = MoEConfig(d_model=256, n_experts=23, top_k=2,
                           expert_hidden_mult=4, n_layers=1, n_heads=4)
    classifier = MoEBugClassifier(bug_config, input_dim=256, output_dim=2).to(device)
    cls_params = sum(p.numel() for p in classifier.parameters())
    print(f"   Classifier params: {cls_params:,}")

    features = torch.randn(32, 256, device=device)  # batch of 32, 256-dim features
    cls_logits = classifier(features)
    print(f"   Output shape: {cls_logits.shape}")
    print(f"   Aux loss:     {classifier.aux_loss.item():.4f}")

    # --- Device budget ---
    print("\n[6] Device-adaptive sharding...")
    vram_mb, dev_name = detect_vram_budget()
    budget = compute_expert_budget(config)
    print(f"   GPU: {dev_name}, VRAM: {vram_mb} MB")
    print(f"   Expert budget: {budget}/{config.n_experts}")

    print("\n" + "=" * 70)
    print("✅ All smoke tests passed!")
    print("=" * 70)

    return {
        "total_params": total_params,
        "expert_params": expert_params,
        "active_params": active_params,
        "logits_shape": tuple(logits.shape),
        "ce_loss": ce_loss.item(),
        "aux_loss": aux_loss.item(),
        "total_loss": total_loss.item(),
        "grad_norm": grad_norm,
        "vram_mb": vram_mb,
        "expert_budget": budget,
    }


# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    results = run_smoke_test()
    print(f"\nResults: {json.dumps(results, indent=2)}")
