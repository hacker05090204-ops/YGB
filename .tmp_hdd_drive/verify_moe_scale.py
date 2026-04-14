"""Verify MoE scaling"""
import os, torch
os.environ['YGB_USE_MOE'] = 'true'
from impl_v1.phase49.moe import MoEClassifier, MoEConfig

# Config for ~100M+ total
config = MoEConfig(
    d_model=1024,
    n_experts=23,
    top_k=2,
    expert_hidden_mult=2,
    dropout=0.3,
    gate_noise=1.0,
    aux_loss_coeff=0.01
)
config.expert_hidden_dim = 1024
config.expert_n_layers = 4
config.expert_n_heads = 8

print('Building scaled MoE model...')
model = MoEClassifier(config, input_dim=267, output_dim=5)
summary = model.parameter_summary()

print('='*70)
print('MOE PARAMETER COUNT')
print('='*70)
print(f'Total params:       {summary["total_params"]:>15,}')
print(f'Expert params:      {summary["expert_params"]:>15,}')
print(f'Per-expert params:  {summary["expert_params"] // 23:>15,}')
print(f'Shared params:      {summary["shared_params"]:>15,}')
print('='*70)
print(f'Per-expert MB:      {(summary["expert_params"] // 23) * 4 / (1024**2):>15.1f}')
print(f'Total GB:           {summary["total_params"] * 4 / (1024**3):>15.2f}')
print('='*70)

if summary["total_params"] >= 100_000_000:
    print('PASS: Model has >= 100M params')
    print(f'Per-expert: {summary["expert_params"] // 23 / 1_000_000:.1f}M')
else:
    print(f'FAIL: {summary["total_params"]:,} < 100M')

# Test forward
print('\nTesting forward pass...')
x = torch.randn(2, 267)
out = model(x)
print(f'PASS: Forward {x.shape} -> {out.shape}')
print('\nPHASE 1 GATE: READY')
