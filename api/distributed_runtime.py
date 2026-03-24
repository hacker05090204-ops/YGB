"""Distributed coordination primitives for the YGB backend.

This module provides lightweight cluster coordination using durable manifests,
lease-based leader election, checkpoint barriers, replicated state, shared
memory exchange, anomaly detection, and tiered deduplicated storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import socket
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass(slots=True)
class LeaderLease:
    leader_id: str
    term: int
    expires_at: float


class FileLock:
    """Simple file lock based on exclusive creation."""

    def __init__(self, path: Path, timeout: float = 3.0, poll_interval: float = 0.05):
        self.path = path
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._handle = None

    async def __aenter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = self.path.open("x", encoding="utf-8")
                self._handle.write(str(os.getpid()))
                self._handle.flush()
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError(f"Timed out acquiring file lock {self.path}")
                await asyncio.sleep(self.poll_interval)

    async def __aexit__(self, exc_type, exc, tb):
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


class TieredStorageManager:
    """RAM -> NVMe -> backup storage with global blob deduplication."""

    def __init__(self, root_dir: Path, ram_items: int = 64) -> None:
        self.root_dir = root_dir
        self.ram_items = ram_items
        self.nvme_dir = root_dir / "nvme"
        self.cloud_dir = Path(
            os.getenv("YGB_CLOUD_BACKUP_DIR", str(root_dir / "cloud_backup"))
        )
        self.manifest_dir = root_dir / "manifests"
        self._ram_cache: OrderedDict[str, bytes] = OrderedDict()
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        for directory in (
            self.root_dir,
            self.nvme_dir,
            self.cloud_dir,
            self.manifest_dir,
        ):
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)

    async def store_bytes(
        self,
        *,
        namespace: str,
        payload: bytes,
        filename: Optional[str] = None,
        backup: bool = True,
    ) -> dict[str, Any]:
        blob_hash = hashlib.sha256(payload).hexdigest()
        suffix = Path(filename or "blob.bin").suffix or ".bin"
        blob_name = f"{blob_hash}{suffix}"
        nvme_path = self.nvme_dir / blob_name
        async with self._lock:
            self._ram_cache[blob_hash] = payload
            self._ram_cache.move_to_end(blob_hash)
            while len(self._ram_cache) > self.ram_items:
                self._ram_cache.popitem(last=False)

        if not nvme_path.exists():
            await asyncio.to_thread(nvme_path.write_bytes, payload)

        backup_path = self.cloud_dir / blob_name
        if backup and not backup_path.exists():
            try:
                await asyncio.to_thread(shutil.copy2, nvme_path, backup_path)
            except Exception:
                backup_path = self.cloud_dir / blob_name

        manifest = {
            "namespace": namespace,
            "blob_hash": blob_hash,
            "filename": filename or blob_name,
            "nvme_path": str(nvme_path),
            "backup_path": str(backup_path) if backup else None,
            "size_bytes": len(payload),
            "stored_at": _now_iso(),
        }
        manifest_path = self.manifest_dir / f"{namespace}_{blob_hash}.json"
        await asyncio.to_thread(
            manifest_path.write_text,
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        return manifest

    async def store_file(
        self,
        *,
        namespace: str,
        file_path: Path,
        backup: bool = True,
    ) -> dict[str, Any]:
        payload = await asyncio.to_thread(file_path.read_bytes)
        return await self.store_bytes(
            namespace=namespace,
            payload=payload,
            filename=file_path.name,
            backup=backup,
        )


class DistributedClusterCoordinator:
    """Shared file-backed cluster coordination layer."""

    def __init__(
        self, root_dir: Optional[Path] = None, node_id: Optional[str] = None
    ) -> None:
        self.root_dir = root_dir or (
            Path(__file__).parent.parent / "reports" / "cluster"
        )
        self.node_id = node_id or os.getenv(
            "YGB_NODE_ID", f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        )
        self.node_ttl_seconds = float(os.getenv("YGB_NODE_TTL_SECONDS", "20"))
        self.barrier_timeout_seconds = float(
            os.getenv("YGB_CHECKPOINT_BARRIER_TIMEOUT_SECONDS", "15")
        )
        self.heartbeat_interval_seconds = float(
            os.getenv("YGB_CLUSTER_HEARTBEAT_SECONDS", "5")
        )
        self.nodes_dir = self.root_dir / "nodes"
        self.leader_dir = self.root_dir / "leader"
        self.state_dir = self.root_dir / "state"
        self.checkpoint_dir = self.root_dir / "checkpoints"
        self.memory_dir = self.root_dir / "memory"
        self.anomaly_dir = self.root_dir / "anomalies"
        self.storage = TieredStorageManager(self.root_dir / "storage")
        self._lease: Optional[LeaderLease] = None
        self._last_anomalies: list[dict[str, Any]] = []
        self._last_state_hash: str = ""

    async def startup(self) -> None:
        for directory in (
            self.root_dir,
            self.nodes_dir,
            self.leader_dir,
            self.state_dir,
            self.checkpoint_dir,
            self.memory_dir,
            self.anomaly_dir,
        ):
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        await self.storage.startup()
        await self.heartbeat({"status": "startup"})
        await self.ensure_leader()

    async def shutdown(self) -> None:
        node_manifest = self.nodes_dir / f"{self.node_id}.json"
        try:
            await asyncio.to_thread(node_manifest.unlink, missing_ok=True)
        except Exception:
            pass

    async def heartbeat(self, metadata: Optional[dict[str, Any]] = None) -> None:
        payload = {
            "node_id": self.node_id,
            "heartbeat_at": _now_iso(),
            "expires_at": time.time() + self.node_ttl_seconds,
            "metadata": metadata or {},
        }
        await asyncio.to_thread(
            (self.nodes_dir / f"{self.node_id}.json").write_text,
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    async def active_nodes(self) -> list[dict[str, Any]]:
        now = time.time()
        nodes = []
        for manifest_path in await asyncio.to_thread(
            lambda: list(self.nodes_dir.glob("*.json"))
        ):
            try:
                raw = await asyncio.to_thread(manifest_path.read_text, encoding="utf-8")
                payload = json.loads(raw)
                if float(payload.get("expires_at", 0.0)) >= now:
                    nodes.append(payload)
            except Exception:
                continue
        return nodes

    async def ensure_leader(self) -> LeaderLease:
        async with FileLock(self.leader_dir / "leader.lock"):
            lease_path = self.leader_dir / "lease.json"
            current = None
            if lease_path.exists():
                try:
                    current = json.loads(
                        await asyncio.to_thread(lease_path.read_text, encoding="utf-8")
                    )
                except Exception:
                    current = None

            now = time.time()
            if current and float(current.get("expires_at", 0.0)) > now:
                if current.get("leader_id") == self.node_id:
                    current["expires_at"] = now + self.node_ttl_seconds
                    await asyncio.to_thread(
                        lease_path.write_text,
                        json.dumps(current, indent=2),
                        encoding="utf-8",
                    )
                self._lease = LeaderLease(
                    leader_id=str(current.get("leader_id")),
                    term=int(current.get("term", 0)),
                    expires_at=float(current.get("expires_at", now)),
                )
                return self._lease

            term = int(current.get("term", 0) if current else 0) + 1
            proposal = {
                "leader_id": self.node_id,
                "term": term,
                "elected_at": _now_iso(),
                "expires_at": now + self.node_ttl_seconds,
            }
            await asyncio.to_thread(
                lease_path.write_text,
                json.dumps(proposal, indent=2),
                encoding="utf-8",
            )
            self._lease = LeaderLease(
                leader_id=self.node_id,
                term=term,
                expires_at=float(proposal["expires_at"]),
            )
            return self._lease

    async def is_leader(self) -> bool:
        lease = await self.ensure_leader()
        return lease.leader_id == self.node_id

    async def replicate_state(self, state: dict[str, Any]) -> None:
        state_hash = _hash_payload(state)
        self._last_state_hash = state_hash
        node_path = self.state_dir / f"{self.node_id}.json"
        payload = {
            "node_id": self.node_id,
            "state_hash": state_hash,
            "state": state,
            "updated_at": _now_iso(),
        }
        await asyncio.to_thread(
            node_path.write_text,
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        if await self.is_leader():
            canonical_path = self.state_dir / "canonical.json"
            await asyncio.to_thread(
                canonical_path.write_text,
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )

    async def load_canonical_state(self) -> dict[str, Any]:
        canonical_path = self.state_dir / "canonical.json"
        if not canonical_path.exists():
            return {}
        try:
            raw = await asyncio.to_thread(canonical_path.read_text, encoding="utf-8")
            payload = json.loads(raw)
            state = payload.get("state")
            return state if isinstance(state, dict) else {}
        except Exception:
            return {}

    async def publish_memory(self, namespace: str, record: dict[str, Any]) -> None:
        namespace_dir = self.memory_dir / namespace
        await asyncio.to_thread(namespace_dir.mkdir, parents=True, exist_ok=True)
        record_path = namespace_dir / f"{int(time.time() * 1000)}_{self.node_id}.json"
        await asyncio.to_thread(
            record_path.write_text,
            json.dumps(record, indent=2),
            encoding="utf-8",
        )

    async def read_shared_memory(
        self, namespace: str, limit: int = 32
    ) -> list[dict[str, Any]]:
        namespace_dir = self.memory_dir / namespace
        if not namespace_dir.exists():
            return []
        records = []
        for record_path in sorted(
            await asyncio.to_thread(lambda: list(namespace_dir.glob("*.json"))),
            reverse=True,
        )[:limit]:
            try:
                raw = await asyncio.to_thread(record_path.read_text, encoding="utf-8")
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    records.append(payload)
            except Exception:
                continue
        return records

    async def begin_checkpoint_barrier(
        self,
        checkpoint_id: str,
        payload: dict[str, Any],
    ) -> Path:
        barrier_dir = self.checkpoint_dir / checkpoint_id / "barrier"
        await asyncio.to_thread(barrier_dir.mkdir, parents=True, exist_ok=True)
        barrier_path = barrier_dir / f"{self.node_id}.json"
        await asyncio.to_thread(
            barrier_path.write_text,
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return barrier_path

    async def commit_checkpoint_consensus(
        self,
        checkpoint_id: str,
        *,
        version: int,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        checkpoint_root = self.checkpoint_dir / checkpoint_id
        barrier_dir = checkpoint_root / "barrier"
        commit_dir = checkpoint_root / "commits"
        await asyncio.to_thread(commit_dir.mkdir, parents=True, exist_ok=True)

        deadline = time.time() + self.barrier_timeout_seconds
        active_node_ids = {node["node_id"] for node in await self.active_nodes()}
        active_node_ids.add(self.node_id)
        barriers = []
        while time.time() < deadline:
            barriers = await asyncio.to_thread(lambda: list(barrier_dir.glob("*.json")))
            barrier_nodes = {path.stem for path in barriers}
            if active_node_ids.issubset(barrier_nodes):
                break
            await asyncio.sleep(0.25)

        if not active_node_ids.issubset({path.stem for path in barriers}):
            raise TimeoutError(
                f"Checkpoint barrier timed out for {checkpoint_id}; expected {sorted(active_node_ids)}"
            )

        canonical_manifest = {
            "checkpoint_id": checkpoint_id,
            "version": version,
            "barrier_nodes": sorted(active_node_ids),
            "barrier_count": len(barriers),
            "manifest": manifest,
            "committed_at": _now_iso(),
            "leader_id": (await self.ensure_leader()).leader_id,
            "manifest_hash": _hash_payload(manifest),
        }

        commit_path = commit_dir / f"v{version:06d}.json"
        latest_path = self.checkpoint_dir / "latest_consistent_checkpoint.json"
        rollback_path = self.checkpoint_dir / "rollback_checkpoint.json"

        await asyncio.to_thread(
            commit_path.write_text,
            json.dumps(canonical_manifest, indent=2),
            encoding="utf-8",
        )
        await asyncio.to_thread(
            latest_path.write_text,
            json.dumps(canonical_manifest, indent=2),
            encoding="utf-8",
        )
        await asyncio.to_thread(
            rollback_path.write_text,
            json.dumps(canonical_manifest, indent=2),
            encoding="utf-8",
        )
        return canonical_manifest

    async def latest_consistent_checkpoint(self) -> dict[str, Any]:
        latest_path = self.checkpoint_dir / "latest_consistent_checkpoint.json"
        if not latest_path.exists():
            return {}
        try:
            raw = await asyncio.to_thread(latest_path.read_text, encoding="utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    async def rollback_manifest(self) -> dict[str, Any]:
        rollback_path = self.checkpoint_dir / "rollback_checkpoint.json"
        if not rollback_path.exists():
            return {}
        try:
            raw = await asyncio.to_thread(rollback_path.read_text, encoding="utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    async def detect_anomalies(self) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        now = time.time()
        lease = await self.ensure_leader()
        if lease.expires_at < now:
            anomalies.append(
                {
                    "type": "leader_lease_expired",
                    "details": f"Leader {lease.leader_id} lease expired",
                    "detected_at": _now_iso(),
                }
            )

        states = []
        for state_path in await asyncio.to_thread(
            lambda: list(self.state_dir.glob("*.json"))
        ):
            if state_path.name == "canonical.json":
                continue
            try:
                raw = await asyncio.to_thread(state_path.read_text, encoding="utf-8")
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    states.append(payload)
            except Exception:
                continue
        hashes = {
            payload.get("state_hash") for payload in states if payload.get("state_hash")
        }
        if len(hashes) > 1:
            anomalies.append(
                {
                    "type": "state_divergence",
                    "details": f"Detected {len(hashes)} distinct state hashes across nodes",
                    "detected_at": _now_iso(),
                }
            )

        self._last_anomalies = anomalies
        if anomalies:
            anomaly_path = self.anomaly_dir / f"anomaly_{int(time.time())}.json"
            await asyncio.to_thread(
                anomaly_path.write_text,
                json.dumps(anomalies, indent=2),
                encoding="utf-8",
            )
        return anomalies

    async def snapshot(self) -> dict[str, Any]:
        active_nodes = await self.active_nodes()
        lease = await self.ensure_leader()
        latest_checkpoint = await self.latest_consistent_checkpoint()
        return {
            "node_id": self.node_id,
            "leader_id": lease.leader_id,
            "leader_term": lease.term,
            "is_leader": lease.leader_id == self.node_id,
            "active_nodes": [node["node_id"] for node in active_nodes],
            "active_node_count": len(active_nodes),
            "last_state_hash": self._last_state_hash,
            "latest_checkpoint": latest_checkpoint.get("checkpoint_id"),
            "latest_checkpoint_version": latest_checkpoint.get("version"),
            "anomalies": list(self._last_anomalies),
        }
