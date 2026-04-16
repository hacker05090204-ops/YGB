"""Test current MoE parameter count"""
import os
os.environ['YGB_USE_MOE'] = 'true'

from impl_v1.phase49.moe import MoEClassifier, MoEConfig

# Create a test config similar to what training_controller uses
config = MoEConfig(
    d_model=256,
    n_experts=23,
    top_k=2,
    expert_hidden_mult=2,
    dropout=0.3,
    gate_noise=1.0,
    aux_loss_coeff=0.01,
)

# Set expert_hidden_dim to achieve 130M per expert
# Target: 130M per expert × 23 = ~3B total
# Let's try different hidden dims
for expert_hidden_dim in [2048, 3072, 4096]:
    setattr(config, 'expert_hidden_dim', expert_hidden_dim)
    setattr(config, 'expert_n_layers', 6)
    setattr(config, 'expert_n_heads', 16)
    
    model = MoEClassifier(config, input_dim=267, output_dim=5)
    summary = model.parameter_summary()
    
    total_params = summary['total_params']
    expert_params = summary['expert_params']
    per_expert = expert_params // 23
    
    print(f"\nHidden dim: {expert_hidden_dim}")
    print(f"  Total params: {total_params:,} ({total_params/1e6:.1f}M)")
    print(f"  Expert params: {expert_params:,} ({expert_params/1e6:.1f}M)")
    print(f"  Per expert: {per_expert:,} ({per_expert/1e6:.1f}M)")
    print(f"  Shared params: {summary['shared_params']:,}")
    
    if per_expert >= 130_000_000:
        print(f"  ✓ TARGET REACHED: {per_expert/1e6:.1f}M per expert")
        break
