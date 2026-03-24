"""Unified leader DDP training entrypoint.

Leader-mode orchestration is routed through the canonical training core rather
than maintaining a second standalone training implementation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from training_core.entrypoints import run_leader_ddp_main


@dataclass
class LeaderDDPConfig:
    leader_node: str = "RTX2050"
    follower_node: str = "RTX3050"
    rank: int = 0
    world_size: int = 2
    backend: str = "nccl"
    master_addr: str = "127.0.0.1"
    master_port: int = 29500
    input_dim: int = 256
    hidden_dim: int = 512
    num_classes: int = 2
    num_epochs: int = 3
    base_batch_size: int = 512
    base_lr: float = 0.001
    gradient_clip: float = 1.0
    seed: int = 42
    num_samples: int = 8000
    cosine_lr: bool = True


def main():
    result = run_leader_ddp_main(LeaderDDPConfig())
    if result is not None:
        print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
