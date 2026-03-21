from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

EXPERTS = [
    "web_vulns",
    "api_testing",
    "mobile_apk",
    "cloud_misconfig",
    "blockchain",
    "iot",
    "hardware",
    "firmware",
    "ssrf",
    "rce",
    "xss",
    "sqli",
    "auth_bypass",
    "idor",
    "graphql_abuse",
    "rest_attacks",
    "csrf",
    "file_upload",
    "deserialization",
    "privilege_escalation",
    "cryptography",
    "subdomain_takeover",
    "race_condition",
]

TARGET_PARAMS_PER_EXPERT = 130_430_000


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ExpertCheckpoint:
    expert_name: str
    version: int
    created_at: float
    step: int
    epoch: int
    params_target: int = TARGET_PARAMS_PER_EXPERT
    checkpoint_id: str = ""
    model_path: str = ""
    optimizer_path: str = ""
    router_path: str = ""
    metadata_path: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    data_manifest_hash: str = ""
    sample_count: int = 0
    content_sha256: str = ""
    parent_sha256: str = ""
    promotion_policy: str = "shadow_then_promote"
    artifact_hashes: Dict[str, str] = field(default_factory=dict)


class ExpertCheckpointRegistry:
    """Independent checkpoint lineage for 23 trainable experts."""

    def __init__(self, root: str = "secure_data/expert_checkpoints") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "registry.json"
        self.registry = self._load()
        self._ensure_experts()

    def _load(self) -> Dict[str, List[Dict[str, Any]]]:
        if self.registry_path.exists():
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        _atomic_write_json(self.registry_path, self.registry)

    def _ensure_experts(self) -> None:
        for name in EXPERTS:
            self.registry.setdefault(name, [])
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self._save()

    def create_checkpoint(
        self,
        expert_name: str,
        *,
        epoch: int,
        step: int,
        metrics: Dict[str, Any],
        data_manifest_hash: str,
        sample_count: int,
        model_bytes: bytes = b"",
        optimizer_bytes: bytes = b"",
        router_bytes: bytes = b"",
        promotion_policy: str = "shadow_then_promote",
    ) -> ExpertCheckpoint:
        if expert_name not in EXPERTS:
            raise ValueError(f"unknown expert: {expert_name}")

        version = len(self.registry[expert_name]) + 1
        checkpoint_id = f"{expert_name}-v{version:05d}"
        checkpoint_dir = self.root / expert_name / checkpoint_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        model_path = checkpoint_dir / "model.safetensors"
        optimizer_path = checkpoint_dir / "optimizer.pt"
        router_path = checkpoint_dir / "router.safetensors"
        _atomic_write_bytes(model_path, model_bytes)
        _atomic_write_bytes(optimizer_path, optimizer_bytes)
        _atomic_write_bytes(router_path, router_bytes)

        artifact_hashes = {
            "model.safetensors": _sha256_file(model_path),
            "optimizer.pt": _sha256_file(optimizer_path),
            "router.safetensors": _sha256_file(router_path),
        }
        artifact_blob = json.dumps(artifact_hashes, sort_keys=True).encode("utf-8")
        content_sha256 = hashlib.sha256(artifact_blob).hexdigest()
        parent_sha256 = (
            self.registry[expert_name][-1]["content_sha256"]
            if self.registry[expert_name]
            else ""
        )
        metadata_path = checkpoint_dir / "metadata.json"
        meta = ExpertCheckpoint(
            expert_name=expert_name,
            version=version,
            created_at=time.time(),
            step=step,
            epoch=epoch,
            checkpoint_id=checkpoint_id,
            model_path=str(model_path),
            optimizer_path=str(optimizer_path),
            router_path=str(router_path),
            metadata_path=str(metadata_path),
            metrics=dict(metrics),
            data_manifest_hash=data_manifest_hash,
            sample_count=int(sample_count),
            content_sha256=content_sha256,
            parent_sha256=parent_sha256,
            promotion_policy=promotion_policy,
            artifact_hashes=artifact_hashes,
        )
        _atomic_write_json(metadata_path, asdict(meta))
        self.registry[expert_name].append(asdict(meta))
        self._save()
        return meta

    def latest(self, expert_name: str) -> Optional[Dict[str, Any]]:
        history = self.registry.get(expert_name, [])
        return history[-1] if history else None

    def history(self, expert_name: str) -> List[Dict[str, Any]]:
        return list(self.registry.get(expert_name, []))

    def verify_lineage(self, expert_name: str) -> bool:
        history = self.registry.get(expert_name, [])
        parent_sha = ""
        for item in history:
            if str(item.get("parent_sha256", "") or "") != parent_sha:
                return False
            parent_sha = str(item.get("content_sha256", "") or "")
        return True
