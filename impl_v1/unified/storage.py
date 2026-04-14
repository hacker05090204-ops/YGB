from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from typing import Any, Dict, Optional, Tuple

from storage_backend import get_storage


logger = logging.getLogger(__name__)


@dataclass
class BlobRecord:
    blob_id: str
    sha256: str
    size_bytes: int
    local_path: str
    remote_path: str
    deduplicated: bool
    mirrored: bool
    created_at: str


@dataclass
class DeltaCheckpointRecord:
    checkpoint_id: str
    parent_checkpoint_id: str
    changed_keys: Tuple[str, ...]
    full_manifest_path: str
    delta_manifest_path: str
    blob_sha256: str
    mirrored: bool
    created_at: str


class TieredCheckpointStorageEngine:
    """Delta checkpoint metadata + content-addressable dedupe + remote mirror."""

    def __init__(self, root_dir: str, remote_prefix: str = "tiered_storage"):
        self.root_dir = root_dir
        self.remote_prefix = remote_prefix.strip("/").replace("\\", "/")
        self.nvme_dir = os.path.join(root_dir, "nvme")
        self.manifest_dir = os.path.join(root_dir, "manifests")
        self.index_path = os.path.join(root_dir, "index.json")
        self.storage = get_storage()
        self._index = self._load_index()
        os.makedirs(self.nvme_dir, exist_ok=True)
        os.makedirs(self.manifest_dir, exist_ok=True)

    def _load_index(self) -> Dict[str, Any]:
        try:
            with open(self.index_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {"blobs": {}, "checkpoints": {}}
        except Exception:
            return {"blobs": {}, "checkpoints": {}}

    def _persist_index(self) -> None:
        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        tmp = f"{self.index_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self._index, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, self.index_path)

    def _hash_bytes(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _remote_path(self, *parts: str) -> str:
        clean = [part.strip("/").replace("\\", "/") for part in parts if part]
        return "/".join([self.remote_prefix, *clean])

    def store_blob(self, name: str, payload: bytes, *, mirror_remote: bool = False) -> BlobRecord:
        digest = self._hash_bytes(payload)
        existing = self._index["blobs"].get(digest)
        blob_rel = os.path.join("blobs", digest[:2], f"{digest}.bin")
        local_path = os.path.join(self.nvme_dir, blob_rel)
        remote_path = self._remote_path("blobs", digest[:2], f"{digest}.bin")
        deduplicated = existing is not None and os.path.exists(existing.get("local_path", ""))

        if not deduplicated:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as handle:
                handle.write(payload)

        mirrored = bool(existing.get("mirrored")) if existing else False
        if mirror_remote and not mirrored:
            mirrored = bool(self.storage.write(remote_path, payload))

        record = BlobRecord(
            blob_id=f"BLOB-{digest[:12].upper()}",
            sha256=digest,
            size_bytes=len(payload),
            local_path=local_path,
            remote_path=remote_path,
            deduplicated=deduplicated,
            mirrored=mirrored,
            created_at=(existing or {}).get("created_at", datetime.now(UTC).isoformat()),
        )
        self._index["blobs"][digest] = asdict(record)
        self._persist_index()
        return record

    def store_checkpoint_manifest(
        self,
        checkpoint_id: str,
        manifest: Dict[str, Any],
        *,
        parent_manifest: Optional[Dict[str, Any]] = None,
        parent_checkpoint_id: str = "",
        mirror_remote: bool = True,
    ) -> DeltaCheckpointRecord:
        manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        blob = self.store_blob(f"{checkpoint_id}.json", manifest_bytes, mirror_remote=mirror_remote)

        changed_keys = tuple(
            sorted(
                key
                for key, value in manifest.items()
                if (parent_manifest or {}).get(key) != value
            )
        )
        delta_payload = {
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "changed_keys": changed_keys,
            "delta": {key: manifest[key] for key in changed_keys},
            "full_manifest_sha256": blob.sha256,
            "created_at": datetime.now(UTC).isoformat(),
        }

        full_manifest_path = os.path.join(self.manifest_dir, f"{checkpoint_id}.full.json")
        delta_manifest_path = os.path.join(self.manifest_dir, f"{checkpoint_id}.delta.json")
        with open(full_manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        with open(delta_manifest_path, "w", encoding="utf-8") as handle:
            json.dump(delta_payload, handle, indent=2)
            handle.write("\n")

        mirrored = blob.mirrored
        if mirror_remote:
            delta_remote = self._remote_path("manifests", f"{checkpoint_id}.delta.json")
            mirrored = bool(self.storage.write(delta_remote, json.dumps(delta_payload, indent=2).encode("utf-8"))) and mirrored

        record = DeltaCheckpointRecord(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            changed_keys=changed_keys,
            full_manifest_path=full_manifest_path,
            delta_manifest_path=delta_manifest_path,
            blob_sha256=blob.sha256,
            mirrored=mirrored,
            created_at=delta_payload["created_at"],
        )
        self._index["checkpoints"][checkpoint_id] = asdict(record)
        self._persist_index()
        return record

    def hydrate_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        record = self._index["checkpoints"].get(checkpoint_id)
        if not record:
            return {}
        base: Dict[str, Any] = {}
        parent_id = record.get("parent_checkpoint_id", "")
        if parent_id:
            base.update(self.hydrate_checkpoint(parent_id))
        try:
            with open(record["delta_manifest_path"], "r", encoding="utf-8") as handle:
                delta_payload = json.load(handle)
            base.update(delta_payload.get("delta", {}))
        except Exception as exc:
            logger.warning(
                "[TIERED_STORAGE] Failed to hydrate delta manifest for %s from %s; returning parent manifest only: %s",
                checkpoint_id,
                record.get("delta_manifest_path", ""),
                exc,
            )
        return base

    def get_status(self) -> Dict[str, Any]:
        return {
            "root_dir": self.root_dir,
            "nvme_dir": self.nvme_dir,
            "blobs": len(self._index.get("blobs", {})),
            "checkpoints": len(self._index.get("checkpoints", {})),
            "remote_backend": self.storage.backend_name,
        }
