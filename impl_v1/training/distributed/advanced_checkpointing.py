from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


try:
    import torch
    from safetensors.torch import load_file as st_load
    from safetensors.torch import save_file as st_save
except Exception:  # pragma: no cover
    torch = None
    st_load = None
    st_save = None


@dataclass
class CheckpointShard:
    rank: int
    world_size: int
    model_path: str
    optimizer_path: str
    scheduler_path: str
    meta_path: str
    model_sha256: str = ""
    optimizer_sha256: str = ""
    scheduler_sha256: str = ""


@dataclass
class DistributedCheckpointBundle:
    name: str
    version: int
    dir_path: str
    model_shards: List[CheckpointShard] = field(default_factory=list)
    latest_pointer_path: str = ""
    best_pointer_path: str = ""
    meta_path: str = ""


@dataclass
class LoadedCheckpoint:
    bundle: DistributedCheckpointBundle
    meta: Dict[str, Any]
    model_state: Dict[str, Any]
    optimizer_state: Dict[str, Any]
    scheduler_state: Dict[str, Any]


JSON_PRIMITIVES = (str, int, float, bool, type(None))


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    _ensure_dir(os.path.dirname(path) or ".")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, JSON_PRIMITIVES):
        return value
    if isinstance(value, tuple):
        return [_normalize_json_value(v) for v in value]
    if isinstance(value, list):
        return [_normalize_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize_json_value(v) for k, v in value.items()}
    return repr(value)


def _split_tensors(obj: Any, prefix: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if torch is not None and isinstance(obj, torch.Tensor):
        tensor = obj.detach().cpu().contiguous()
        return {prefix or "root": tensor}, {"__tensor__": prefix or "root"}

    if isinstance(obj, dict):
        tensors: Dict[str, Any] = {}
        template: Dict[str, Any] = {}
        for key, value in obj.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            child_tensors, child_template = _split_tensors(value, child_prefix)
            tensors.update(child_tensors)
            template[str(key)] = child_template
        return tensors, template

    if isinstance(obj, (list, tuple)):
        tensors = {}
        template = []
        for idx, value in enumerate(obj):
            child_prefix = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            child_tensors, child_template = _split_tensors(value, child_prefix)
            tensors.update(child_tensors)
            template.append(child_template)
        return tensors, template

    return {}, _normalize_json_value(obj)


def _restore_tensors(template: Any, tensors: Dict[str, Any]) -> Any:
    if isinstance(template, dict) and "__tensor__" in template:
        return tensors[template["__tensor__"]]
    if isinstance(template, dict):
        return {key: _restore_tensors(value, tensors) for key, value in template.items()}
    if isinstance(template, list):
        return [_restore_tensors(value, tensors) for value in template]
    return template


def _bundle_paths(base_dir: str, name: str, version: int, world_size: int) -> DistributedCheckpointBundle:
    dir_path = os.path.join(base_dir, f"{name}.v{version:04d}")
    shards = []
    for rank in range(world_size):
        shards.append(
            CheckpointShard(
                rank=rank,
                world_size=world_size,
                model_path=os.path.join(dir_path, f"model-rank{rank:05d}-of{world_size:05d}.safetensors"),
                optimizer_path=os.path.join(dir_path, f"optimizer-rank{rank:05d}-of{world_size:05d}.safetensors"),
                scheduler_path=os.path.join(dir_path, f"scheduler-rank{rank:05d}-of{world_size:05d}.safetensors"),
                meta_path=os.path.join(dir_path, f"rank{rank:05d}.json"),
            )
        )
    return DistributedCheckpointBundle(
        name=name,
        version=version,
        dir_path=dir_path,
        model_shards=shards,
        latest_pointer_path=os.path.join(base_dir, "latest.json"),
        best_pointer_path=os.path.join(base_dir, "best.json"),
        meta_path=os.path.join(dir_path, "bundle.json"),
    )


class AsyncDistributedCheckpointManager:
    """Versioned sharded checkpoint manager with SafeTensors-backed shards."""

    def __init__(self, base_dir: str, max_workers: int = 2):
        self.base_dir = base_dir
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ckpt-save")
        self._lock = threading.Lock()
        _ensure_dir(base_dir)
        self.manifest_path = os.path.join(base_dir, "manifest.json")

    def close(self) -> None:
        self.executor.shutdown(wait=True)

    def _next_version(self) -> int:
        manifest = self._load_manifest()
        return int(manifest.get("next_version", 1))

    def _load_manifest(self) -> Dict[str, Any]:
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _persist_manifest(self, manifest: Dict[str, Any]) -> None:
        _atomic_write_json(self.manifest_path, manifest)

    def save_async(
        self,
        *,
        name: str,
        model_state: Dict[str, Any],
        optimizer_state: Dict[str, Any],
        scheduler_state: Dict[str, Any],
        meta: Dict[str, Any],
        rank: int = 0,
        world_size: int = 1,
        is_latest: bool = True,
        is_best: bool = False,
    ) -> Future:
        return self.executor.submit(
            self.save,
            name=name,
            model_state=model_state,
            optimizer_state=optimizer_state,
            scheduler_state=scheduler_state,
            meta=meta,
            rank=rank,
            world_size=world_size,
            is_latest=is_latest,
            is_best=is_best,
        )

    def save(
        self,
        *,
        name: str,
        model_state: Dict[str, Any],
        optimizer_state: Dict[str, Any],
        scheduler_state: Dict[str, Any],
        meta: Dict[str, Any],
        rank: int = 0,
        world_size: int = 1,
        is_latest: bool = True,
        is_best: bool = False,
    ) -> str:
        if st_save is None:
            raise RuntimeError("SafeTensors is required for checkpoint saving")

        with self._lock:
            version = self._next_version()
            bundle = _bundle_paths(self.base_dir, name, version, world_size)
            shard = bundle.model_shards[rank]
            _ensure_dir(bundle.dir_path)
            manifest = self._load_manifest()
            manifest["next_version"] = version + 1
            self._persist_manifest(manifest)

        model_tensors, model_template = _split_tensors(model_state)
        optimizer_tensors, optimizer_template = _split_tensors(optimizer_state)
        scheduler_tensors, scheduler_template = _split_tensors(scheduler_state)

        for path, tensors in (
            (shard.model_path, model_tensors),
            (shard.optimizer_path, optimizer_tensors),
            (shard.scheduler_path, scheduler_tensors),
        ):
            tmp = f"{path}.tmp"
            st_save(tensors or {"__empty__": torch.zeros(1, dtype=torch.uint8)}, tmp)
            os.replace(tmp, path)

        shard.model_sha256 = _sha256_file(shard.model_path)
        shard.optimizer_sha256 = _sha256_file(shard.optimizer_path)
        shard.scheduler_sha256 = _sha256_file(shard.scheduler_path)

        shard_meta = {
            "rank": rank,
            "world_size": world_size,
            "version": version,
            "model_template": model_template,
            "optimizer_template": optimizer_template,
            "scheduler_template": scheduler_template,
            "model_sha256": shard.model_sha256,
            "optimizer_sha256": shard.optimizer_sha256,
            "scheduler_sha256": shard.scheduler_sha256,
            "saved_at": datetime.now().isoformat(),
        }
        _atomic_write_json(shard.meta_path, shard_meta)

        bundle_meta = {
            **meta,
            "name": name,
            "version": version,
            "saved_at": datetime.now().isoformat(),
            "is_latest": is_latest,
            "is_best": is_best,
            "rank": rank,
            "world_size": world_size,
            "dir_path": bundle.dir_path,
            "shards": [asdict(s) for s in bundle.model_shards],
        }
        _atomic_write_json(bundle.meta_path, bundle_meta)

        with self._lock:
            manifest = self._load_manifest()
            history = manifest.get("history", [])
            history.append(
                {
                    "name": name,
                    "version": version,
                    "meta_path": bundle.meta_path,
                    "epoch": meta.get("epoch"),
                    "accuracy": meta.get("accuracy"),
                    "best_accuracy": meta.get("best_accuracy"),
                    "saved_at": bundle_meta["saved_at"],
                    "status": "valid",
                }
            )
            manifest["history"] = history[-200:]
            manifest["next_version"] = max(int(manifest.get("next_version", 1)), version + 1)
            if is_latest:
                manifest["latest"] = {
                    "name": name,
                    "version": version,
                    "meta_path": bundle.meta_path,
                }
                _atomic_write_json(bundle.latest_pointer_path, manifest["latest"])
            if is_best:
                manifest["best"] = {
                    "name": name,
                    "version": version,
                    "meta_path": bundle.meta_path,
                }
                _atomic_write_json(bundle.best_pointer_path, manifest["best"])
            self._persist_manifest(manifest)
        logger.info("[ADV_CKPT] saved %s v%s rank=%s/%s", name, version, rank, world_size)
        return bundle.meta_path

    def _validate_bundle_meta(self, meta_path: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
            for shard in meta.get("shards", []):
                for key in ("model_path", "optimizer_path", "scheduler_path", "meta_path"):
                    path = shard.get(key, "")
                    if not path or not os.path.exists(path):
                        return False, None, f"missing shard file: {key}"
                if shard.get("model_sha256") and _sha256_file(shard["model_path"]) != shard["model_sha256"]:
                    return False, None, "model checksum mismatch"
                if shard.get("optimizer_sha256") and _sha256_file(shard["optimizer_path"]) != shard["optimizer_sha256"]:
                    return False, None, "optimizer checksum mismatch"
                if shard.get("scheduler_sha256") and _sha256_file(shard["scheduler_path"]) != shard["scheduler_sha256"]:
                    return False, None, "scheduler checksum mismatch"
            return True, meta, "ok"
        except Exception as exc:
            return False, None, str(exc)

    def load_latest_valid(self, preferred: Iterable[str] = ("latest", "best"), rank: int = 0) -> Optional[LoadedCheckpoint]:
        manifest = self._load_manifest()
        candidates: List[Dict[str, Any]] = []
        for key in preferred:
            pointer = manifest.get(key)
            if isinstance(pointer, dict):
                candidates.append(pointer)
        for item in reversed(manifest.get("history", [])):
            if isinstance(item, dict):
                candidates.append(item)

        seen = set()
        for candidate in candidates:
            meta_path = candidate.get("meta_path")
            if not meta_path or meta_path in seen:
                continue
            seen.add(meta_path)
            valid, meta, reason = self._validate_bundle_meta(meta_path)
            if not valid or meta is None:
                logger.warning("[ADV_CKPT] invalid checkpoint %s: %s", meta_path, reason)
                self.mark_corrupted(meta_path, reason)
                continue
            bundle = _bundle_paths(self.base_dir, meta.get("name", "checkpoint"), int(meta.get("version", 0)), int(meta.get("world_size", 1)))
            shard_meta = bundle.model_shards[min(rank, len(bundle.model_shards) - 1)]
            with open(shard_meta.meta_path, "r", encoding="utf-8") as handle:
                rank_payload = json.load(handle)
            model_tensors = st_load(shard_meta.model_path, device="cpu") if st_load is not None else {}
            optimizer_tensors = st_load(shard_meta.optimizer_path, device="cpu") if st_load is not None else {}
            scheduler_tensors = st_load(shard_meta.scheduler_path, device="cpu") if st_load is not None else {}
            model_state = _restore_tensors(rank_payload.get("model_template", {}), model_tensors)
            optimizer_state = _restore_tensors(rank_payload.get("optimizer_template", {}), optimizer_tensors)
            scheduler_state = _restore_tensors(rank_payload.get("scheduler_template", {}), scheduler_tensors)
            return LoadedCheckpoint(
                bundle=bundle,
                meta=meta,
                model_state=model_state,
                optimizer_state=optimizer_state,
                scheduler_state=scheduler_state,
            )
        return None

    def mark_corrupted(self, meta_path: str, reason: str) -> None:
        manifest = self._load_manifest()
        history = manifest.get("history", [])
        for item in history:
            if item.get("meta_path") == meta_path:
                item["status"] = "corrupted"
                item["reason"] = reason
        self._persist_manifest(manifest)
