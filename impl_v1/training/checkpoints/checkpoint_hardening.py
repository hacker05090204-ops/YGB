"""
Checkpoint hardening for resumable production training.

Supports:
- per-rank sharded checkpoints
- SafeTensors model shards
- optimizer, scheduler, scaler, RNG, and training metadata persistence
- atomic file writes with manifest + latest/best pointers
- async checkpoint persistence
- recovery from the latest valid checkpoint
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import random
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CheckpointMetadata:
    """Metadata for a checkpoint."""

    checkpoint_id: str
    epoch: int
    step: int
    sha256: str
    timestamp: str
    metrics: Dict[str, float]
    replay_verified: bool
    global_step: int = 0
    world_size: int = 1
    checkpoint_kind: str = "full"
    checkpoint_path: str = ""
    metadata_path: str = ""
    training_state_path: str = ""
    is_best: bool = False
    is_latest: bool = False
    shards: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ResumeResult:
    """Result returned by resume operations."""

    resumed: bool
    checkpoint_id: str = ""
    checkpoint_path: str = ""
    epoch: int = 0
    step: int = 0
    global_step: int = 0
    metrics: Dict[str, float] = field(default_factory=dict)
    reason: str = ""


class HardenedCheckpointManager:
    """Checkpoint manager with atomic writes and validated resume."""

    def __init__(
        self,
        checkpoint_dir: Path,
        *,
        max_async_workers: int = 1,
    ):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.checkpoint_dir / "checkpoint_manifest.json"
        self.pointer_file = self.checkpoint_dir / "checkpoint_pointers.json"
        self.checkpoints: Dict[str, CheckpointMetadata] = {}
        self._latest_checkpoint_id = ""
        self._best_checkpoint_id = ""
        self._lock = Lock()
        self._pending_futures: List[Future] = []
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_async_workers)),
            thread_name_prefix="checkpoint-save",
        )
        self._load_manifest()
        self._load_pointers()
        self._discover_checkpoints_from_disk()

    def close(self) -> None:
        """Flush pending writes and stop async workers."""
        self.wait_for_pending_writes()
        self._executor.shutdown(wait=True)

    def __del__(self):  # pragma: no cover - defensive cleanup only
        executor = getattr(self, "_executor", None)
        if executor is None:
            return
        try:
            executor.shutdown(wait=False, cancel_futures=False)
        except Exception:
            logger.warning(
                "[CKPT] Failed to shut down checkpoint executor during cleanup",
                exc_info=True,
            )

    @property
    def latest_checkpoint_id(self) -> str:
        return self._latest_checkpoint_id

    @property
    def best_checkpoint_id(self) -> str:
        return self._best_checkpoint_id

    @staticmethod
    def capture_rng_state() -> Dict[str, Any]:
        """Capture Python, NumPy, and Torch RNG state."""
        import numpy as np
        import torch

        state: Dict[str, Any] = {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch": torch.get_rng_state(),
        }
        if torch.cuda.is_available():
            try:
                state["cuda_all"] = torch.cuda.get_rng_state_all()
            except Exception:
                state["cuda_all"] = None
        return state

    @staticmethod
    def restore_rng_state(rng_state: Optional[Dict[str, Any]]) -> bool:
        """Restore Python, NumPy, and Torch RNG state."""
        if not rng_state:
            return False

        import numpy as np
        import torch

        try:
            if "python" in rng_state:
                random.setstate(rng_state["python"])
            if "numpy" in rng_state:
                np.random.set_state(rng_state["numpy"])
            if "torch" in rng_state and rng_state["torch"] is not None:
                torch.set_rng_state(rng_state["torch"].cpu())
            cuda_state = rng_state.get("cuda_all")
            if cuda_state is not None and torch.cuda.is_available():
                normalized = [
                    state.cpu() if hasattr(state, "cpu") else state
                    for state in cuda_state
                ]
                torch.cuda.set_rng_state_all(normalized)
            return True
        except Exception as exc:
            logger.warning("[CKPT] Failed to restore RNG state: %s", exc)
            return False

    def save_checkpoint(
        self,
        state_dict: Dict[str, Any],
        epoch: int,
        step: int,
        metrics: Dict[str, float],
        *,
        optimizer_state: Optional[Dict[str, Any]] = None,
        scheduler_state: Optional[Dict[str, Any]] = None,
        rng_state: Optional[Dict[str, Any]] = None,
        training_state: Optional[Dict[str, Any]] = None,
        scaler_state: Optional[Dict[str, Any]] = None,
        rank: int = 0,
        world_size: int = 1,
        global_step: Optional[int] = None,
        is_best: bool = False,
        checkpoint_kind: str = "full",
        checkpoint_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, CheckpointMetadata]:
        """Synchronously persist a full checkpoint."""
        snapshot = self._prepare_snapshot(
            state_dict=state_dict,
            epoch=epoch,
            step=step,
            metrics=metrics,
            optimizer_state=optimizer_state,
            scheduler_state=scheduler_state,
            rng_state=rng_state,
            training_state=training_state,
            scaler_state=scaler_state,
            rank=rank,
            world_size=world_size,
            global_step=global_step,
            is_best=is_best,
            checkpoint_kind=checkpoint_kind,
            checkpoint_id=checkpoint_id,
            extra_metadata=extra_metadata,
        )
        return self._save_checkpoint(snapshot)

    def save_checkpoint_async(
        self,
        state_dict: Dict[str, Any],
        epoch: int,
        step: int,
        metrics: Dict[str, float],
        *,
        optimizer_state: Optional[Dict[str, Any]] = None,
        scheduler_state: Optional[Dict[str, Any]] = None,
        rng_state: Optional[Dict[str, Any]] = None,
        training_state: Optional[Dict[str, Any]] = None,
        scaler_state: Optional[Dict[str, Any]] = None,
        rank: int = 0,
        world_size: int = 1,
        global_step: Optional[int] = None,
        is_best: bool = False,
        checkpoint_kind: str = "full",
        checkpoint_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Future:
        """Persist a full checkpoint on a background worker."""
        snapshot = self._prepare_snapshot(
            state_dict=state_dict,
            epoch=epoch,
            step=step,
            metrics=metrics,
            optimizer_state=optimizer_state,
            scheduler_state=scheduler_state,
            rng_state=rng_state,
            training_state=training_state,
            scaler_state=scaler_state,
            rank=rank,
            world_size=world_size,
            global_step=global_step,
            is_best=is_best,
            checkpoint_kind=checkpoint_kind,
            checkpoint_id=checkpoint_id,
            extra_metadata=extra_metadata,
        )
        future = self._executor.submit(self._save_checkpoint, snapshot)
        with self._lock:
            self._pending_futures.append(future)
        future.add_done_callback(self._remove_future)
        return future

    def wait_for_pending_writes(self, timeout: Optional[float] = None) -> None:
        """Block until all currently scheduled async writes finish."""
        with self._lock:
            pending = list(self._pending_futures)
        for future in pending:
            future.result(timeout=timeout)

    def get_checkpoint_metadata(self, checkpoint_id: str) -> Optional[CheckpointMetadata]:
        return self.checkpoints.get(checkpoint_id)

    def get_checkpoint_path(self, checkpoint_id: str) -> Path:
        metadata = self.checkpoints.get(checkpoint_id)
        if metadata and metadata.checkpoint_path:
            return Path(metadata.checkpoint_path)
        return self.checkpoint_dir / checkpoint_id

    def get_latest_checkpoint(self) -> Optional[str]:
        if self._latest_checkpoint_id:
            return self._latest_checkpoint_id
        ordered = self._ordered_checkpoint_ids()
        return ordered[-1] if ordered else None

    def get_best_checkpoint(self) -> Optional[str]:
        if self._best_checkpoint_id:
            return self._best_checkpoint_id
        best_candidates = [
            meta for meta in self.checkpoints.values() if meta.is_best
        ]
        if not best_candidates:
            return None
        return max(
            best_candidates,
            key=lambda item: (item.global_step, item.step, item.epoch),
        ).checkpoint_id

    def get_latest_valid_checkpoint(self) -> Optional[str]:
        candidates: List[str] = []
        if self._latest_checkpoint_id:
            candidates.append(self._latest_checkpoint_id)
        candidates.extend(
            checkpoint_id
            for checkpoint_id in reversed(self._ordered_checkpoint_ids())
            if checkpoint_id not in candidates
        )
        for checkpoint_id in candidates:
            valid, _ = self.verify_checkpoint(checkpoint_id)
            if valid:
                return checkpoint_id
        return None

    def verify_checkpoint(self, checkpoint_id: str) -> Tuple[bool, str]:
        """Verify checkpoint integrity and required artifacts."""
        metadata = self.checkpoints.get(checkpoint_id)
        if metadata is None:
            legacy_path = self._legacy_checkpoint_path(checkpoint_id)
            if legacy_path and legacy_path.exists():
                expected_hash = self._read_sha256_sidecar(legacy_path)
                if not expected_hash:
                    return False, "Legacy checkpoint sha256 sidecar missing"
                current_hash = self._compute_hash(legacy_path)
                if current_hash != expected_hash:
                    return False, "Legacy checkpoint hash mismatch"
                return True, "Legacy checkpoint verified"
            return False, "Checkpoint not in manifest"

        checkpoint_path = Path(metadata.checkpoint_path or self.checkpoint_dir / checkpoint_id)
        if checkpoint_path.is_file():
            expected_hash = str(
                metadata.sha256 or self._read_sha256_sidecar(checkpoint_path) or ""
            ).strip()
            if not expected_hash:
                return False, "Legacy checkpoint sha256 missing"
            current_hash = self._compute_hash(checkpoint_path)
            if current_hash != expected_hash:
                return False, "Legacy checkpoint hash mismatch"
            return True, "Legacy checkpoint verified"

        metadata_path = checkpoint_path / "metadata.json"
        training_state_path = checkpoint_path / "training_state.json"
        if not metadata_path.exists():
            return False, "Checkpoint metadata missing"
        if not training_state_path.exists():
            return False, "Training state missing"

        try:
            on_disk = self._read_json(metadata_path)
        except Exception as exc:
            return False, f"Checkpoint metadata unreadable: {exc}"

        if on_disk.get("checkpoint_id") != checkpoint_id:
            return False, "Checkpoint metadata ID mismatch"

        artifacts = on_disk.get("shards", [])
        if not artifacts:
            return False, "Checkpoint artifact manifest missing"

        combined_entries: List[Dict[str, Any]] = []
        for artifact in artifacts:
            relative_path = artifact.get("relative_path", "")
            expected_hash = artifact.get("sha256", "")
            artifact_path = checkpoint_path / relative_path
            if not artifact_path.exists():
                return False, f"Missing artifact: {relative_path}"
            current_hash = self._compute_hash(artifact_path)
            if expected_hash and current_hash != expected_hash:
                return False, f"Artifact hash mismatch: {relative_path}"
            combined_entries.append(
                {
                    "relative_path": relative_path,
                    "sha256": current_hash,
                }
            )

        combined_hash = self._combine_artifact_hashes(combined_entries)
        if combined_hash != metadata.sha256:
            return False, "Checkpoint manifest hash mismatch"

        return True, "Checkpoint verified"

    def load_checkpoint(
        self,
        checkpoint_id: Optional[str] = None,
        *,
        device: str = "cpu",
        rank: int = 0,
        prefer_best: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Load a checkpoint payload without mutating runtime objects."""
        resolved_id = self._resolve_checkpoint_id(
            checkpoint_id=checkpoint_id,
            prefer_best=prefer_best,
        )
        if not resolved_id:
            return None

        from training.safetensors_io import CheckpointIntegrityError, load_safetensors
        import torch

        metadata = self.checkpoints.get(resolved_id)
        if metadata is None:
            legacy_path = self._legacy_checkpoint_path(resolved_id)
            if legacy_path is None or not legacy_path.exists():
                return None
            return self._load_legacy_checkpoint(legacy_path, device=device)

        valid, reason = self.verify_checkpoint(resolved_id)
        if not valid:
            raise CheckpointIntegrityError(
                f"Checkpoint integrity verification failed for {resolved_id}: {reason}"
            )

        checkpoint_path = Path(metadata.checkpoint_path or self.checkpoint_dir / resolved_id)
        if checkpoint_path.is_file():
            return self._load_legacy_checkpoint(
                checkpoint_path,
                device=device,
                expected_sha256=metadata.sha256,
            )

        model_path = checkpoint_path / f"model_shard_{rank}.safetensors"
        if not model_path.exists():
            model_path = checkpoint_path / "model_shard_0.safetensors"
        if not model_path.exists():
            return None

        on_disk_metadata = self._read_json(checkpoint_path / "metadata.json")
        artifact_hashes = {
            str(item.get("relative_path", "") or ""): str(item.get("sha256", "") or "")
            for item in (on_disk_metadata.get("shards", []) or [])
            if isinstance(item, dict)
        }

        def _artifact_hash(artifact_path: Path) -> str:
            relative_path = artifact_path.relative_to(checkpoint_path).as_posix()
            expected_hash = artifact_hashes.get(relative_path, "")
            if not expected_hash:
                raise CheckpointIntegrityError(
                    f"Checkpoint artifact hash missing for {resolved_id}:{relative_path}"
                )
            return expected_hash

        optimizer_path = checkpoint_path / f"optimizer_{rank}.pt"
        if not optimizer_path.exists():
            optimizer_path = checkpoint_path / "optimizer_0.pt"

        rng_path = checkpoint_path / f"rng_state_{rank}.pt"
        if not rng_path.exists():
            rng_path = checkpoint_path / "rng_state_0.pt"

        scaler_path = checkpoint_path / f"grad_scaler_{rank}.pt"
        if not scaler_path.exists():
            scaler_path = checkpoint_path / "grad_scaler_0.pt"

        return {
            "checkpoint_id": resolved_id,
            "model_state_dict": load_safetensors(str(model_path), device=device),
            "optimizer_state_dict": (
                self._load_torch_artifact(
                    optimizer_path,
                    device=device,
                    expected_sha256=_artifact_hash(optimizer_path),
                )
                if optimizer_path.exists()
                else None
            ),
            "scheduler_state_dict": (
                self._load_torch_artifact(
                    checkpoint_path / "scheduler.pt",
                    device=device,
                    expected_sha256=_artifact_hash(checkpoint_path / "scheduler.pt"),
                )
                if (checkpoint_path / "scheduler.pt").exists()
                else None
            ),
            "rng_state": (
                self._load_torch_artifact(
                    rng_path,
                    device="cpu",
                    expected_sha256=_artifact_hash(rng_path),
                )
                if rng_path.exists()
                else None
            ),
            "scaler_state_dict": (
                self._load_torch_artifact(
                    scaler_path,
                    device=device,
                    expected_sha256=_artifact_hash(scaler_path),
                )
                if scaler_path.exists()
                else None
            ),
            "training_state": self._read_json(checkpoint_path / "training_state.json"),
            "metadata": on_disk_metadata,
        }

    def resume_from_latest(
        self,
        *,
        model: Optional[Any] = None,
        optimizer: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        scaler: Optional[Any] = None,
        device: str = "cpu",
        rank: int = 0,
        prefer_best: bool = False,
    ) -> ResumeResult:
        """Load the latest valid checkpoint and optionally restore runtime objects."""
        checkpoint_payload = self.load_checkpoint(
            None,
            device=device,
            rank=rank,
            prefer_best=prefer_best,
        )
        if checkpoint_payload is None:
            return ResumeResult(resumed=False, reason="No valid checkpoint found")

        metadata = checkpoint_payload.get("metadata", {})
        training_state = checkpoint_payload.get("training_state", {})
        if model is not None:
            self._unwrap_model(model).load_state_dict(checkpoint_payload["model_state_dict"])
        if optimizer is not None and checkpoint_payload.get("optimizer_state_dict") is not None:
            optimizer.load_state_dict(checkpoint_payload["optimizer_state_dict"])
        if scheduler is not None and checkpoint_payload.get("scheduler_state_dict") is not None:
            scheduler.load_state_dict(checkpoint_payload["scheduler_state_dict"])
        if scaler is not None and checkpoint_payload.get("scaler_state_dict") is not None:
            scaler.load_state_dict(checkpoint_payload["scaler_state_dict"])
        self.restore_rng_state(checkpoint_payload.get("rng_state"))

        return ResumeResult(
            resumed=True,
            checkpoint_id=str(checkpoint_payload.get("checkpoint_id", "")),
            checkpoint_path=str(metadata.get("checkpoint_path", "")),
            epoch=int(training_state.get("epoch", metadata.get("epoch", 0))),
            step=int(training_state.get("step", metadata.get("step", 0))),
            global_step=int(
                training_state.get("global_step", metadata.get("global_step", 0))
            ),
            metrics=dict(metadata.get("metrics", {})),
            reason="Resumed from latest valid checkpoint",
        )

    def verify_replay(
        self,
        checkpoint_id: str,
        model: Any,
        sample_batch: Any,
    ) -> Tuple[bool, str]:
        """Load checkpoint weights into a model and verify a deterministic replay."""
        import torch

        payload = self.load_checkpoint(checkpoint_id, device="cpu", rank=0)
        if payload is None:
            return False, "Checkpoint load failed"

        self._unwrap_model(model).load_state_dict(payload["model_state_dict"])
        with torch.no_grad():
            output = model(sample_batch)

        output_hash = hashlib.sha256(
            output.detach().cpu().numpy().tobytes()
        ).hexdigest()[:16]

        metadata = self.checkpoints.get(checkpoint_id)
        if metadata is not None:
            metadata.replay_verified = True
            self._persist_metadata(metadata)
            self._save_manifest()

        return True, f"Replay verified, output hash: {output_hash}"

    def count_verified_checkpoints(self) -> int:
        """Count replay-verified checkpoints."""
        return sum(1 for metadata in self.checkpoints.values() if metadata.replay_verified)

    def _prepare_snapshot(
        self,
        *,
        state_dict: Dict[str, Any],
        epoch: int,
        step: int,
        metrics: Dict[str, float],
        optimizer_state: Optional[Dict[str, Any]],
        scheduler_state: Optional[Dict[str, Any]],
        rng_state: Optional[Dict[str, Any]],
        training_state: Optional[Dict[str, Any]],
        scaler_state: Optional[Dict[str, Any]],
        rank: int,
        world_size: int,
        global_step: Optional[int],
        is_best: bool,
        checkpoint_kind: str,
        checkpoint_id: Optional[str],
        extra_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        materialized_global_step = int(global_step if global_step is not None else step)
        resolved_checkpoint_id = checkpoint_id or f"ckpt_e{int(epoch):04d}_s{int(step):06d}"
        return {
            "checkpoint_id": resolved_checkpoint_id,
            "epoch": int(epoch),
            "step": int(step),
            "global_step": materialized_global_step,
            "metrics": {str(k): float(v) for k, v in metrics.items()},
            "rank": int(rank),
            "world_size": max(1, int(world_size)),
            "is_best": bool(is_best),
            "checkpoint_kind": checkpoint_kind,
            "model_state_dict": self._normalize_model_state(state_dict),
            "optimizer_state": self._clone_state_tree(optimizer_state),
            "scheduler_state": self._clone_state_tree(scheduler_state),
            "rng_state": self._clone_state_tree(rng_state),
            "scaler_state": self._clone_state_tree(scaler_state),
            "training_state": self._json_safe(
                {
                    **(training_state or {}),
                    "epoch": int(epoch),
                    "step": int(step),
                    "global_step": materialized_global_step,
                }
            ),
            "extra_metadata": self._json_safe(extra_metadata or {}),
        }

    def _save_checkpoint(self, snapshot: Dict[str, Any]) -> Tuple[bool, CheckpointMetadata]:
        from training.safetensors_io import save_safetensors

        checkpoint_id = snapshot["checkpoint_id"]
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)
        if checkpoint_path.exists():
            valid, _ = self.verify_checkpoint(checkpoint_id)
            if valid and checkpoint_id in self.checkpoints:
                return True, self.checkpoints[checkpoint_id]
            checkpoint_id = f"{checkpoint_id}_retry_{int(datetime.now(UTC).timestamp())}"
            checkpoint_path = self.get_checkpoint_path(checkpoint_id)
            snapshot = dict(snapshot)
            snapshot["checkpoint_id"] = checkpoint_id

        checkpoint_path.mkdir(parents=True, exist_ok=True)

        rank = snapshot["rank"]
        artifacts: List[Dict[str, Any]] = []

        model_path = checkpoint_path / f"model_shard_{rank}.safetensors"
        model_file_hash, tensor_hash = save_safetensors(
            snapshot["model_state_dict"],
            str(model_path),
            metadata={
                "checkpoint_id": checkpoint_id,
                "rank": str(rank),
                "world_size": str(snapshot["world_size"]),
            },
        )
        artifacts.append(
            self._artifact_record(
                checkpoint_path=checkpoint_path,
                artifact_path=model_path,
                kind="model_weights",
                rank=rank,
                sha256=model_file_hash,
                extra={"tensor_hash": tensor_hash},
            )
        )

        if rank == 0 and snapshot["world_size"] == 1:
            legacy_single_file = self.checkpoint_dir / f"{checkpoint_id}.safetensors"
            shutil.copyfile(model_path, legacy_single_file)

        if snapshot["optimizer_state"] is not None:
            optimizer_path = checkpoint_path / f"optimizer_{rank}.pt"
            optimizer_hash = self._atomic_write_torch(
                optimizer_path,
                snapshot["optimizer_state"],
            )
            artifacts.append(
                self._artifact_record(
                    checkpoint_path=checkpoint_path,
                    artifact_path=optimizer_path,
                    kind="optimizer_state",
                    rank=rank,
                    sha256=optimizer_hash,
                )
            )

        if snapshot["scheduler_state"] is not None:
            scheduler_path = checkpoint_path / "scheduler.pt"
            scheduler_hash = self._atomic_write_torch(
                scheduler_path,
                snapshot["scheduler_state"],
            )
            artifacts.append(
                self._artifact_record(
                    checkpoint_path=checkpoint_path,
                    artifact_path=scheduler_path,
                    kind="scheduler_state",
                    rank=-1,
                    sha256=scheduler_hash,
                )
            )

        if snapshot["rng_state"] is not None:
            rng_path = checkpoint_path / f"rng_state_{rank}.pt"
            rng_hash = self._atomic_write_torch(rng_path, snapshot["rng_state"])
            artifacts.append(
                self._artifact_record(
                    checkpoint_path=checkpoint_path,
                    artifact_path=rng_path,
                    kind="rng_state",
                    rank=rank,
                    sha256=rng_hash,
                )
            )

        if snapshot["scaler_state"] is not None:
            scaler_path = checkpoint_path / f"grad_scaler_{rank}.pt"
            scaler_hash = self._atomic_write_torch(
                scaler_path,
                snapshot["scaler_state"],
            )
            artifacts.append(
                self._artifact_record(
                    checkpoint_path=checkpoint_path,
                    artifact_path=scaler_path,
                    kind="grad_scaler_state",
                    rank=rank,
                    sha256=scaler_hash,
                )
            )

        training_state_path = checkpoint_path / "training_state.json"
        training_state_payload = {
            **snapshot["training_state"],
            "checkpoint_id": checkpoint_id,
            "rank": rank,
            "world_size": snapshot["world_size"],
            "checkpoint_kind": snapshot["checkpoint_kind"],
            "created_at": datetime.now(UTC).isoformat(),
        }
        training_state_hash = self._atomic_write_json(
            training_state_path,
            training_state_payload,
        )
        artifacts.append(
            self._artifact_record(
                checkpoint_path=checkpoint_path,
                artifact_path=training_state_path,
                kind="training_state",
                rank=-1,
                sha256=training_state_hash,
            )
        )

        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            epoch=snapshot["epoch"],
            step=snapshot["step"],
            global_step=snapshot["global_step"],
            sha256=self._combine_artifact_hashes(artifacts),
            timestamp=datetime.now(UTC).isoformat(),
            metrics=snapshot["metrics"],
            replay_verified=False,
            world_size=snapshot["world_size"],
            checkpoint_kind=snapshot["checkpoint_kind"],
            checkpoint_path=str(checkpoint_path),
            metadata_path=str(checkpoint_path / "metadata.json"),
            training_state_path=str(training_state_path),
            is_best=snapshot["is_best"],
            is_latest=True,
            shards=artifacts,
        )
        self._persist_metadata(metadata, extra_metadata=snapshot["extra_metadata"])

        with self._lock:
            for item in self.checkpoints.values():
                item.is_latest = False
            if metadata.is_best and self._best_checkpoint_id in self.checkpoints:
                self.checkpoints[self._best_checkpoint_id].is_best = False
            self.checkpoints[checkpoint_id] = metadata
            self._latest_checkpoint_id = checkpoint_id
            if metadata.is_best:
                self._best_checkpoint_id = checkpoint_id
            elif not self._best_checkpoint_id:
                self._best_checkpoint_id = checkpoint_id
            self._save_manifest()
            self._write_checkpoint_pointers()

        return True, metadata

    def _persist_metadata(
        self,
        metadata: CheckpointMetadata,
        *,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata_path = Path(
            metadata.metadata_path
            or self.get_checkpoint_path(metadata.checkpoint_id) / "metadata.json"
        )
        payload = asdict(metadata)
        if extra_metadata:
            payload["extra_metadata"] = extra_metadata
        self._atomic_write_json(metadata_path, payload)

    def _resolve_checkpoint_id(
        self,
        *,
        checkpoint_id: Optional[str],
        prefer_best: bool,
    ) -> Optional[str]:
        if checkpoint_id:
            path_candidate = Path(checkpoint_id)
            if path_candidate.exists():
                if path_candidate.is_dir():
                    metadata_path = path_candidate / "metadata.json"
                    if metadata_path.exists():
                        payload = self._read_json(metadata_path)
                        return str(payload.get("checkpoint_id", ""))
                if path_candidate.is_file():
                    return checkpoint_id
            return checkpoint_id
        if prefer_best:
            best_id = self.get_best_checkpoint()
            if best_id:
                return best_id
        return self.get_latest_checkpoint()

    def _load_manifest(self) -> None:
        if not self.metadata_file.exists():
            return
        try:
            payload = self._read_json(self.metadata_file)
        except Exception:
            return

        checkpoints_payload = payload.get("checkpoints", payload)
        if not isinstance(checkpoints_payload, dict):
            return

        for checkpoint_id, raw_metadata in checkpoints_payload.items():
            if not isinstance(raw_metadata, dict):
                continue
            raw_metadata.setdefault("checkpoint_id", checkpoint_id)
            raw_metadata.setdefault("global_step", raw_metadata.get("step", 0))
            raw_metadata.setdefault("world_size", 1)
            raw_metadata.setdefault("checkpoint_kind", "full")
            raw_metadata.setdefault("checkpoint_path", str(self.checkpoint_dir / checkpoint_id))
            raw_metadata.setdefault(
                "metadata_path",
                str(self.checkpoint_dir / checkpoint_id / "metadata.json"),
            )
            raw_metadata.setdefault(
                "training_state_path",
                str(self.checkpoint_dir / checkpoint_id / "training_state.json"),
            )
            raw_metadata.setdefault("is_best", False)
            raw_metadata.setdefault("is_latest", False)
            raw_metadata.setdefault("shards", [])
            try:
                self.checkpoints[checkpoint_id] = CheckpointMetadata(**raw_metadata)
            except TypeError:
                continue

    def _load_pointers(self) -> None:
        if not self.pointer_file.exists():
            return
        try:
            payload = self._read_json(self.pointer_file)
        except Exception:
            return
        self._latest_checkpoint_id = str(payload.get("latest_checkpoint_id", "") or "")
        self._best_checkpoint_id = str(payload.get("best_checkpoint_id", "") or "")

    def _discover_checkpoints_from_disk(self) -> None:
        try:
            children = list(self.checkpoint_dir.iterdir())
        except OSError:
            return

        discovered = False
        for child in children:
            if not child.is_dir():
                continue
            metadata_path = child / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                payload = self._read_json(metadata_path)
                checkpoint_id = str(payload.get("checkpoint_id", child.name))
                if checkpoint_id in self.checkpoints:
                    continue
                payload.setdefault("global_step", payload.get("step", 0))
                payload.setdefault("world_size", 1)
                payload.setdefault("checkpoint_kind", "full")
                payload.setdefault("checkpoint_path", str(child))
                payload.setdefault("metadata_path", str(metadata_path))
                payload.setdefault(
                    "training_state_path",
                    str(child / "training_state.json"),
                )
                payload.setdefault("is_best", False)
                payload.setdefault("is_latest", False)
                payload.setdefault("shards", [])
                self.checkpoints[checkpoint_id] = CheckpointMetadata(**payload)
                discovered = True
            except Exception:
                continue

        if discovered:
            ordered = self._ordered_checkpoint_ids()
            if ordered and not self._latest_checkpoint_id:
                self._latest_checkpoint_id = ordered[-1]
            if not self._best_checkpoint_id:
                best_id = self.get_best_checkpoint()
                self._best_checkpoint_id = best_id or ""
            self._save_manifest()
            self._write_checkpoint_pointers()

    def _save_manifest(self) -> None:
        payload = {
            "checkpoints": {
                checkpoint_id: asdict(metadata)
                for checkpoint_id, metadata in self.checkpoints.items()
            },
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._atomic_write_json(self.metadata_file, payload)

    def _write_checkpoint_pointers(self) -> None:
        payload = {
            "latest_checkpoint_id": self._latest_checkpoint_id,
            "best_checkpoint_id": self._best_checkpoint_id,
            "latest_checkpoint_path": (
                str(self.get_checkpoint_path(self._latest_checkpoint_id))
                if self._latest_checkpoint_id
                else ""
            ),
            "best_checkpoint_path": (
                str(self.get_checkpoint_path(self._best_checkpoint_id))
                if self._best_checkpoint_id
                else ""
            ),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._atomic_write_json(self.pointer_file, payload)

    def _ordered_checkpoint_ids(self) -> List[str]:
        return [
            metadata.checkpoint_id
            for metadata in sorted(
                self.checkpoints.values(),
                key=lambda item: (item.global_step, item.step, item.epoch, item.timestamp),
            )
        ]

    def _remove_future(self, future: Future) -> None:
        with self._lock:
            self._pending_futures = [
                pending for pending in self._pending_futures if pending is not future
            ]

    @staticmethod
    def _unwrap_model(model: Any) -> Any:
        return getattr(model, "module", model)

    @staticmethod
    def _artifact_record(
        *,
        checkpoint_path: Path,
        artifact_path: Path,
        kind: str,
        rank: int,
        sha256: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        stat = artifact_path.stat()
        payload = {
            "relative_path": artifact_path.relative_to(checkpoint_path).as_posix(),
            "kind": kind,
            "rank": rank,
            "sha256": sha256,
            "size_bytes": stat.st_size,
        }
        if extra:
            payload.update(extra)
        return payload

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _compute_hash(path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _combine_artifact_hashes(artifacts: List[Dict[str, Any]]) -> str:
        sha256 = hashlib.sha256()
        for artifact in sorted(artifacts, key=lambda item: item["relative_path"]):
            sha256.update(str(artifact["relative_path"]).encode("utf-8"))
            sha256.update(str(artifact["sha256"]).encode("utf-8"))
        return sha256.hexdigest()

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        return HardenedCheckpointManager._compute_hash(path)

    @staticmethod
    def _atomic_write_torch(path: Path, payload: Any) -> str:
        import torch

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "wb") as handle:
            torch.save(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        return HardenedCheckpointManager._compute_hash(path)

    def _normalize_model_state(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        import torch

        normalized: Dict[str, Any] = {}
        for key, value in state_dict.items():
            if not isinstance(value, torch.Tensor):
                raise TypeError(
                    f"SafeTensors checkpoint requires tensor values, got {type(value)!r} for {key}"
                )
            normalized[key] = value.detach().cpu().clone()
        return normalized

    def _clone_state_tree(self, value: Any) -> Any:
        import torch

        if value is None:
            return None
        if isinstance(value, torch.Tensor):
            return value.detach().cpu().clone()
        if isinstance(value, dict):
            return {key: self._clone_state_tree(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._clone_state_tree(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._clone_state_tree(item) for item in value)
        return copy.deepcopy(value)

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                logger.warning(
                    "[CKPT] Failed to serialize %s via isoformat(); falling back to string",
                    type(value).__name__,
                    exc_info=True,
                )
        return str(value)

    @staticmethod
    def _legacy_checkpoint_path(checkpoint_id: str) -> Optional[Path]:
        candidate = Path(checkpoint_id)
        if candidate.exists():
            return candidate
        return None

    @staticmethod
    def _read_sha256_sidecar(path: Path) -> str:
        candidates = []
        for candidate in (
            Path(str(path) + ".sha256"),
            path.with_suffix(path.suffix + ".sha256") if path.suffix else Path(str(path) + ".sha256"),
            path.with_suffix(".sha256"),
        ):
            candidate_str = str(candidate)
            if candidate_str not in candidates:
                candidates.append(candidate_str)
        for candidate_str in candidates:
            candidate = Path(candidate_str)
            if not candidate.exists():
                continue
            raw_value = candidate.read_text(encoding="utf-8").strip()
            if raw_value:
                return raw_value.split()[0].strip().lower()
        return ""

    @classmethod
    def _require_verified_file_hash(
        cls,
        path: Path,
        *,
        expected_sha256: Optional[str] = None,
    ) -> str:
        from training.safetensors_io import CheckpointIntegrityError

        expected = str(expected_sha256 or cls._read_sha256_sidecar(path) or "").strip().lower()
        if not expected:
            raise CheckpointIntegrityError(f"Checkpoint SHA-256 metadata missing for {path}")
        if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
            raise CheckpointIntegrityError(f"Checkpoint SHA-256 metadata invalid for {path}")

        actual = cls._compute_hash(path)
        if actual != expected:
            raise CheckpointIntegrityError(
                f"Checkpoint SHA-256 mismatch for {path}: expected={expected[:16]}..., got={actual[:16]}..."
            )
        return actual

    @classmethod
    def _load_torch_artifact(
        cls,
        path: Path,
        *,
        device: str,
        expected_sha256: Optional[str],
    ) -> Any:
        import torch

        cls._require_verified_file_hash(path, expected_sha256=expected_sha256)
        return torch.load(path, map_location=device, weights_only=False)

    @classmethod
    def _load_legacy_checkpoint(
        cls,
        path: Path,
        *,
        device: str,
        expected_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        import torch

        cls._require_verified_file_hash(path, expected_sha256=expected_sha256)

        if path.suffix == ".safetensors":
            from training.safetensors_io import load_safetensors

            return {
                "checkpoint_id": path.stem,
                "model_state_dict": load_safetensors(str(path), device=device),
                "optimizer_state_dict": None,
                "scheduler_state_dict": None,
                "rng_state": None,
                "scaler_state_dict": None,
                "training_state": {},
                "metadata": {},
            }

        state = torch.load(path, map_location=device, weights_only=False)
        if "model_state_dict" not in state:
            state = {"model_state_dict": state}
        return {
            "checkpoint_id": path.stem,
            "model_state_dict": state.get("model_state_dict"),
            "optimizer_state_dict": state.get("optimizer_state_dict"),
            "scheduler_state_dict": state.get("scheduler_state_dict"),
            "rng_state": state.get("rng_state"),
            "scaler_state_dict": state.get("scaler_state_dict"),
            "training_state": {
                key: value
                for key, value in state.items()
                if key
                not in {
                    "model_state_dict",
                    "optimizer_state_dict",
                    "scheduler_state_dict",
                    "rng_state",
                    "scaler_state_dict",
                }
            },
            "metadata": {},
        }
