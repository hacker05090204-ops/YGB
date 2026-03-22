from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from backend.ingest.normalize.canonicalize import CanonicalRecord


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_json(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(_normalize_json(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass
class PublishedSnapshot:
    snapshot_id: str
    manifest_path: str
    records_path: str
    manifest_sha256: str
    signature: str
    record_count: int
    exact_hashes: List[str]


class SnapshotPublisher:
    """Publishes immutable, signed, real-only training snapshots."""

    def __init__(
        self,
        root: str = "secure_data/ingest_snapshots",
        *,
        signing_key: bytes | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshots_root = self.root / "published"
        self.quarantine_root = self.root / "quarantine"
        self.index_path = self.root / "exact_hash_index.json"
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.signing_key = signing_key or self._load_signing_key()

    @staticmethod
    def _load_signing_key() -> bytes:
        env_key = os.environ.get("YGB_SNAPSHOT_SIGNING_KEY", "").strip()
        if env_key:
            return env_key.encode("utf-8")
        shared_hmac = os.environ.get("YGB_HMAC_SECRET", "").strip()
        if shared_hmac:
            return shared_hmac.encode("utf-8")
        raise RuntimeError(
            "Snapshot signing requires YGB_SNAPSHOT_SIGNING_KEY or YGB_HMAC_SECRET"
        )

    def exact_hashes(self) -> Dict[str, str]:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return {
            str(key): str(value)
            for key, value in payload.items()
            if str(key).strip() and str(value).strip()
        }

    def load_recent_records(self, *, limit: int = 25) -> List[CanonicalRecord]:
        records: List[CanonicalRecord] = []
        manifests = sorted(self.snapshots_root.glob("*/manifest.json"), reverse=True)
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            records_path = Path(str(manifest.get("records_path", "")))
            if not records_path.exists():
                continue
            with open(records_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    records.append(CanonicalRecord(**json.loads(line)))
                    if len(records) >= limit:
                        return records
        return records

    def quarantine(
        self,
        record: CanonicalRecord,
        *,
        reason: str,
        score: float = 0.0,
    ) -> str:
        quarantine_id = f"quarantine-{int(time.time() * 1000)}-{record.record_id[:8]}"
        path = self.quarantine_root / f"{quarantine_id}.json"
        _atomic_write_json(
            path,
            {
                "quarantine_id": quarantine_id,
                "reason": reason,
                "near_duplicate_score": score,
                "record": record.to_dict(),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        return str(path)

    def publish(
        self,
        records: Sequence[CanonicalRecord],
        *,
        route: str = "trainer",
    ) -> PublishedSnapshot:
        if not records:
            raise ValueError("cannot publish empty snapshot")
        exact_hashes = sorted({record.content_sha256 for record in records if record.content_sha256})
        raw_lines = [
            json.dumps(_normalize_json(record.to_dict()), sort_keys=True)
            for record in records
        ]
        records_blob = ("\n".join(raw_lines) + "\n").encode("utf-8")
        records_sha256 = _sha256_bytes(records_blob)
        snapshot_id = f"snapshot-{int(time.time() * 1000)}-{records_sha256[:12]}"
        snapshot_dir = self.snapshots_root / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        records_path = snapshot_dir / "records.jsonl"
        _atomic_write_bytes(records_path, records_blob)

        manifest_payload = {
            "snapshot_id": snapshot_id,
            "schema_version": "2026-03-real-only",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "immutable": True,
            "route": route,
            "record_count": len(records),
            "records_path": str(records_path),
            "records_sha256": records_sha256,
            "exact_hashes": exact_hashes,
            "source_names": sorted({record.source_name for record in records}),
        }
        manifest_blob = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self.signing_key, manifest_blob, hashlib.sha256).hexdigest()
        manifest_sha256 = _sha256_bytes(manifest_blob)
        manifest = dict(manifest_payload)
        manifest["manifest_sha256"] = manifest_sha256
        manifest["signature"] = signature
        manifest_path = snapshot_dir / "manifest.json"
        _atomic_write_json(manifest_path, manifest)

        index = self.exact_hashes()
        for content_hash in exact_hashes:
            index[content_hash] = snapshot_id
        _atomic_write_json(self.index_path, index)
        return PublishedSnapshot(
            snapshot_id=snapshot_id,
            manifest_path=str(manifest_path),
            records_path=str(records_path),
            manifest_sha256=manifest_sha256,
            signature=signature,
            record_count=len(records),
            exact_hashes=exact_hashes,
        )

    def verify_manifest(self, manifest_path: str) -> bool:
        path = Path(manifest_path)
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        signature = str(payload.pop("signature", "") or "")
        manifest_sha256 = str(payload.pop("manifest_sha256", "") or "")
        manifest_blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_signature = hmac.new(self.signing_key, manifest_blob, hashlib.sha256).hexdigest()
        if signature != expected_signature:
            return False
        if manifest_sha256 and manifest_sha256 != _sha256_bytes(manifest_blob):
            return False
        records_path = Path(str(payload.get("records_path", "")))
        if not records_path.exists():
            return False
        records_sha256 = str(payload.get("records_sha256", "") or "")
        if records_sha256 and _sha256_bytes(records_path.read_bytes()) != records_sha256:
            return False
        return True
