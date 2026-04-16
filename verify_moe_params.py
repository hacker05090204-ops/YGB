"""Verify MoE parameter count"""
import os
os.environ['YGB_USE_MOE'] = 'true'

try:
    from impl_v1.phase49.moe import MoEClassifier, MoEConfig
    
    # Create MoE with orchestrator's target specs
    config = MoEConfig(
        d_model=256,
        n_experts=23,
        top_k=2,
        expert_hidden_mult=2,
        dropout=0.3,
        gate_noise=1.0,
        aux_loss_coeff=0.01,
    )
    
    model = MoEClassifier(config, input_dim=267, output_dim=5)
    
    total_params = sum(p.numel() for p in model.parameters())
    summary = model.parameter_summary()
    
    per_expert = summary['expert_params'] // 23
    
    print(f"✓ MoE Class: {type(model).__name__}")
    print(f"✓ Total params: {total_params:,} ({total_params/1e6:.1f}M)")
    print(f"✓ Expert params: {summary['expert_params']:,} ({summary['expert_params']/1e6:.1f}M)")
    print(f"✓ Per expert: {per_expert:,} ({per_expert/1e6:.1f}M)")
    print(f"✓ Shared params: {summary['shared_params']:,}")
    
    if total_params > 100_000_000:
        print(f"\n✅ PHASE 1 GATE: PASS - MoE has {total_params/1e6:.1f}M params (>100M required)")
    else:
        print(f"\n❌ PHASE 1 GATE: FAIL - MoE has only {total_params/1e6:.1f}M params (<100M required)")
        print(f"   Need to increase expert size to reach 130M per expert")
        
except Exception as e:
    print(f"❌ MoE verification failed: {e}")
    import traceback
    traceback.print_exc()
