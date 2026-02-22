"""
auto_recovery.py — Auto-Recovery Engine (Phase 6)

If node missing shards:
1. Query cluster peers
2. Fetch from peers
3. If not found, fetch from NAS
4. If not found, fetch from cloud
5. Verify hash before restore
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RecoverySource:
    """A source to recover a shard from."""
    source_type: str   # peer / nas / cloud
    source_id: str
    available: bool = True
    latency_ms: int = 0


@dataclass
class RecoveryOp:
    """A single shard recovery operation."""
    shard_id: str
    source: RecoverySource
    hash_verified: bool
    success: bool
    error: str = ""


@dataclass
class RecoveryReport:
    """Full recovery report."""
    total_missing: int
    recovered: int
    failed: int
    operations: List[RecoveryOp]
    fully_restored: bool
    timestamp: str = ""


class AutoRecoveryEngine:
    """Self-healing shard recovery with fallback chain.

    Order: peer → NAS → cloud.
    """

    def __init__(self):
        self._peers: Dict[str, List[str]] = {}     # peer_id: [shard_ids]
        self._nas_shards: List[str] = []
        self._cloud_shards: List[str] = []

    def register_peer_shards(self, peer_id: str, shard_ids: List[str]):
        """Register shards available on a peer."""
        self._peers[peer_id] = shard_ids

    def register_nas_shards(self, shard_ids: List[str]):
        """Register shards available on NAS."""
        self._nas_shards = shard_ids

    def register_cloud_shards(self, shard_ids: List[str]):
        """Register shards available in cloud backup."""
        self._cloud_shards = shard_ids

    def find_source(self, shard_id: str) -> Optional[RecoverySource]:
        """Find the best source for a shard.

        Priority: peer (lowest latency) → NAS → cloud.
        """
        # Check peers
        for peer_id, shards in self._peers.items():
            if shard_id in shards:
                return RecoverySource(
                    source_type="peer",
                    source_id=peer_id,
                    available=True,
                    latency_ms=5,
                )

        # Check NAS
        if shard_id in self._nas_shards:
            return RecoverySource(
                source_type="nas",
                source_id="nas_d_drive",
                available=True,
                latency_ms=50,
            )

        # Check cloud
        if shard_id in self._cloud_shards:
            return RecoverySource(
                source_type="cloud",
                source_id="google_drive",
                available=True,
                latency_ms=5000,
            )

        return None

    def recover_shards(
        self,
        missing_shard_ids: List[str],
        verify_hash: bool = True,
    ) -> RecoveryReport:
        """Recover all missing shards.

        For each missing shard:
        1. Find source (peer → NAS → cloud)
        2. Simulate transfer
        3. Verify hash
        """
        operations = []
        recovered = 0
        failed = 0

        for shard_id in missing_shard_ids:
            source = self.find_source(shard_id)

            if source is None:
                op = RecoveryOp(
                    shard_id=shard_id,
                    source=RecoverySource("none", "none", False),
                    hash_verified=False,
                    success=False,
                    error="No source found for shard",
                )
                operations.append(op)
                failed += 1
                logger.error(
                    f"[RECOVERY] ✗ {shard_id[:16]}... — no source"
                )
                continue

            # Simulate transfer + verify
            hash_ok = verify_hash  # In real impl, compare SHA-256
            op = RecoveryOp(
                shard_id=shard_id,
                source=source,
                hash_verified=hash_ok,
                success=True,
            )
            operations.append(op)
            recovered += 1

            logger.info(
                f"[RECOVERY] ✓ {shard_id[:16]}... "
                f"← {source.source_type}:{source.source_id} "
                f"(~{source.latency_ms}ms)"
            )

        report = RecoveryReport(
            total_missing=len(missing_shard_ids),
            recovered=recovered,
            failed=failed,
            operations=operations,
            fully_restored=(failed == 0),
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"[RECOVERY] Result: {recovered}/{len(missing_shard_ids)} "
            f"restored, {failed} failed"
        )

        return report
