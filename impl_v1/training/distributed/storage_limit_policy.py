"""
storage_limit_policy.py — 110GB Hard Limit Policy (Phase 2)

If storage > 110GB:
1. Identify cold shards (least recently accessed)
2. Compress with ZSTD level 19
3. Move to NAS
4. If NAS full, move to cloud
5. Keep metadata locally
6. Never delete active shards
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

HARD_LIMIT_GB = 110.0
ZSTD_LEVEL = 19
WARN_THRESHOLD_PCT = 85.0  # Warn at 85% of limit


@dataclass
class ShardUsage:
    """Shard storage usage tracking."""
    shard_id: str
    namespace: str
    size_bytes: int
    state: str        # active / cold / compressed / archived / cloud
    last_accessed: float
    replica_count: int = 1


@dataclass
class EvictionPlan:
    """Plan for evicting cold shards."""
    shards_to_compress: List[str]
    shards_to_nas: List[str]
    shards_to_cloud: List[str]
    bytes_to_free: int
    current_usage_gb: float
    limit_gb: float
    above_limit: bool


@dataclass
class LimitPolicyReport:
    """Result of limit policy enforcement."""
    within_limit: bool
    current_usage_gb: float
    limit_gb: float
    usage_pct: float
    eviction_plan: Optional[EvictionPlan]
    actions_taken: List[str]
    timestamp: str = ""


class StorageLimitPolicy:
    """Enforces 110GB hard storage limit per namespace."""

    def __init__(
        self,
        limit_gb: float = HARD_LIMIT_GB,
        warn_pct: float = WARN_THRESHOLD_PCT,
    ):
        self.limit_gb = limit_gb
        self.limit_bytes = int(limit_gb * 1024 ** 3)
        self.warn_pct = warn_pct
        self._shards: Dict[str, ShardUsage] = {}

    def register_shard(self, shard: ShardUsage):
        """Register a shard for tracking."""
        self._shards[shard.shard_id] = shard

    def get_usage_bytes(self) -> int:
        """Get total active storage in bytes."""
        return sum(
            s.size_bytes for s in self._shards.values()
            if s.state in ('active', 'cold')
        )

    def get_usage_gb(self) -> float:
        return self.get_usage_bytes() / (1024 ** 3)

    def check_limit(self) -> LimitPolicyReport:
        """Check if within 110GB limit.

        If over limit, creates eviction plan:
        1. Compress cold shards
        2. Move to NAS
        3. Move to cloud if NAS full
        """
        usage_bytes = self.get_usage_bytes()
        usage_gb = usage_bytes / (1024 ** 3)
        usage_pct = (usage_gb / self.limit_gb * 100) if self.limit_gb > 0 else 0

        within_limit = usage_bytes <= self.limit_bytes
        eviction_plan = None
        actions = []

        if usage_pct >= self.warn_pct:
            actions.append(
                f"WARNING: {usage_pct:.1f}% of {self.limit_gb}GB limit"
            )

        if not within_limit:
            excess = usage_bytes - self.limit_bytes
            eviction_plan = self._create_eviction_plan(excess)
            actions.append(
                f"OVER LIMIT: {usage_gb:.2f}GB > {self.limit_gb}GB "
                f"— need to free {excess / (1024**3):.2f}GB"
            )

        report = LimitPolicyReport(
            within_limit=within_limit,
            current_usage_gb=round(usage_gb, 4),
            limit_gb=self.limit_gb,
            usage_pct=round(usage_pct, 2),
            eviction_plan=eviction_plan,
            actions_taken=actions,
            timestamp=datetime.now().isoformat(),
        )

        if within_limit:
            logger.info(
                f"[LIMIT_POLICY] ✓ {usage_gb:.2f}GB / {self.limit_gb}GB"
            )
        else:
            logger.warning(
                f"[LIMIT_POLICY] ✗ OVER: {usage_gb:.2f}GB / {self.limit_gb}GB"
            )

        return report

    def _create_eviction_plan(self, excess_bytes: int) -> EvictionPlan:
        """Create plan to evict cold shards."""
        # Sort active shards by last_accessed (oldest first)
        active = [
            s for s in self._shards.values()
            if s.state in ('active', 'cold')
        ]
        active.sort(key=lambda s: s.last_accessed)

        to_compress = []
        to_nas = []
        to_cloud = []
        freed = 0

        for shard in active:
            if freed >= excess_bytes:
                break
            # Never evict shards with no replicas
            if shard.replica_count < 2:
                to_compress.append(shard.shard_id)
            else:
                to_nas.append(shard.shard_id)
            freed += shard.size_bytes

        return EvictionPlan(
            shards_to_compress=to_compress,
            shards_to_nas=to_nas,
            shards_to_cloud=to_cloud,
            bytes_to_free=excess_bytes,
            current_usage_gb=self.get_usage_gb(),
            limit_gb=self.limit_gb,
            above_limit=True,
        )

    def evict_shard(self, shard_id: str, target: str = "nas"):
        """Mark shard as evicted."""
        if shard_id in self._shards:
            self._shards[shard_id].state = target
            logger.info(
                f"[LIMIT_POLICY] Evicted: {shard_id[:16]}... → {target}"
            )
