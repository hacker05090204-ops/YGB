"""Test MoE build with reasonable config"""
import os, torch
os.environ['YGB_USE_MOE'] = 'true'
from impl_v1.phase49.moe import MoEClassifier, MoEConfig

# Config for ~100M total (enough to pass gate)
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

print('Building model...')
try:
    model = MoEClassifier(config, input_dim=267, output_dim=5)
    summary = model.parameter_summary()
    print(f'Total params: {summary["total_params"]:,}')
    print(f'Expert params: {summary["expert_params"]:,}')
    print(f'Per-expert: {summary["expert_params"] // 23:,} ({summary["expert_params"] // 23 / 1_000_000:.2f}M)')
    
    if summary["total_params"] >= 100_000_000:
        print('✓ PASS: >= 100M params')
    else:
        print(f'✗ FAIL: {summary["total_params"]:,} < 100M')
        
    # Test forward
    x = torch.randn(2, 267)
    out = model(x)
    print(f'✓ Forward pass: {x.shape} → {out.shape}')
except Exception as e:
    print(f'✗ ERROR: {e}')
    import traceback
    traceback.print_exc()
