"""Check MoE parameter count"""
import os
os.environ['YGB_USE_MOE'] = 'true'
from impl_v1.phase49.moe import MoEClassifier, MoEConfig

# Create config matching training_controller expectations
config = MoEConfig(
    d_model=256,
    n_experts=23,
    top_k=2,
    expert_hidden_mult=2,
    dropout=0.3,
    gate_noise=1.0,
    aux_loss_coeff=0.01
)

# Set expert_hidden_dim to achieve 130M per expert
config.expert_hidden_dim = 2048

model = MoEClassifier(config, input_dim=267, output_dim=5)
summary = model.parameter_summary()
print(f'Total params: {summary["total_params"]:,}')
print(f'Expert params: {summary["expert_params"]:,}')
print(f'Per-expert params: {summary["expert_params"] // 23:,}')
print(f'Shared params: {summary["shared_params"]:,}')
print(f'Target: 130M per expert = 3B total')
print(f'Current per-expert: {summary["expert_params"] // 23 / 1_000_000:.2f}M')

if summary["total_params"] < 100_000_000:
    print('\n*** CRITICAL: Model has < 100M params — needs scaling ***')
else:
    print('\n✓ Model meets 100M+ parameter requirement')
