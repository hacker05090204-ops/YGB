"""
global_storage_cap.py — Global 110GB Storage Cap (Phase 1)

Single global pool replaces per-field limits.
All shards belong to one pool.
Cascade: compress→SSD→NAS→Gmail encrypted archive.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GLOBAL_CAP_GB = 110.0


@dataclass
class PoolShard:
    """A shard in the global pool."""
    shard_id: str
    field_name: str
    size_bytes: int
    tier: str           # ssd / nas / gmail / compressed
    state: str          # active / cold / compressed / archived
    last_accessed: float
    replica_count: int = 1


@dataclass
class EvictionCascade:
    """Cascade eviction plan."""
    compress: List[str]
    move_to_ssd: List[str]
    move_to_nas: List[str]
    move_to_gmail: List[str]
    bytes_to_free: int
    current_gb: float
    cap_gb: float


@dataclass
class GlobalCapReport:
    """Status of global storage pool."""
    within_cap: bool
    used_gb: float
    cap_gb: float
    usage_pct: float
    shard_count: int
    field_breakdown: Dict[str, float]   # field → GB
    eviction: Optional[EvictionCascade]
    timestamp: str = ""


class GlobalStorageCap:
    """Enforces a single global 110GB storage cap.

    Replaces per-field namespace limits.
    Cascade eviction: compress → owner SSD → NAS → Gmail encrypted.
    """

    def __init__(self, cap_gb: float = GLOBAL_CAP_GB):
        self.cap_gb = cap_gb
        self.cap_bytes = int(cap_gb * 1024 ** 3)
        self._pool: Dict[str, PoolShard] = {}

    def register_shard(self, shard: PoolShard):
        """Register a shard to global pool."""
        self._pool[shard.shard_id] = shard

    def add_shard(
        self,
        shard_id: str,
        field_name: str,
        size_bytes: int,
        last_accessed: float = 0.0,
    ) -> bool:
        """Add shard to pool. Returns False if would exceed cap."""
        current = self._active_bytes()
        if current + size_bytes > self.cap_bytes:
            logger.warning(
                f"[GLOBAL_CAP] Shard {shard_id[:12]}... rejected: "
                f"would exceed {self.cap_gb}GB cap"
            )
            return False

        self._pool[shard_id] = PoolShard(
            shard_id=shard_id,
            field_name=field_name,
            size_bytes=size_bytes,
            tier="ssd",
            state="active",
            last_accessed=last_accessed,
        )
        return True

    def check_cap(self) -> GlobalCapReport:
        """Check if pool is within global cap."""
        used = self._active_bytes()
        used_gb = used / (1024 ** 3)
        pct = (used_gb / self.cap_gb * 100) if self.cap_gb > 0 else 0

        # Field breakdown
        breakdown: Dict[str, float] = {}
        for s in self._pool.values():
            if s.state in ('active', 'cold'):
                breakdown[s.field_name] = breakdown.get(s.field_name, 0) + s.size_bytes / (1024 ** 3)

        within = used <= self.cap_bytes
        eviction = None if within else self._cascade_plan(used - self.cap_bytes)

        report = GlobalCapReport(
            within_cap=within,
            used_gb=round(used_gb, 4),
            cap_gb=self.cap_gb,
            usage_pct=round(pct, 2),
            shard_count=len(self._pool),
            field_breakdown={k: round(v, 4) for k, v in breakdown.items()},
            eviction=eviction,
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if within else "✗"
        logger.info(
            f"[GLOBAL_CAP] {icon} {used_gb:.2f}GB / {self.cap_gb}GB "
            f"({pct:.1f}%) — {len(self._pool)} shards"
        )
        return report

    def _cascade_plan(self, excess_bytes: int) -> EvictionCascade:
        """Create cascade eviction plan.

        Order: compress cold → move to SSD owner → NAS → Gmail encrypted.
        """
        active = [
            s for s in self._pool.values()
            if s.state in ('active', 'cold')
        ]
        active.sort(key=lambda s: s.last_accessed)

        compress, to_ssd, to_nas, to_gmail = [], [], [], []
        freed = 0

        for shard in active:
            if freed >= excess_bytes:
                break

            if shard.state == 'cold' and shard.tier == 'ssd':
                compress.append(shard.shard_id)
                freed += shard.size_bytes // 4  # ~75% compression
            elif shard.replica_count >= 2:
                to_nas.append(shard.shard_id)
                freed += shard.size_bytes
            else:
                to_ssd.append(shard.shard_id)
                freed += shard.size_bytes // 2

        # If still not enough, archive to Gmail
        if freed < excess_bytes:
            for shard in active:
                if freed >= excess_bytes:
                    break
                if shard.shard_id not in compress + to_nas + to_ssd:
                    to_gmail.append(shard.shard_id)
                    freed += shard.size_bytes

        return EvictionCascade(
            compress=compress,
            move_to_ssd=to_ssd,
            move_to_nas=to_nas,
            move_to_gmail=to_gmail,
            bytes_to_free=excess_bytes,
            current_gb=self._active_bytes() / (1024 ** 3),
            cap_gb=self.cap_gb,
        )

    def evict_shard(self, shard_id: str, target_tier: str):
        """Move shard to target tier."""
        if shard_id in self._pool:
            self._pool[shard_id].tier = target_tier
            self._pool[shard_id].state = (
                "compressed" if target_tier == "compressed"
                else "archived" if target_tier in ("nas", "gmail")
                else "active"
            )

    def get_field_usage(self, field_name: str) -> float:
        """Get GB used by a specific field."""
        return sum(
            s.size_bytes for s in self._pool.values()
            if s.field_name == field_name and s.state in ('active', 'cold')
        ) / (1024 ** 3)

    def _active_bytes(self) -> int:
        return sum(
            s.size_bytes for s in self._pool.values()
            if s.state in ('active', 'cold')
        )

    @property
    def used_gb(self) -> float:
        return self._active_bytes() / (1024 ** 3)

    @property
    def shard_count(self) -> int:
        return len(self._pool)
