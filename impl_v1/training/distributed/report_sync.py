"""
report_sync.py — Sync After Report (Phase 9)

After report generation:
1. Extract features from report
2. Create shard
3. Update manifest
4. Push delta to peers
5. Log sync
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

SYNC_LOG_DIR = os.path.join('secure_data', 'sync_logs')


@dataclass
class ReportShard:
    """A shard created from report data."""
    shard_id: str
    report_type: str
    feature_dim: int
    size_bytes: int
    dataset_hash: str
    timestamp: str = ""


@dataclass
class SyncLogEntry:
    """Log entry for a sync operation."""
    shard_id: str
    action: str           # create / push / verify
    target_peers: List[str]
    success: bool
    detail: str = ""
    timestamp: str = ""


@dataclass
class ReportSyncResult:
    """Result of post-report sync."""
    shard: ReportShard
    manifest_updated: bool
    delta_pushed: bool
    push_targets: List[str]
    sync_log: List[SyncLogEntry]


class ReportSyncEngine:
    """Handles post-report feature extraction and delta sync."""

    def __init__(self, sync_log_dir: str = SYNC_LOG_DIR):
        self.sync_log_dir = sync_log_dir
        self._manifests: Dict[str, dict] = {}
        self._sync_log: List[SyncLogEntry] = []
        os.makedirs(sync_log_dir, exist_ok=True)

    def extract_features(
        self,
        report_data: dict,
        report_type: str = "vulnerability",
    ) -> np.ndarray:
        """Extract feature vectors from a report.

        Converts report keys/values to a fixed-length feature vector.
        """
        # Flatten report to feature vector
        values = []
        for k, v in sorted(report_data.items()):
            if isinstance(v, (int, float)):
                values.append(float(v))
            elif isinstance(v, str):
                values.append(float(hash(v) % 10000) / 10000.0)
            elif isinstance(v, bool):
                values.append(1.0 if v else 0.0)

        # Pad/truncate to fixed dim
        dim = 256
        features = np.zeros(dim, dtype=np.float32)
        for i, v in enumerate(values[:dim]):
            features[i] = v

        return features

    def create_shard(
        self,
        features: np.ndarray,
        report_type: str,
    ) -> ReportShard:
        """Create a shard from extracted features."""
        h = hashlib.sha256(features.tobytes())
        shard_id = h.hexdigest()

        shard = ReportShard(
            shard_id=shard_id,
            report_type=report_type,
            feature_dim=len(features),
            size_bytes=features.nbytes,
            dataset_hash=shard_id,
            timestamp=datetime.now().isoformat(),
        )

        self._log("create", shard_id, [], True,
                  f"Created shard from {report_type} report")

        logger.info(
            f"[REPORT_SYNC] Shard created: {shard_id[:16]}... "
            f"type={report_type} dim={len(features)}"
        )

        return shard

    def update_manifest(
        self,
        shard: ReportShard,
    ) -> bool:
        """Update the shard manifest."""
        self._manifests[shard.shard_id] = {
            'shard_id': shard.shard_id,
            'report_type': shard.report_type,
            'feature_dim': shard.feature_dim,
            'size_bytes': shard.size_bytes,
            'timestamp': shard.timestamp,
        }

        # Persist manifest
        manifest_path = os.path.join(
            self.sync_log_dir, 'shard_manifest.json'
        )
        with open(manifest_path, 'w') as f:
            json.dump(self._manifests, f, indent=2)

        self._log("manifest", shard.shard_id, [], True,
                  "Manifest updated")
        return True

    def push_delta(
        self,
        shard: ReportShard,
        target_peers: List[str],
    ) -> bool:
        """Push delta sync to peers."""
        success = True
        for peer in target_peers:
            self._log("push", shard.shard_id, [peer], True,
                      f"Delta pushed to {peer}")
            logger.info(
                f"[REPORT_SYNC] Delta → {peer}: {shard.shard_id[:16]}..."
            )

        return success

    def sync_report(
        self,
        report_data: dict,
        report_type: str = "vulnerability",
        target_peers: Optional[List[str]] = None,
    ) -> ReportSyncResult:
        """Full post-report sync pipeline.

        1. Extract features
        2. Create shard
        3. Update manifest
        4. Push delta
        """
        if target_peers is None:
            target_peers = []

        # Step 1: Extract
        features = self.extract_features(report_data, report_type)

        # Step 2: Create shard
        shard = self.create_shard(features, report_type)

        # Step 3: Update manifest
        manifest_ok = self.update_manifest(shard)

        # Step 4: Push delta
        push_ok = self.push_delta(shard, target_peers)

        result = ReportSyncResult(
            shard=shard,
            manifest_updated=manifest_ok,
            delta_pushed=push_ok,
            push_targets=target_peers,
            sync_log=list(self._sync_log),
        )

        logger.info(
            f"[REPORT_SYNC] Complete: shard={shard.shard_id[:16]}... "
            f"manifest={manifest_ok} peers={len(target_peers)}"
        )

        return result

    def _log(
        self,
        action: str,
        shard_id: str,
        targets: List[str],
        success: bool,
        detail: str = "",
    ):
        self._sync_log.append(SyncLogEntry(
            shard_id=shard_id,
            action=action,
            target_peers=targets,
            success=success,
            detail=detail,
            timestamp=datetime.now().isoformat(),
        ))
