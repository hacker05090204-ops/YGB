from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from impl_v1.training.distributed.drift_guard import DriftGuard
from impl_v1.training.safety.overfit_guard import OverfitGuard
from impl_v1.unified.memory import UnifiedMemoryStore
from storage_backend import get_storage
from training.safetensors_io import load_safetensors, save_safetensors

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_SPECIALTIES = (
    "api",
    "mobile",
    "subdomain",
    "auth",
    "backend",
    "frontend",
    "cloud",
    "storage",
    "database",
    "network",
    "browser",
    "android",
    "ios",
    "firmware",
    "payments",
    "identity",
    "telemetry",
    "ml_pipeline",
    "data_platform",
    "integration",
    "security",
    "governance",
    "infrastructure",
)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_json(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return repr(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(_normalize_json(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    _ensure_dir(path.parent)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _atomic_write_torch(path: Path, payload: Any) -> None:
    import torch

    _ensure_dir(path.parent)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "wb") as handle:
        torch.save(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_text(sample: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in (
        "title",
        "summary",
        "description",
        "endpoint",
        "parameters",
        "payload",
        "exploit_vector",
        "impact",
        "source",
        "source_tag",
        "bug_type",
        "category",
    ):
        value = sample.get(key)
        if value:
            parts.append(str(value))
    tags = sample.get("tags")
    if isinstance(tags, (list, tuple, set)):
        parts.extend(str(tag) for tag in tags if tag)
    return " ".join(parts).lower()


def _sample_fingerprint(sample: Mapping[str, Any]) -> str:
    normalized = {
        "agent_id": sample.get("agent_id", ""),
        "title": sample.get("title", ""),
        "summary": sample.get("summary", ""),
        "description": sample.get("description", ""),
        "endpoint": sample.get("endpoint", ""),
        "parameters": sample.get("parameters", ""),
        "payload": sample.get("payload", sample.get("exploit_vector", "")),
        "impact": sample.get("impact", ""),
        "source": sample.get("source", sample.get("source_tag", "")),
        "bug_type": sample.get("bug_type", sample.get("category", "")),
        "tags": sorted(str(tag).lower() for tag in sample.get("tags", []) or []),
    }
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(_normalize_json(payload), sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _checkpoint_step_value(checkpoint_id: str) -> int:
    prefix, _, suffix = checkpoint_id.partition("_")
    if prefix == "step" and suffix.isdigit():
        return int(suffix)
    try:
        return int(checkpoint_id.rsplit("_", 1)[-1])
    except ValueError:
        return -1


def _load_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else dict(default or {})
    except (OSError, json.JSONDecodeError):
        return dict(default or {})


@dataclass(frozen=True)
class AgentIsolationProfile:
    agent_id: str
    role: str
    parameter_count: int = 130_000_000
    required_keywords: Tuple[str, ...] = ()
    blocked_keywords: Tuple[str, ...] = ()
    allowed_sources: Tuple[str, ...] = ()
    allowed_bug_types: Tuple[str, ...] = ()
    notes: str = ""


@dataclass
class DatasetValidationReport:
    agent_id: str
    dataset_hash: str
    dataset_path: str
    accepted_count: int
    rejected_count: int
    deduplicated_count: int
    contamination_rejections: int
    accepted_fingerprints: List[str] = field(default_factory=list)
    rejected_samples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TrainingCheckpoint:
    agent_id: str
    checkpoint_id: str
    checkpoint_dir: str
    step: int
    epoch: int
    metrics: Dict[str, float]
    is_best: bool
    is_latest: bool
    created_at: str
    artifact_hashes: Dict[str, str]
    backup_receipt_path: str = ""


@dataclass
class CheckpointRestoreResult:
    restored: bool
    agent_id: str
    checkpoint_id: str = ""
    checkpoint_dir: str = ""
    epoch: int = 0
    step: int = 0
    metrics: Dict[str, float] = field(default_factory=dict)
    reason: str = ""


@dataclass
class BackupReceipt:
    agent_id: str
    checkpoint_id: str
    primary_path: str
    secondary_path: str = ""
    hybrid_paths: Dict[str, str] = field(default_factory=dict)
    remote_paths: List[str] = field(default_factory=list)
    completed_locations: int = 1
    errors: List[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class IncrementalTrainingRequest:
    request_id: str
    agent_id: str
    target: str
    fallback_target: str
    reason: str
    dataset_path: str
    bug_fingerprint: str
    created_at: str


@dataclass
class StartupRecoveryAgentStatus:
    agent_id: str
    restored: bool = False
    resumed_checkpoint_id: str = ""
    resumed_step: int = 0
    resumed_epoch: int = 0
    pending_request_ids: List[str] = field(default_factory=list)
    rerouted_request_ids: List[str] = field(default_factory=list)
    repaired_backups: List[str] = field(default_factory=list)
    invalid_checkpoints: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)


@dataclass
class StartupRecoveryReport:
    recovered_at: str
    availability: Dict[str, bool]
    agents: List[StartupRecoveryAgentStatus] = field(default_factory=list)


@dataclass
class TrainingSafetyDecision:
    pause_training: bool
    rollback_checkpoint_id: str
    reasons: List[str] = field(default_factory=list)
    drift_events: List[Dict[str, Any]] = field(default_factory=list)
    overfit_warning: bool = False


class AsyncCheckpointReplicator:
    """Non-blocking local + remote checkpoint replication."""

    def __init__(
        self,
        *,
        secondary_root: Path,
        hybrid_root: Path,
        remote_prefix: str = "training_checkpoints",
        max_workers: int = 2,
    ):
        self.secondary_root = secondary_root
        self.hybrid_root = hybrid_root
        self.remote_prefix = remote_prefix.strip("/").replace("\\", "/")
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="checkpoint-backup",
        )
        self._futures: List[Future] = []
        self._lock = Lock()
        _ensure_dir(secondary_root)
        _ensure_dir(hybrid_root)

    def replicate_async(
        self,
        *,
        agent_id: str,
        checkpoint_id: str,
        checkpoint_dir: Path,
        execution_target: str,
    ) -> Future:
        future = self._executor.submit(
            self._replicate,
            agent_id=agent_id,
            checkpoint_id=checkpoint_id,
            checkpoint_dir=checkpoint_dir,
            execution_target=execution_target,
        )
        with self._lock:
            self._futures.append(future)
        future.add_done_callback(self._remove_future)
        return future

    def wait(self, timeout: Optional[float] = None) -> None:
        with self._lock:
            futures = list(self._futures)
        for future in futures:
            future.result(timeout=timeout)

    def close(self) -> None:
        self.wait()
        self._executor.shutdown(wait=True)

    def _remove_future(self, future: Future) -> None:
        with self._lock:
            self._futures = [item for item in self._futures if item is not future]

    def _replicate(
        self,
        *,
        agent_id: str,
        checkpoint_id: str,
        checkpoint_dir: Path,
        execution_target: str,
    ) -> BackupReceipt:
        receipt = BackupReceipt(
            agent_id=agent_id,
            checkpoint_id=checkpoint_id,
            primary_path=str(checkpoint_dir),
            completed_locations=1,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        peer_target = "local_gpu" if execution_target == "vps" else "vps"
        try:
            secondary_dir = self.secondary_root / f"agent_{agent_id}" / checkpoint_id
            self._copy_checkpoint_tree(checkpoint_dir, secondary_dir)
            receipt.secondary_path = str(secondary_dir)
            receipt.completed_locations += 1
        except Exception as exc:
            receipt.errors.append(f"secondary_backup_failed: {exc}")

        try:
            hybrid_dir = self.hybrid_root / peer_target / f"agent_{agent_id}" / checkpoint_id
            self._copy_checkpoint_tree(checkpoint_dir, hybrid_dir)
            receipt.hybrid_paths[peer_target] = str(hybrid_dir)
            receipt.completed_locations += 1
        except Exception as exc:
            receipt.errors.append(f"hybrid_sync_failed: {exc}")

        try:
            storage = get_storage()
            remote_paths = self._mirror_remote(storage, agent_id, checkpoint_id, checkpoint_dir)
            if remote_paths:
                receipt.remote_paths = remote_paths
                receipt.completed_locations += 1
        except Exception as exc:
            receipt.errors.append(f"remote_backup_failed: {exc}")

        _atomic_write_json(checkpoint_dir / "backup_receipt.json", asdict(receipt))
        return receipt

    @staticmethod
    def _copy_checkpoint_tree(source: Path, destination: Path) -> None:
        _ensure_dir(destination.parent)
        temp_destination = destination.with_name(f"{destination.name}.tmp")
        if temp_destination.exists():
            shutil.rmtree(temp_destination)
        shutil.copytree(source, temp_destination)
        if destination.exists():
            shutil.rmtree(temp_destination)
            return
        os.replace(temp_destination, destination)

    def _mirror_remote(
        self,
        storage: Any,
        agent_id: str,
        checkpoint_id: str,
        checkpoint_dir: Path,
    ) -> List[str]:
        remote_paths: List[str] = []
        for artifact in sorted(checkpoint_dir.iterdir()):
            if not artifact.is_file():
                continue
            relative = "/".join(
                (
                    self.remote_prefix,
                    f"agent_{agent_id}",
                    checkpoint_id,
                    artifact.name,
                )
            )
            if storage.write(relative, artifact.read_bytes()):
                remote_paths.append(relative)
        return remote_paths


class ProductionTrainingOrchestrator:
    """Agent-isolated training runtime with crash-safe checkpoints and feedback learning."""

    def __init__(
        self,
        *,
        secure_root: str = "secure_data",
        checkpoint_step_interval: int = 1_000,
        checkpoint_time_interval_sec: int = 900,
        bootstrap_default_agents: bool = True,
    ):
        self.secure_root = Path(secure_root)
        self.agent_root = self.secure_root / "agents"
        self.checkpoint_root = self.secure_root / "checkpoints"
        self.secondary_backup_root = self.secure_root / "secondary_backups"
        self.hybrid_root = self.secure_root / "hybrid_sync"
        self.trace_root = self.secure_root / "training_traces"
        self.training_queue_root = self.secure_root / "training_queue"
        self.isolation_root = self.secure_root / "agent_isolation"
        self.memory_path = self.secure_root / "experience_memory.json"
        self.state_path = self.secure_root / "production_training_state.json"
        self.global_index_path = self.isolation_root / "global_sample_index.json"
        self._lock = Lock()
        self.checkpoint_step_interval = max(1, int(checkpoint_step_interval))
        self.checkpoint_time_interval_sec = max(1, int(checkpoint_time_interval_sec))
        self._profiles: Dict[str, AgentIsolationProfile] = {}
        self._drift_guards: Dict[str, DriftGuard] = {}
        self._overfit_guards: Dict[str, OverfitGuard] = {}
        self._memory = UnifiedMemoryStore(str(self.memory_path))
        self._replicator = AsyncCheckpointReplicator(
            secondary_root=self.secondary_backup_root,
            hybrid_root=self.hybrid_root,
        )
        self._runtime_state = self._load_runtime_state()
        self._availability = dict(
            self._runtime_state.get(
                "availability",
                {"vps": True, "local_gpu": True, "cpu": True},
            )
        )
        for path in (
            self.secure_root,
            self.agent_root,
            self.checkpoint_root,
            self.secondary_backup_root,
            self.hybrid_root,
            self.trace_root,
            self.training_queue_root,
            self.isolation_root,
        ):
            _ensure_dir(path)
        self._load_profiles()
        if bootstrap_default_agents and not self._profiles:
            self._bootstrap_default_profiles()

    def close(self) -> None:
        self._replicator.close()

    def set_runtime_availability(
        self,
        *,
        vps_available: Optional[bool] = None,
        local_gpu_available: Optional[bool] = None,
        cpu_available: Optional[bool] = None,
    ) -> None:
        if vps_available is not None:
            self._availability["vps"] = bool(vps_available)
        if local_gpu_available is not None:
            self._availability["local_gpu"] = bool(local_gpu_available)
        if cpu_available is not None:
            self._availability["cpu"] = bool(cpu_available)
        self._persist_runtime_state()

    def register_agent(self, profile: AgentIsolationProfile) -> AgentIsolationProfile:
        with self._lock:
            self._profiles[profile.agent_id] = profile
            self._drift_guards.setdefault(profile.agent_id, DriftGuard())
            self._overfit_guards.setdefault(profile.agent_id, OverfitGuard())
            profile_path = self._profile_path(profile.agent_id)
            _atomic_write_json(profile_path, asdict(profile))
            self._persist_runtime_state()
        self._log_event(
            profile.agent_id,
            "agent_registered",
            {
                "role": profile.role,
                "parameter_count": profile.parameter_count,
                "required_keywords": list(profile.required_keywords),
                "blocked_keywords": list(profile.blocked_keywords),
            },
        )
        return profile

    def get_profile(self, agent_id: str) -> AgentIsolationProfile:
        if agent_id not in self._profiles:
            raise KeyError(f"Unknown agent: {agent_id}")
        return self._profiles[agent_id]

    def validate_dataset(
        self,
        agent_id: str,
        samples: Sequence[Mapping[str, Any]],
        *,
        dataset_name: str = "validated",
    ) -> DatasetValidationReport:
        profile = self.get_profile(agent_id)
        global_index = _load_json(self.global_index_path, default={})
        agent_index_path = self._agent_dataset_root(agent_id) / "sample_index.json"
        agent_index = _load_json(agent_index_path, default={})
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        seen_in_batch: set[str] = set()
        deduplicated_count = 0
        contamination_rejections = 0

        known_agent_ids = set(self._profiles.keys())
        for raw_sample in samples:
            sample = dict(raw_sample)
            fingerprint = str(sample.get("fingerprint") or _sample_fingerprint(sample))
            explicit_agent = str(sample.get("agent_id", "") or "").strip()
            if explicit_agent and explicit_agent != agent_id:
                contamination_rejections += 1
                rejected.append(
                    {
                        "fingerprint": fingerprint,
                        "reason": f"explicit_agent_mismatch:{explicit_agent}",
                    }
                )
                continue
            sample["fingerprint"] = fingerprint
            sample["owner_agent_id"] = explicit_agent
            sample["agent_id"] = agent_id

            if fingerprint in seen_in_batch or fingerprint in agent_index:
                deduplicated_count += 1
                continue

            owner = str(global_index.get(fingerprint, "") or "")
            if owner and owner != agent_id:
                contamination_rejections += 1
                rejected.append(
                    {
                        "fingerprint": fingerprint,
                        "reason": f"cross_agent_contamination:{owner}",
                    }
                )
                continue

            explicit_tags = {
                str(tag).strip().lower()
                for tag in sample.get("tags", []) or []
                if str(tag).strip()
            }
            foreign_tags = sorted(
                tag for tag in explicit_tags if tag in known_agent_ids and tag != agent_id
            )
            if foreign_tags:
                contamination_rejections += 1
                rejected.append(
                    {
                        "fingerprint": fingerprint,
                        "reason": f"foreign_agent_tags:{','.join(foreign_tags)}",
                    }
                )
                continue

            valid, reason = self._sample_matches_profile(profile, sample)
            if not valid:
                rejected.append({"fingerprint": fingerprint, "reason": reason})
                continue

            seen_in_batch.add(fingerprint)
            accepted.append(sample)

        dataset_hash = _sha256_bytes(
            json.dumps(_normalize_json(accepted), sort_keys=True).encode("utf-8")
        )
        dataset_path = self._agent_dataset_root(agent_id) / f"{dataset_name}_{dataset_hash[:16]}.jsonl"
        manifest_path = self._agent_dataset_root(agent_id) / f"{dataset_name}_{dataset_hash[:16]}.manifest.json"

        if accepted:
            lines = [
                json.dumps(_normalize_json(item), sort_keys=True) for item in accepted
            ]
            _atomic_write_bytes(dataset_path, ("\n".join(lines) + "\n").encode("utf-8"))
            for sample in accepted:
                agent_index[str(sample["fingerprint"])] = dataset_hash
                global_index[str(sample["fingerprint"])] = agent_id
            _atomic_write_json(agent_index_path, agent_index)
            _atomic_write_json(self.global_index_path, global_index)
        elif dataset_path.exists():
            dataset_path.unlink()

        report = DatasetValidationReport(
            agent_id=agent_id,
            dataset_hash=dataset_hash,
            dataset_path=str(dataset_path),
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            deduplicated_count=deduplicated_count,
            contamination_rejections=contamination_rejections,
            accepted_fingerprints=[str(item["fingerprint"]) for item in accepted],
            rejected_samples=rejected,
        )
        _atomic_write_json(manifest_path, asdict(report))
        self._log_event(agent_id, "dataset_validated", asdict(report))
        return report

    def record_prediction(
        self,
        agent_id: str,
        *,
        prediction_id: str,
        sample: Mapping[str, Any],
        prediction: Mapping[str, Any],
        checkpoint_id: str = "",
    ) -> str:
        namespace = f"experience:{agent_id}"
        entry = self._memory.remember(
            namespace,
            prediction_id,
            prompt=_sample_text(sample),
            response={
                "sample": _normalize_json(sample),
                "prediction": _normalize_json(prediction),
                "checkpoint_id": checkpoint_id,
            },
            tags=("prediction", agent_id),
            references=(checkpoint_id,) if checkpoint_id else (),
        )
        _append_jsonl(
            self._agent_experience_root(agent_id) / "predictions.jsonl",
            {
                "record_id": entry.record_id,
                "prediction_id": prediction_id,
                "checkpoint_id": checkpoint_id,
                "sample": _normalize_json(sample),
                "prediction": _normalize_json(prediction),
                "created_at": entry.created_at,
            },
        )
        self._log_event(
            agent_id,
            "prediction_recorded",
            {"prediction_id": prediction_id, "checkpoint_id": checkpoint_id},
        )
        return entry.record_id

    def record_feedback(
        self,
        agent_id: str,
        *,
        prediction_id: str,
        verified_result: Mapping[str, Any],
        correction_sample: Optional[Mapping[str, Any]] = None,
        was_correct: Optional[bool] = None,
    ) -> IncrementalTrainingRequest:
        namespace = f"experience:{agent_id}"
        existing = self._memory.find(namespace, prediction_id)
        if existing is None:
            raise KeyError(f"Unknown prediction id: {prediction_id}")

        sample = dict(existing.response.get("sample", {}))
        predicted = dict(existing.response.get("prediction", {}))
        truth = _normalize_json(verified_result)
        if was_correct is None:
            was_correct = predicted == truth

        delta = 0.25 if was_correct else -0.5
        self._memory.reinforce(existing.record_id, delta)
        feedback_entry = self._memory.remember(
            f"feedback:{agent_id}",
            prediction_id,
            prompt=existing.prompt,
            response={
                "prediction": predicted,
                "verified_result": truth,
                "sample": sample,
                "was_correct": bool(was_correct),
            },
            tags=("feedback", agent_id, "correct" if was_correct else "correction"),
            references=(existing.record_id,),
        )
        _append_jsonl(
            self._agent_experience_root(agent_id) / "feedback.jsonl",
            {
                "feedback_record_id": feedback_entry.record_id,
                "prediction_id": prediction_id,
                "was_correct": bool(was_correct),
                "verified_result": truth,
                "created_at": feedback_entry.created_at,
            },
        )

        retraining_sample = dict(correction_sample or sample)
        if not retraining_sample:
            retraining_sample = {
                "title": prediction_id,
                "summary": existing.prompt,
            }
        retraining_sample["verified_result"] = truth
        validation = self.validate_dataset(
            agent_id,
            [retraining_sample],
            dataset_name="experience",
        )
        request = self.queue_incremental_training(
            agent_id,
            reason="feedback_correction" if not was_correct else "verified_feedback",
            dataset_path=validation.dataset_path,
            bug_fingerprint=validation.accepted_fingerprints[0] if validation.accepted_fingerprints else prediction_id,
        )
        self._log_event(
            agent_id,
            "feedback_recorded",
            {
                "prediction_id": prediction_id,
                "was_correct": bool(was_correct),
                "request_id": request.request_id,
            },
        )
        return request

    def classify_bug(self, bug_report: Mapping[str, Any]) -> str:
        explicit = str(bug_report.get("agent_id", "") or "").strip()
        if explicit and explicit in self._profiles:
            return explicit

        bug_text = _sample_text(bug_report)
        bug_type = str(bug_report.get("bug_type", bug_report.get("category", ""))).lower()
        tags = {
            str(tag).lower()
            for tag in bug_report.get("tags", []) or []
            if str(tag).strip()
        }
        best_agent = ""
        best_score = -1
        for profile in self._profiles.values():
            score = 0
            keywords = {item.lower() for item in profile.required_keywords}
            blocked = {item.lower() for item in profile.blocked_keywords}
            score += sum(1 for keyword in keywords if keyword and keyword in bug_text)
            if bug_type and bug_type in {item.lower() for item in profile.allowed_bug_types}:
                score += 3
            if profile.role.lower() in bug_text:
                score += 2
            if profile.agent_id.lower() in tags:
                score += 4
            if any(keyword in bug_text for keyword in blocked):
                score -= 5
            if score > best_score:
                best_score = score
                best_agent = profile.agent_id
        if not best_agent:
            raise RuntimeError("No registered agents available for bug routing")
        return best_agent

    def ingest_bug_report(
        self,
        bug_report: Mapping[str, Any],
        *,
        preferred_target: str = "vps",
    ) -> IncrementalTrainingRequest:
        agent_id = self.classify_bug(bug_report)
        validation = self.validate_dataset(
            agent_id,
            [bug_report],
            dataset_name="bug",
        )
        fingerprint = (
            validation.accepted_fingerprints[0]
            if validation.accepted_fingerprints
            else _sample_fingerprint(bug_report)
        )
        request = self.queue_incremental_training(
            agent_id,
            reason=f"new_bug:{bug_report.get('bug_type', bug_report.get('category', 'unknown'))}",
            dataset_path=validation.dataset_path,
            bug_fingerprint=fingerprint,
            preferred_target=preferred_target,
        )
        self._log_event(
            agent_id,
            "bug_ingested",
            {
                "request_id": request.request_id,
                "bug_fingerprint": fingerprint,
                "dataset_path": validation.dataset_path,
            },
        )
        return request

    def queue_incremental_training(
        self,
        agent_id: str,
        *,
        reason: str,
        dataset_path: str,
        bug_fingerprint: str,
        preferred_target: str = "vps",
    ) -> IncrementalTrainingRequest:
        target = self._select_execution_target(preferred_target)
        fallback_target = self._fallback_target(target)
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        request_id = f"REQ-{agent_id.upper()}-{int(time.time() * 1000)}"
        request = IncrementalTrainingRequest(
            request_id=request_id,
            agent_id=agent_id,
            target=target,
            fallback_target=fallback_target,
            reason=reason,
            dataset_path=dataset_path,
            bug_fingerprint=bug_fingerprint,
            created_at=created_at,
        )
        request_path = self.training_queue_root / f"agent_{agent_id}" / f"{request_id}.json"
        _atomic_write_json(request_path, asdict(request))
        self._log_event(
            agent_id,
            "incremental_training_queued",
            asdict(request),
        )
        return request

    def should_checkpoint(
        self,
        agent_id: str,
        *,
        step: int,
        now: Optional[float] = None,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        agent_state = self._agent_runtime_state(agent_id)
        now_ts = time.time() if now is None else float(now)
        last_step = int(agent_state.get("last_checkpoint_step", -1))
        last_at = float(agent_state.get("last_checkpoint_at", 0.0) or 0.0)
        return (
            last_step < 0
            or step - last_step >= self.checkpoint_step_interval
            or now_ts - last_at >= self.checkpoint_time_interval_sec
        )

    def save_checkpoint(
        self,
        agent_id: str,
        *,
        model_state: Mapping[str, Any],
        optimizer_state: Mapping[str, Any],
        scheduler_state: Mapping[str, Any],
        step: int,
        epoch: int,
        metrics: Mapping[str, Any],
        execution_target: str = "vps",
        dataset_hash: str = "",
        force: bool = False,
        rng_state: Optional[Mapping[str, Any]] = None,
        scaler_state: Optional[Mapping[str, Any]] = None,
        extra_state: Optional[Mapping[str, Any]] = None,
    ) -> Optional[TrainingCheckpoint]:
        if not self.should_checkpoint(agent_id, step=step, force=force):
            return None

        checkpoint_id = f"step_{int(step)}"
        checkpoint_dir = self._agent_checkpoint_root(agent_id) / checkpoint_id
        _ensure_dir(checkpoint_dir)

        artifact_hashes: Dict[str, str] = {}
        model_path = checkpoint_dir / "model.safetensors"
        model_file_hash, tensor_hash = save_safetensors(
            dict(model_state),
            str(model_path),
            metadata={
                "agent_id": agent_id,
                "step": str(step),
                "epoch": str(epoch),
                "tensor_hash": "",
            },
        )
        artifact_hashes["model.safetensors"] = model_file_hash
        artifact_hashes["model_tensor_hash"] = tensor_hash

        optimizer_path = checkpoint_dir / "optimizer.pt"
        scheduler_path = checkpoint_dir / "scheduler.pt"
        _atomic_write_torch(optimizer_path, dict(optimizer_state))
        _atomic_write_torch(scheduler_path, dict(scheduler_state))
        artifact_hashes["optimizer.pt"] = _sha256_file(optimizer_path)
        artifact_hashes["scheduler.pt"] = _sha256_file(scheduler_path)

        if rng_state is not None:
            rng_path = checkpoint_dir / "rng_state.pt"
            _atomic_write_torch(rng_path, dict(rng_state))
            artifact_hashes["rng_state.pt"] = _sha256_file(rng_path)
        if scaler_state is not None:
            scaler_path = checkpoint_dir / "scaler.pt"
            _atomic_write_torch(scaler_path, dict(scaler_state))
            artifact_hashes["scaler.pt"] = _sha256_file(scaler_path)

        metrics_dict = {
            str(key): float(value)
            for key, value in metrics.items()
            if isinstance(value, (int, float))
        }
        is_best = self._is_best_checkpoint(agent_id, metrics_dict)
        metadata = {
            "agent_id": agent_id,
            "checkpoint_id": checkpoint_id,
            "epoch": int(epoch),
            "step": int(step),
            "metrics": metrics_dict,
            "execution_target": execution_target,
            "dataset_hash": dataset_hash,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "is_best": is_best,
            "is_latest": True,
            "artifact_hashes": artifact_hashes,
            "extra_state": _normalize_json(extra_state or {}),
        }
        metadata_path = checkpoint_dir / "metadata.json"
        _atomic_write_json(metadata_path, metadata)
        metadata["artifact_hashes"] = artifact_hashes
        _atomic_write_json(metadata_path, metadata)

        checkpoint = TrainingCheckpoint(
            agent_id=agent_id,
            checkpoint_id=checkpoint_id,
            checkpoint_dir=str(checkpoint_dir),
            step=int(step),
            epoch=int(epoch),
            metrics=metrics_dict,
            is_best=is_best,
            is_latest=True,
            created_at=metadata["created_at"],
            artifact_hashes=artifact_hashes,
        )
        self._update_checkpoint_index(agent_id, checkpoint)
        backup_future = self._replicator.replicate_async(
            agent_id=agent_id,
            checkpoint_id=checkpoint_id,
            checkpoint_dir=checkpoint_dir,
            execution_target=execution_target,
        )
        checkpoint.backup_receipt_path = str(checkpoint_dir / "backup_receipt.json")
        self._track_backup_future(agent_id, checkpoint_id, backup_future)
        self._log_event(
            agent_id,
            "checkpoint_saved",
            {
                "checkpoint_id": checkpoint_id,
                "step": step,
                "epoch": epoch,
                "is_best": is_best,
                "execution_target": execution_target,
            },
        )
        return checkpoint

    def wait_for_backups(self, timeout: Optional[float] = None) -> None:
        self._replicator.wait(timeout=timeout)

    def verify_checkpoint(self, agent_id: str, checkpoint_id: str) -> Tuple[bool, str]:
        checkpoint_dir = self._agent_checkpoint_root(agent_id) / checkpoint_id
        metadata_path = checkpoint_dir / "metadata.json"
        if not metadata_path.exists():
            return False, "metadata_missing"

        metadata = _load_json(metadata_path, default={})
        artifact_hashes = metadata.get("artifact_hashes", {})
        required = ("model.safetensors", "optimizer.pt", "scheduler.pt", "metadata.json")
        for name in required:
            artifact = checkpoint_dir / name
            if not artifact.exists():
                return False, f"missing_artifact:{name}"
            expected = str(artifact_hashes.get(name, "") or "")
            if expected and _sha256_file(artifact) != expected:
                return False, f"hash_mismatch:{name}"

        optional = ("rng_state.pt", "scaler.pt")
        for name in optional:
            expected = str(artifact_hashes.get(name, "") or "")
            if expected:
                artifact = checkpoint_dir / name
                if not artifact.exists():
                    return False, f"missing_artifact:{name}"
                if _sha256_file(artifact) != expected:
                    return False, f"hash_mismatch:{name}"

        return True, "ok"

    def load_checkpoint(
        self,
        agent_id: str,
        *,
        checkpoint_id: Optional[str] = None,
        device: str = "cpu",
    ) -> Optional[Dict[str, Any]]:
        import torch

        candidates = self._checkpoint_candidates(agent_id, checkpoint_id)
        for candidate in candidates:
            valid, _ = self.verify_checkpoint(agent_id, candidate)
            if not valid:
                continue

            checkpoint_dir = self._agent_checkpoint_root(agent_id) / candidate
            metadata = _load_json(checkpoint_dir / "metadata.json", default={})
            return {
                "checkpoint_id": candidate,
                "checkpoint_dir": str(checkpoint_dir),
                "metadata": metadata,
                "model_state": load_safetensors(str(checkpoint_dir / "model.safetensors"), device=device),
                "optimizer_state": torch.load(checkpoint_dir / "optimizer.pt", map_location=device, weights_only=False),
                "scheduler_state": torch.load(checkpoint_dir / "scheduler.pt", map_location=device, weights_only=False),
                "rng_state": (
                    torch.load(checkpoint_dir / "rng_state.pt", map_location="cpu", weights_only=False)
                    if (checkpoint_dir / "rng_state.pt").exists()
                    else None
                ),
                "scaler_state": (
                    torch.load(checkpoint_dir / "scaler.pt", map_location=device, weights_only=False)
                    if (checkpoint_dir / "scaler.pt").exists()
                    else None
                ),
            }
        return None

    def resume_latest(
        self,
        agent_id: str,
        *,
        model: Optional[Any] = None,
        optimizer: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        scaler: Optional[Any] = None,
        device: str = "cpu",
    ) -> CheckpointRestoreResult:
        payload = self.load_checkpoint(agent_id, device=device)
        if payload is None:
            return CheckpointRestoreResult(
                restored=False,
                agent_id=agent_id,
                reason="no_valid_checkpoint",
            )

        metadata = payload["metadata"]
        if model is not None:
            model.load_state_dict(payload["model_state"])
        if optimizer is not None:
            optimizer.load_state_dict(payload["optimizer_state"])
        if scheduler is not None:
            scheduler.load_state_dict(payload["scheduler_state"])
        if scaler is not None and payload.get("scaler_state") is not None:
            scaler.load_state_dict(payload["scaler_state"])

        result = CheckpointRestoreResult(
            restored=True,
            agent_id=agent_id,
            checkpoint_id=str(payload["checkpoint_id"]),
            checkpoint_dir=str(payload["checkpoint_dir"]),
            epoch=int(metadata.get("epoch", 0)),
            step=int(metadata.get("step", 0)),
            metrics=dict(metadata.get("metrics", {})),
            reason="resumed_latest_valid",
        )
        self._log_event(
            agent_id,
            "checkpoint_resumed",
            {
                "checkpoint_id": result.checkpoint_id,
                "epoch": result.epoch,
                "step": result.step,
            },
        )
        return result

    def evaluate_training_safety(
        self,
        agent_id: str,
        *,
        epoch: int,
        train_loss: float,
        val_loss: float,
        accuracy: float,
        gradient_norm: float = 0.0,
    ) -> TrainingSafetyDecision:
        drift_guard = self._drift_guards.setdefault(agent_id, DriftGuard())
        overfit_guard = self._overfit_guards.setdefault(agent_id, OverfitGuard())
        drift_events = drift_guard.check_epoch(
            epoch,
            val_loss,
            accuracy,
            gradient_norm=gradient_norm,
        )
        overfit_metrics = overfit_guard.check_epoch(epoch, train_loss, val_loss)
        reasons: List[str] = []
        if drift_guard.should_abort:
            reasons.extend(event.event_type for event in drift_events)
        if overfit_metrics.overfit_warning:
            reasons.append("overfit_warning")
        rollback_checkpoint_id = self.best_checkpoint_id(agent_id) or self.latest_checkpoint_id(agent_id)
        decision = TrainingSafetyDecision(
            pause_training=bool(reasons),
            rollback_checkpoint_id=rollback_checkpoint_id,
            reasons=reasons,
            drift_events=[asdict(event) for event in drift_events],
            overfit_warning=overfit_metrics.overfit_warning,
        )
        if decision.pause_training:
            self._log_event(
                agent_id,
                "training_paused",
                {
                    "rollback_checkpoint_id": rollback_checkpoint_id,
                    "reasons": reasons,
                },
            )
        return decision

    def latest_checkpoint_id(self, agent_id: str) -> str:
        state = self._agent_runtime_state(agent_id)
        return str(state.get("latest_checkpoint_id", "") or "")

    def best_checkpoint_id(self, agent_id: str) -> str:
        state = self._agent_runtime_state(agent_id)
        return str(state.get("best_checkpoint_id", "") or "")

    def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        state = self._agent_runtime_state(agent_id)
        return {
            "agent_id": agent_id,
            "role": self.get_profile(agent_id).role,
            "latest_checkpoint_id": state.get("latest_checkpoint_id", ""),
            "best_checkpoint_id": state.get("best_checkpoint_id", ""),
            "last_checkpoint_step": state.get("last_checkpoint_step", -1),
            "last_checkpoint_at": state.get("last_checkpoint_at", 0.0),
            "availability": dict(self._availability),
            "memory": self._memory.stats(),
        }

    def list_agent_ids(self) -> List[str]:
        agent_ids = set(self._profiles)
        agent_ids.update(self._runtime_state.get("agents", {}).keys())
        for root in (self.agent_root, self.checkpoint_root, self.training_queue_root):
            if not root.exists():
                continue
            for path in root.glob("agent_*"):
                if path.is_dir():
                    agent_ids.add(path.name[len("agent_"):])
        return sorted(agent_ids)

    def list_pending_training_requests(
        self,
        agent_id: Optional[str] = None,
    ) -> List[IncrementalTrainingRequest]:
        request_paths: List[Path] = []
        if agent_id is not None:
            root = self.training_queue_root / f"agent_{agent_id}"
            if root.exists():
                request_paths.extend(sorted(root.glob("*.json")))
        elif self.training_queue_root.exists():
            for root in sorted(self.training_queue_root.glob("agent_*")):
                if root.is_dir():
                    request_paths.extend(sorted(root.glob("*.json")))

        requests: List[IncrementalTrainingRequest] = []
        for path in request_paths:
            request = self._load_training_request(path)
            if request is not None:
                requests.append(request)
        requests.sort(key=lambda item: (item.created_at, item.request_id))
        return requests

    def recover_startup_state(
        self,
        *,
        device: str = "cpu",
    ) -> StartupRecoveryReport:
        recovered_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        report = StartupRecoveryReport(
            recovered_at=recovered_at,
            availability=dict(self._availability),
        )
        for agent_id in self.list_agent_ids():
            agent_report = StartupRecoveryAgentStatus(agent_id=agent_id)
            for checkpoint_id in self._checkpoint_candidates(agent_id, None):
                valid, reason = self.verify_checkpoint(agent_id, checkpoint_id)
                if not valid:
                    agent_report.invalid_checkpoints.append(
                        f"{checkpoint_id}:{reason}"
                    )

            resume = self.resume_latest(agent_id, device=device)
            agent_report.restored = resume.restored
            agent_report.resumed_checkpoint_id = resume.checkpoint_id
            agent_report.resumed_step = resume.step
            agent_report.resumed_epoch = resume.epoch

            if resume.restored and resume.checkpoint_id:
                if self._checkpoint_backup_needs_repair(agent_id, resume.checkpoint_id):
                    checkpoint_dir = self._agent_checkpoint_root(agent_id) / resume.checkpoint_id
                    metadata = _load_json(checkpoint_dir / "metadata.json", default={})
                    future = self._replicator.replicate_async(
                        agent_id=agent_id,
                        checkpoint_id=resume.checkpoint_id,
                        checkpoint_dir=checkpoint_dir,
                        execution_target=str(
                            metadata.get("execution_target", "vps") or "vps"
                        ),
                    )
                    self._track_backup_future(agent_id, resume.checkpoint_id, future)
                    agent_report.repaired_backups.append(resume.checkpoint_id)
                    self._log_event(
                        agent_id,
                        "checkpoint_backup_repair_scheduled",
                        {"checkpoint_id": resume.checkpoint_id},
                    )

            requests = self.list_pending_training_requests(agent_id)
            agent_report.pending_request_ids = [item.request_id for item in requests]
            for request in requests:
                target = self._select_execution_target(request.target)
                fallback_target = self._fallback_target(target)
                if target != request.target or fallback_target != request.fallback_target:
                    updated_request = IncrementalTrainingRequest(
                        request_id=request.request_id,
                        agent_id=request.agent_id,
                        target=target,
                        fallback_target=fallback_target,
                        reason=request.reason,
                        dataset_path=request.dataset_path,
                        bug_fingerprint=request.bug_fingerprint,
                        created_at=request.created_at,
                    )
                    _atomic_write_json(
                        self._training_request_path(agent_id, request.request_id),
                        asdict(updated_request),
                    )
                    agent_report.rerouted_request_ids.append(request.request_id)
                    self._log_event(
                        agent_id,
                        "training_request_rerouted",
                        {
                            "request_id": request.request_id,
                            "target": target,
                            "fallback_target": fallback_target,
                        },
                    )
                if request.dataset_path and not Path(request.dataset_path).exists():
                    agent_report.issues.append(
                        f"missing_dataset:{request.request_id}"
                    )

            if not resume.restored and requests:
                agent_report.issues.append("pending_training_without_checkpoint")

            report.agents.append(agent_report)

        self._runtime_state["last_recovery_at"] = recovered_at
        self._runtime_state["last_recovery"] = asdict(report)
        self._persist_runtime_state()
        return report

    def _bootstrap_default_profiles(self) -> None:
        for index, specialty in enumerate(_DEFAULT_AGENT_SPECIALTIES, start=1):
            profile = AgentIsolationProfile(
                agent_id=f"agent_{index:02d}",
                role=specialty,
                required_keywords=(specialty.replace("_", " "), specialty.split("_")[0]),
            )
            self.register_agent(profile)

    def _load_profiles(self) -> None:
        if not self.agent_root.exists():
            return
        for profile_path in self.agent_root.glob("agent_*/profile.json"):
            payload = _load_json(profile_path, default={})
            if not payload:
                continue
            profile = AgentIsolationProfile(
                agent_id=str(payload.get("agent_id", "")),
                role=str(payload.get("role", "general")),
                parameter_count=int(payload.get("parameter_count", 130_000_000)),
                required_keywords=tuple(payload.get("required_keywords", []) or []),
                blocked_keywords=tuple(payload.get("blocked_keywords", []) or []),
                allowed_sources=tuple(payload.get("allowed_sources", []) or []),
                allowed_bug_types=tuple(payload.get("allowed_bug_types", []) or []),
                notes=str(payload.get("notes", "")),
            )
            if profile.agent_id:
                self._profiles[profile.agent_id] = profile
                self._drift_guards.setdefault(profile.agent_id, DriftGuard())
                self._overfit_guards.setdefault(profile.agent_id, OverfitGuard())

    def _load_runtime_state(self) -> Dict[str, Any]:
        return _load_json(self.state_path, default={"agents": {}, "availability": {}})

    def _persist_runtime_state(self) -> None:
        payload = dict(self._runtime_state)
        payload["availability"] = dict(self._availability)
        payload["agents"] = self._runtime_state.get("agents", {})
        _atomic_write_json(self.state_path, payload)

    def _profile_path(self, agent_id: str) -> Path:
        root = self._agent_root(agent_id)
        _ensure_dir(root)
        return root / "profile.json"

    def _agent_root(self, agent_id: str) -> Path:
        root = self.agent_root / f"agent_{agent_id}"
        _ensure_dir(root)
        return root

    def _agent_dataset_root(self, agent_id: str) -> Path:
        root = self._agent_root(agent_id) / "datasets"
        _ensure_dir(root)
        return root

    def _agent_experience_root(self, agent_id: str) -> Path:
        root = self._agent_root(agent_id) / "experience"
        _ensure_dir(root)
        return root

    def _agent_checkpoint_root(self, agent_id: str) -> Path:
        root = self.checkpoint_root / f"agent_{agent_id}"
        _ensure_dir(root)
        return root

    def _agent_runtime_state(self, agent_id: str) -> Dict[str, Any]:
        agents = self._runtime_state.setdefault("agents", {})
        return agents.setdefault(
            agent_id,
            {
                "latest_checkpoint_id": "",
                "best_checkpoint_id": "",
                "last_checkpoint_step": -1,
                "last_checkpoint_at": 0.0,
                "best_validation_accuracy": None,
                "best_validation_loss": None,
                "pending_backups": {},
            },
        )

    def _training_request_path(self, agent_id: str, request_id: str) -> Path:
        root = self.training_queue_root / f"agent_{agent_id}"
        _ensure_dir(root)
        return root / f"{request_id}.json"

    def _load_training_request(
        self,
        path: Path,
    ) -> Optional[IncrementalTrainingRequest]:
        payload = _load_json(path, default={})
        request_id = str(payload.get("request_id", path.stem) or path.stem)
        agent_id = str(
            payload.get("agent_id", path.parent.name[len("agent_"):])
            or path.parent.name[len("agent_"):]
        )
        if not request_id or not agent_id:
            return None
        return IncrementalTrainingRequest(
            request_id=request_id,
            agent_id=agent_id,
            target=str(payload.get("target", "cpu") or "cpu"),
            fallback_target=str(payload.get("fallback_target", "cpu") or "cpu"),
            reason=str(payload.get("reason", "") or ""),
            dataset_path=str(payload.get("dataset_path", "") or ""),
            bug_fingerprint=str(payload.get("bug_fingerprint", "") or ""),
            created_at=str(payload.get("created_at", "") or ""),
        )

    def _checkpoint_candidates(
        self,
        agent_id: str,
        checkpoint_id: Optional[str],
    ) -> List[str]:
        if checkpoint_id:
            return [checkpoint_id]

        agent_state = self._agent_runtime_state(agent_id)
        ordered: List[str] = []
        latest = str(agent_state.get("latest_checkpoint_id", "") or "")
        best = str(agent_state.get("best_checkpoint_id", "") or "")
        if latest:
            ordered.append(latest)
        if best and best not in ordered:
            ordered.append(best)

        manifest = _load_json(self._agent_checkpoint_root(agent_id) / "manifest.json", default={})
        checkpoints = list(manifest.get("checkpoints", {}).keys())
        checkpoints.sort(key=_checkpoint_step_value, reverse=True)
        for item in checkpoints:
            if item not in ordered:
                ordered.append(item)
        return ordered

    def _sample_matches_profile(
        self,
        profile: AgentIsolationProfile,
        sample: Mapping[str, Any],
    ) -> Tuple[bool, str]:
        explicit_agent = str(sample.get("owner_agent_id", sample.get("agent_id", "")) or "").strip()
        if explicit_agent and explicit_agent != profile.agent_id:
            return False, f"explicit_agent_mismatch:{explicit_agent}"

        source = str(sample.get("source", sample.get("source_tag", "")) or "").lower()
        if profile.allowed_sources and source not in {
            item.lower() for item in profile.allowed_sources
        }:
            return False, f"source_mismatch:{source or 'unknown'}"

        bug_type = str(sample.get("bug_type", sample.get("category", "")) or "").lower()
        if profile.allowed_bug_types and bug_type and bug_type not in {
            item.lower() for item in profile.allowed_bug_types
        }:
            return False, f"bug_type_mismatch:{bug_type}"

        text = _sample_text(sample)
        blocked = [item.lower() for item in profile.blocked_keywords]
        for keyword in blocked:
            if keyword and keyword in text:
                return False, f"blocked_keyword:{keyword}"

        required = [item.lower() for item in profile.required_keywords]
        if required and not any(keyword and keyword in text for keyword in required):
            return False, "required_keyword_missing"

        return True, "accepted"

    def _select_execution_target(self, preferred_target: str) -> str:
        preferred = str(preferred_target or "vps").lower()
        order = [preferred]
        for candidate in ("vps", "local_gpu", "cpu"):
            if candidate not in order:
                order.append(candidate)
        for candidate in order:
            if self._availability.get(candidate):
                return candidate
        return "cpu"

    @staticmethod
    def _fallback_target(target: str) -> str:
        if target == "vps":
            return "local_gpu"
        if target == "local_gpu":
            return "cpu"
        return "cpu"

    def _checkpoint_backup_needs_repair(
        self,
        agent_id: str,
        checkpoint_id: str,
    ) -> bool:
        checkpoint_dir = self._agent_checkpoint_root(agent_id) / checkpoint_id
        if not checkpoint_dir.exists():
            return False

        receipt = _load_json(checkpoint_dir / "backup_receipt.json", default={})
        if not receipt:
            return True
        completed = int(receipt.get("completed_locations", 0) or 0)
        if completed < 2:
            return True

        secondary_path = str(receipt.get("secondary_path", "") or "")
        if secondary_path and not Path(secondary_path).exists():
            return True

        hybrid_paths = receipt.get("hybrid_paths", {}) or {}
        has_hybrid = any(Path(str(path)).exists() for path in hybrid_paths.values())
        has_remote = bool(receipt.get("remote_paths", []) or [])
        if secondary_path or hybrid_paths or has_remote:
            return not (
                (secondary_path and Path(secondary_path).exists())
                or has_hybrid
                or has_remote
            )

        return True

    def _is_best_checkpoint(self, agent_id: str, metrics: Mapping[str, float]) -> bool:
        agent_state = self._agent_runtime_state(agent_id)
        val_acc = float(metrics.get("validation_accuracy", metrics.get("accuracy", float("-inf"))))
        val_loss = float(metrics.get("validation_loss", metrics.get("loss", float("inf"))))
        best_acc_raw = agent_state.get("best_validation_accuracy")
        best_loss_raw = agent_state.get("best_validation_loss")
        best_acc = float(best_acc_raw) if best_acc_raw is not None else float("-inf")
        best_loss = float(best_loss_raw) if best_loss_raw is not None else float("inf")
        if val_acc > best_acc:
            return True
        return val_acc == best_acc and val_loss < best_loss

    def _update_checkpoint_index(
        self,
        agent_id: str,
        checkpoint: TrainingCheckpoint,
    ) -> None:
        root = self._agent_checkpoint_root(agent_id)
        manifest_path = root / "manifest.json"
        pointer_path = root / "pointers.json"
        manifest = _load_json(manifest_path, default={"checkpoints": {}})
        checkpoints = dict(manifest.get("checkpoints", {}))
        for payload in checkpoints.values():
            payload["is_latest"] = False

        checkpoints[checkpoint.checkpoint_id] = asdict(checkpoint)
        checkpoints[checkpoint.checkpoint_id]["is_latest"] = True
        if checkpoint.is_best:
            for checkpoint_id, payload in checkpoints.items():
                payload["is_best"] = checkpoint_id == checkpoint.checkpoint_id

        manifest["checkpoints"] = checkpoints
        manifest["latest_checkpoint_id"] = checkpoint.checkpoint_id
        agent_state = self._agent_runtime_state(agent_id)
        agent_state["latest_checkpoint_id"] = checkpoint.checkpoint_id
        agent_state["last_checkpoint_step"] = checkpoint.step
        agent_state["last_checkpoint_at"] = time.time()
        if checkpoint.is_best:
            manifest["best_checkpoint_id"] = checkpoint.checkpoint_id
            agent_state["best_checkpoint_id"] = checkpoint.checkpoint_id
            agent_state["best_validation_accuracy"] = float(
                checkpoint.metrics.get("validation_accuracy", checkpoint.metrics.get("accuracy", float("-inf")))
            )
            agent_state["best_validation_loss"] = float(
                checkpoint.metrics.get("validation_loss", checkpoint.metrics.get("loss", float("inf")))
            )
        elif not manifest.get("best_checkpoint_id"):
            manifest["best_checkpoint_id"] = checkpoint.checkpoint_id
            agent_state["best_checkpoint_id"] = checkpoint.checkpoint_id

        _atomic_write_json(manifest_path, manifest)
        _atomic_write_json(
            pointer_path,
            {
                "latest_checkpoint_id": manifest.get("latest_checkpoint_id", ""),
                "best_checkpoint_id": manifest.get("best_checkpoint_id", ""),
                "latest_checkpoint_path": str(root / manifest.get("latest_checkpoint_id", "")),
                "best_checkpoint_path": str(root / manifest.get("best_checkpoint_id", "")),
            },
        )
        self._persist_runtime_state()

    def _track_backup_future(
        self,
        agent_id: str,
        checkpoint_id: str,
        future: Future,
    ) -> None:
        state = self._agent_runtime_state(agent_id)
        pending = dict(state.get("pending_backups", {}))
        pending[checkpoint_id] = "scheduled"
        state["pending_backups"] = pending

        def _resolve(result_future: Future) -> None:
            pending_state = self._agent_runtime_state(agent_id)
            pending_map = dict(pending_state.get("pending_backups", {}))
            try:
                receipt = result_future.result()
                pending_map[checkpoint_id] = f"complete:{receipt.completed_locations}"
            except Exception as exc:  # pragma: no cover
                pending_map[checkpoint_id] = f"failed:{exc}"
            pending_state["pending_backups"] = pending_map
            self._persist_runtime_state()

        future.add_done_callback(_resolve)
        self._persist_runtime_state()

    def _log_event(self, agent_id: str, event: str, payload: Dict[str, Any]) -> None:
        trace_path = self.trace_root / f"agent_{agent_id}.jsonl"
        _append_jsonl(
            trace_path,
            {
                "agent_id": agent_id,
                "event": event,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "payload": payload,
            },
        )
