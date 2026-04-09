# MoE package
from .moe_architecture import (
    MoEConfig,
    MoEModel,
    MoELayer,
    MoEBugClassifier,
    NoisyTopKGate,
    ExpertFFN,
    MoETransformerBlock,
    ExpertOffloader,
    EXPERT_FIELDS,
    create_moe_config_small,
    create_moe_config_medium,
    create_moe_config_large,
    create_moe_model,
    detect_vram_budget,
    compute_expert_budget,
    run_smoke_test,
)


class MoEClassifier(MoEBugClassifier):
    """Backward-compatible alias for the MoE bug classifier."""


__all__ = [
    "MoEConfig",
    "MoEModel",
    "MoELayer",
    "MoEBugClassifier",
    "MoEClassifier",
    "NoisyTopKGate",
    "ExpertFFN",
    "MoETransformerBlock",
    "ExpertOffloader",
    "EXPERT_FIELDS",
    "create_moe_config_small",
    "create_moe_config_medium",
    "create_moe_config_large",
    "create_moe_model",
    "detect_vram_budget",
    "compute_expert_budget",
    "run_smoke_test",
]
