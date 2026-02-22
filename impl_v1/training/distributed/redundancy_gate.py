"""
redundancy_gate.py — Zero-Data-Loss Rule (Phase 8)

Training allowed ONLY if:
- 3 cluster copies exist, OR
- 2 cluster + 1 NAS copy

Abort training if redundancy < required.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

MIN_CLUSTER_COPIES = 3
MIN_CLUSTER_PLUS_NAS = (2, 1)  # 2 cluster + 1 NAS


@dataclass
class ShardRedundancy:
    """Redundancy state for a single shard."""
    shard_id: str
    cluster_copies: int
    nas_copies: int
    cloud_copies: int
    meets_policy: bool


@dataclass
class RedundancyReport:
    """Report on redundancy compliance."""
    training_allowed: bool
    total_shards: int
    compliant_shards: int
    non_compliant_shards: int
    violations: List[str]
    shard_details: List[ShardRedundancy]
    timestamp: str = ""


class RedundancyGate:
    """Enforces zero-data-loss redundancy before training.

    Training blocked unless every active shard has:
    - ≥3 cluster copies, OR
    - ≥2 cluster + ≥1 NAS copy
    """

    def __init__(
        self,
        min_cluster: int = MIN_CLUSTER_COPIES,
        min_cluster_nas: Tuple[int, int] = MIN_CLUSTER_PLUS_NAS,
    ):
        self.min_cluster = min_cluster
        self.min_cluster_nas = min_cluster_nas
        self._shards: Dict[str, ShardRedundancy] = {}

    def register_shard(
        self,
        shard_id: str,
        cluster_copies: int = 0,
        nas_copies: int = 0,
        cloud_copies: int = 0,
    ):
        """Register a shard with its redundancy counts."""
        meets = self._check_shard_policy(
            cluster_copies, nas_copies,
        )

        self._shards[shard_id] = ShardRedundancy(
            shard_id=shard_id,
            cluster_copies=cluster_copies,
            nas_copies=nas_copies,
            cloud_copies=cloud_copies,
            meets_policy=meets,
        )

    def _check_shard_policy(
        self,
        cluster: int,
        nas: int,
    ) -> bool:
        """Check if a shard meets redundancy requirements.

        Allowed if:
        - cluster ≥ 3, OR
        - cluster ≥ 2 AND nas ≥ 1
        """
        if cluster >= self.min_cluster:
            return True
        if (cluster >= self.min_cluster_nas[0] and
                nas >= self.min_cluster_nas[1]):
            return True
        return False

    def check_training_allowed(self) -> RedundancyReport:
        """Check if training should proceed.

        Returns RedundancyReport. Training blocked if ANY shard
        doesn't meet policy.
        """
        violations = []
        compliant = 0
        non_compliant = 0

        for sid, shard in self._shards.items():
            if shard.meets_policy:
                compliant += 1
            else:
                non_compliant += 1
                violations.append(
                    f"Shard {sid[:16]}...: "
                    f"cluster={shard.cluster_copies} "
                    f"nas={shard.nas_copies} "
                    f"— needs ≥3 cluster or ≥2+1NAS"
                )

        allowed = non_compliant == 0 and len(self._shards) > 0

        report = RedundancyReport(
            training_allowed=allowed,
            total_shards=len(self._shards),
            compliant_shards=compliant,
            non_compliant_shards=non_compliant,
            violations=violations,
            shard_details=list(self._shards.values()),
            timestamp=datetime.now().isoformat(),
        )

        if allowed:
            logger.info(
                f"[REDUNDANCY] ✓ Training ALLOWED: "
                f"{compliant}/{len(self._shards)} shards compliant"
            )
        else:
            logger.error(
                f"[REDUNDANCY] ✗ Training BLOCKED: "
                f"{non_compliant} non-compliant shards"
            )
            for v in violations:
                logger.error(f"  {v}")

        return report
