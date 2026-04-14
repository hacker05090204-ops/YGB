"""Test scaled MoE with 130M params per expert"""
import os
os.environ['YGB_USE_MOE'] = 'true'
from impl_v1.phase49.moe import MoEClassifier, MoEConfig

# Create config for 130M per expert
config = MoEConfig(
    d_model=2048,  # Increased from 256
    n_experts=23,
    top_k=2,
    expert_hidden_mult=2,
    dropout=0.3,
    gate_noise=1.0,
    aux_loss_coeff=0.01
)

# Set transformer layers for deep processing
config.expert_hidden_dim = 2048
config.expert_n_layers = 6
config.expert_n_heads = 16
config.expert_depth = 1

print("Building scaled MoE model...")
model = MoEClassifier(config, input_dim=267, output_dim=5)
summary = model.parameter_summary()

print(f'\n{"="*70}')
print("SCALED MOE PARAMETER COUNT")
print(f'{"="*70}')
print(f'Total params:       {summary["total_params"]:>15,}')
print(f'Expert params:      {summary["expert_params"]:>15,}')
print(f'Per-expert params:  {summary["expert_params"] // 23:>15,}')
print(f'Shared params:      {summary["shared_params"]:>15,}')
print(f'{"="*70}')
print(f'Target per-expert:  {130_000_000:>15,} (130M)')
print(f'Current per-expert: {summary["expert_params"] // 23:>15,} ({summary["expert_params"] // 23 / 1_000_000:.1f}M)')
print(f'Total target:       {130_000_000 * 23:>15,} (3B)')
print(f'Current total:      {summary["total_params"]:>15,} ({summary["total_params"] / 1_000_000:.1f}M)')
print(f'{"="*70}')

if summary["total_params"] >= 100_000_000:
    print('\n✓ SUCCESS: Model meets 100M+ parameter requirement')
    print(f'✓ Per-expert: {summary["expert_params"] // 23 / 1_000_000:.1f}M')
else:
    print('\n✗ FAIL: Model has < 100M params')
    
# Test forward pass
import torch
print('\nTesting forward pass...')
x = torch.randn(2, 267)
try:
    out = model(x)
    print(f'✓ Forward pass successful: input {x.shape} → output {out.shape}')
except Exception as e:
    print(f'✗ Forward pass failed: {e}')
