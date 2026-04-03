"""Incremental training loop for new ingestion samples."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from torch.optim import AdamW
from torch.optim.lr_scheduler import OneCycleLR
from torch.utils.data import DataLoader, TensorDataset

from backend.ingestion._integrity import log_module_sha256
from backend.bridge.bridge_state import get_bridge_state
from backend.ingestion.models import IngestedSample
from backend.observability.metrics import metrics_registry
from backend.training.feature_extractor import extract
from backend.training.model_thresholds import (
    calibrate_positive_threshold,
    compute_binary_metrics,
    load_threshold_artifact,
    save_threshold_artifact,
)
from backend.training.state_manager import TrainingMetrics, get_training_state_manager
from impl_v1.phase49.governors.g37_pytorch_backend import (
    BugClassifier,
    ModelConfig,
    create_model_config,
)
from impl_v1.phase49.governors.g38_self_trained_model import can_ai_execute
from training.safetensors_io import load_safetensors, save_safetensors

logger = logging.getLogger("ygb.training.incremental_trainer")

DEFAULT_MODEL_PATH = Path("checkpoints/g38_model_checkpoint.safetensors")
DEFAULT_STATE_PATH = Path("checkpoints/training_state.json")
DEFAULT_BASELINE_PATH = Path("checkpoints/baseline_accuracy.json")
DEFAULT_RAW_DATA_ROOT = Path("data/raw")
_IMPACT_RE = re.compile(r"CVSS:(?P<score>[0-9.]+)\|(?P<severity>[^|]+)")
_CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


@dataclass(frozen=True)
class EpochResult:
    accuracy: float
    precision: float
    recall: float
    f1: float
    eval_loss: float
    samples_processed: int
    epoch_number: int
    rollback: bool
    early_stopped: bool
    prediction_hash: str = ""


class IncrementalTrainer:
    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        state_path: str | Path = DEFAULT_STATE_PATH,
        baseline_path: str | Path = DEFAULT_BASELINE_PATH,
        raw_data_root: str | Path = DEFAULT_RAW_DATA_ROOT,
        num_workers: int = 4,
    ) -> None:
        self.model_path = Path(model_path)
        self.state_path = Path(state_path)
        self.baseline_path = Path(baseline_path)
        self.raw_data_root = Path(raw_data_root)
        self.num_workers = num_workers
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_config = create_model_config(
            input_dim=512,
            output_dim=2,
            hidden_dims=(1024, 512, 256, 128),
            dropout=0.3,
            learning_rate=3e-4,
            batch_size=256,
            epochs=1,
            seed=42,
        )
        self.training_state = self._load_training_state()
        self.baseline_state = self._load_baseline_state()
        self.baseline_accuracy = float(self.baseline_state["baseline_accuracy"])
        self.positive_threshold = float(self.baseline_state["positive_threshold"])
        self.state_manager = get_training_state_manager()
        self.model = self._load_or_initialize_model()

    def _load_training_state(self) -> dict[str, object]:
        if not self.state_path.exists():
            self._atomic_write_json(
                self.state_path,
                {
                    "last_training_time": datetime.fromtimestamp(
                        0, timezone.utc
                    ).isoformat(),
                    "epoch_number": 0,
                    "best_eval_loss": None,
                    "no_improve_count": 0,
                },
            )
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _load_baseline_state(self) -> dict[str, object]:
        payload = load_threshold_artifact(self.baseline_path)
        if not self.baseline_path.exists():
            self._atomic_write_json(self.baseline_path, payload)
        return payload

    def _atomic_write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(temp_path, path)

    @staticmethod
    def _deterministic_indices(total: int, limit: int) -> list[int]:
        if total <= 0 or limit <= 0:
            return []
        if limit >= total:
            return list(range(total))
        return [int((index * total) / limit) for index in range(limit)]

    @staticmethod
    def _hash_predictions(
        predictions: list[int], probabilities: list[list[float]]
    ) -> str:
        payload = {
            "predictions": [int(prediction) for prediction in predictions],
            "probabilities": [
                [round(float(value), 8) for value in row] for row in probabilities
            ],
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    def _load_or_initialize_model(self) -> torch.nn.Module:
        if BugClassifier is None:
            raise RuntimeError("BugClassifier runtime unavailable")
        model = BugClassifier(self.model_config).to(self.device)
        if not self.model_path.exists():
            migrated = self._restore_legacy_checkpoint()
            if not migrated:
                self._save_model_state(model.state_dict(), epoch_number=0)
                return model

        state_dict = load_safetensors(str(self.model_path), device=self.device.type)
        load_result = model.load_state_dict(state_dict, strict=False)
        if load_result.missing_keys or load_result.unexpected_keys:
            logger.info(
                "incremental_trainer_checkpoint_load",
                extra={
                    "event": "incremental_trainer_checkpoint_load",
                    "missing_keys": list(load_result.missing_keys),
                    "unexpected_keys": list(load_result.unexpected_keys),
                },
            )
        return model

    def _restore_legacy_checkpoint(self) -> bool:
        checkpoints_root = self.model_path.parent
        legacy_candidates = sorted(
            checkpoints_root.glob("*.pt"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not legacy_candidates:
            return False

        from scripts.migrate_checkpoint_to_v2 import migrate_checkpoint

        migrated = migrate_checkpoint(str(legacy_candidates[0]), str(self.model_path))
        logger.info(
            "legacy_checkpoint_restored",
            extra={
                "event": "legacy_checkpoint_restored",
                "source_path": str(legacy_candidates[0]),
                "output_path": str(self.model_path),
                "mapped_keys": len(migrated["mapped_keys"]),
                "unmapped_keys": len(migrated["unmapped_keys"]),
            },
        )
        return True

    def _save_model_state(
        self, state_dict: dict[str, torch.Tensor], epoch_number: int
    ) -> None:
        metadata = {"epoch_number": str(epoch_number)}
        save_safetensors(state_dict, str(self.model_path), metadata=metadata)

    def _persist_checkpoint_metrics(
        self,
        *,
        accuracy: float,
        precision: float,
        recall: float,
        f1: float,
        positive_threshold: float,
    ) -> None:
        payload = save_threshold_artifact(
            self.baseline_path,
            baseline_accuracy=max(self.baseline_accuracy, accuracy),
            positive_threshold=positive_threshold,
            checkpoint_accuracy=accuracy,
            checkpoint_precision=precision,
            checkpoint_recall=recall,
            checkpoint_f1=f1,
        )
        self.baseline_state = payload
        self.baseline_accuracy = float(payload["baseline_accuracy"])
        self.positive_threshold = float(payload["positive_threshold"])

    def _parse_sample(self, payload: dict[str, object]) -> IngestedSample:
        ingested_at = datetime.fromisoformat(
            str(payload["ingested_at"]).replace("Z", "+00:00")
        )
        return IngestedSample(
            source=str(payload["source"]),
            raw_text=str(payload["raw_text"]),
            url=str(payload["url"]),
            cve_id=str(payload.get("cve_id", "")),
            severity=str(payload.get("severity", "UNKNOWN")),
            tags=tuple(payload.get("tags", [])),
            ingested_at=ingested_at,
            sha256_hash=str(payload["sha256_hash"]),
            token_count=int(payload["token_count"]),
            lang=str(payload.get("lang", "en")),
        )

    def load_new_samples(self) -> list[IngestedSample]:
        last_training_time = datetime.fromisoformat(
            str(self.training_state["last_training_time"]).replace("Z", "+00:00")
        )
        samples: list[IngestedSample] = []
        for sample_path in sorted(self.raw_data_root.rglob("*.json")):
            if sample_path.name == "dedup_index.json":
                continue
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
            sample = self._parse_sample(payload)
            if sample.ingested_at > last_training_time:
                samples.append(sample)
        if samples:
            logger.info(
                "incremental_samples_loaded",
                extra={
                    "event": "incremental_samples_loaded",
                    "count": len(samples),
                    "source": "data_raw",
                },
            )
            return samples

        bridge_limit = max(
            1000, int(os.environ.get("YGB_BRIDGE_TRAIN_MAX_SAMPLES", "5000"))
        )
        bridge_samples = self._load_bridge_samples(max_samples=bridge_limit)
        logger.info(
            "incremental_samples_loaded",
            extra={
                "event": "incremental_samples_loaded",
                "count": len(bridge_samples),
                "source": "bridge_state",
            },
        )
        return bridge_samples

    def load_evaluation_samples(
        self, max_samples: int
    ) -> tuple[list[IngestedSample], str]:
        samples: list[IngestedSample] = []
        for sample_path in sorted(self.raw_data_root.rglob("*.json")):
            if sample_path.name == "dedup_index.json":
                continue
            try:
                payload = json.loads(sample_path.read_text(encoding="utf-8"))
                samples.append(self._parse_sample(payload))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning(
                    "evaluation_sample_skipped", extra={"path": str(sample_path)}
                )

        if samples:
            if len(samples) > max_samples:
                sample_indices = self._deterministic_indices(len(samples), max_samples)
                samples = [samples[index] for index in sample_indices]
            return samples, "data_raw"

        return self._load_bridge_samples(max_samples=max_samples), "bridge_state"

    @staticmethod
    def _label_for_sample(sample: IngestedSample) -> int:
        return 1 if sample.severity in {"CRITICAL", "HIGH", "MEDIUM"} else 0

    @staticmethod
    def _severity_from_bridge_record(payload: dict[str, object]) -> str:
        impact = str(payload.get("impact", ""))
        match = _IMPACT_RE.search(impact)
        if not match:
            return "UNKNOWN"
        severity = match.group("severity").strip().upper()
        if severity and severity != "UNKNOWN":
            return severity
        score = float(match.group("score"))
        if score >= 9.0:
            return "CRITICAL"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MEDIUM"
        if score > 0.0:
            return "LOW"
        return "UNKNOWN"

    def _load_bridge_samples(self, max_samples: int) -> list[IngestedSample]:
        bridge_state = get_bridge_state()
        rows = bridge_state.read_samples(max_samples=max_samples)
        samples: list[IngestedSample] = []
        for row in rows:
            text = " ".join(
                str(row.get(field, ""))
                for field in ("endpoint", "parameters", "exploit_vector")
                if str(row.get(field, "")).strip()
            ).strip()
            if not text:
                continue
            source_tag = str(row.get("source_tag", "") or "").strip()
            if not source_tag:
                raise RuntimeError("REAL_DATA_REQUIRED: bridge source_tag missing")
            row_timestamp = str(row.get("ingested_at", "") or "").strip()
            if not row_timestamp:
                raise RuntimeError("REAL_DATA_REQUIRED: bridge row ingested_at missing")
            row_sha256_hash = str(row.get("sha256_hash", "") or "").strip()
            if len(row_sha256_hash) != 64:
                raise RuntimeError("REAL_DATA_REQUIRED: bridge row sha256_hash missing")
            endpoint = str(row.get("endpoint", "") or "").strip()
            if not _CVE_ID_RE.fullmatch(endpoint):
                raise RuntimeError(
                    f"REAL_DATA_REQUIRED: bridge endpoint is not a canonical CVE id ({endpoint or '<missing>'})"
                )
            severity = self._severity_from_bridge_record(row)
            ingested_at = datetime.fromisoformat(row_timestamp.replace("Z", "+00:00"))
            samples.append(
                IngestedSample(
                    source=source_tag,
                    raw_text=text,
                    url=f"https://nvd.nist.gov/vuln/detail/{endpoint.upper()}",
                    cve_id=endpoint.upper(),
                    severity=severity,
                    tags=tuple(),
                    ingested_at=ingested_at,
                    sha256_hash=row_sha256_hash,
                    token_count=len(text.split()),
                    lang="en",
                )
            )
        return samples

    def build_dataset(
        self, samples: list[IngestedSample]
    ) -> tuple[DataLoader, DataLoader]:
        if self.num_workers > 0 and can_ai_execute()[0]:
            raise RuntimeError("GUARD")
        if len(samples) < 2:
            raise RuntimeError(
                "REAL_DATA_REQUIRED: At least two real samples are required"
            )

        feature_rows = torch.stack([extract(sample) for sample in samples])
        labels = torch.tensor(
            [self._label_for_sample(sample) for sample in samples], dtype=torch.long
        )
        indices = list(range(len(samples)))
        eval_count = min(len(indices) - 1, max(2, int(len(indices) * 0.1)))
        eval_indices = self._deterministic_indices(len(indices), eval_count)
        eval_index_set = set(eval_indices)
        train_indices = [index for index in indices if index not in eval_index_set]
        if not train_indices or not eval_indices:
            raise RuntimeError(
                "REAL_DATA_REQUIRED: Deterministic train/validation split failed"
            )

        train_dataset = TensorDataset(
            feature_rows[train_indices], labels[train_indices]
        )
        eval_dataset = TensorDataset(feature_rows[eval_indices], labels[eval_indices])
        train_generator = torch.Generator().manual_seed(self.model_config.seed)
        train_loader = DataLoader(
            train_dataset,
            batch_size=256,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=self.device.type == "cuda",
            persistent_workers=self.num_workers > 0,
            generator=train_generator,
        )
        eval_loader = DataLoader(
            eval_dataset,
            batch_size=512,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.device.type == "cuda",
            persistent_workers=self.num_workers > 0,
        )
        return train_loader, eval_loader

    def _restore_previous_state(self, previous_state: dict[str, torch.Tensor]) -> None:
        self.model.load_state_dict(previous_state, strict=False)
        self._save_model_state(
            previous_state, epoch_number=int(self.training_state.get("epoch_number", 0))
        )

    def _backward_pass(self, scaled_loss: torch.Tensor, scaler) -> None:
        if scaler is not None:
            scaler.scale(scaled_loss).backward()
            return
        scaled_loss.backward()

    def _step_optimizer(self, optimizer: torch.optim.Optimizer, scaler) -> None:
        if scaler is not None:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
        else:
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            optimizer.step()
        optimizer.zero_grad(set_to_none=True)

    def benchmark_current_model(self, max_samples: int = 1500) -> dict[str, object]:
        samples, source = self.load_evaluation_samples(max_samples=max_samples)
        if not samples:
            raise RuntimeError("No real samples available for benchmark")

        feature_rows = torch.stack([extract(sample) for sample in samples]).to(
            self.device
        )
        labels = [self._label_for_sample(sample) for sample in samples]

        self.model.eval()
        positive_probabilities: list[float] = []
        with torch.no_grad():
            for start in range(0, len(samples), 512):
                logits = self.model(feature_rows[start : start + 512])
                probs = torch.softmax(logits, dim=1)[:, 1].detach().cpu().tolist()
                positive_probabilities.extend(
                    float(probability) for probability in probs
                )

        live_metrics = compute_binary_metrics(
            labels, positive_probabilities, self.positive_threshold
        )
        calibrated_metrics = calibrate_positive_threshold(
            labels,
            positive_probabilities,
            fallback_threshold=self.positive_threshold,
        )
        return {
            "samples": len(samples),
            "source": source,
            "threshold": float(live_metrics["threshold"]),
            "accuracy": float(live_metrics["accuracy"]),
            "precision": float(live_metrics["precision"]),
            "recall": float(live_metrics["recall"]),
            "f1": float(live_metrics["f1"]),
            "recommended_threshold": float(calibrated_metrics["threshold"]),
            "recommended_strategy": str(calibrated_metrics["strategy"]),
            "recommended_f1": float(calibrated_metrics["f1"]),
        }

    def run_incremental_epoch(self) -> EpochResult:
        samples = self.load_new_samples()
        epoch_number = int(self.training_state.get("epoch_number", 0)) + 1
        if len(samples) < 10:
            logger.info("insufficient samples")
            return EpochResult(
                0.0, 0.0, 0.0, 0.0, 0.0, len(samples), epoch_number, False, False
            )

        train_loader, eval_loader = self.build_dataset(samples)
        optimizer = AdamW(self.model.parameters(), lr=3e-4, weight_decay=0.01)
        scheduler = OneCycleLR(
            optimizer,
            max_lr=3e-4,
            steps_per_epoch=max(len(train_loader), 1),
            epochs=1,
            pct_start=0.3,
        )
        scaler = torch.amp.GradScaler("cuda") if self.device.type == "cuda" else None
        criterion = torch.nn.CrossEntropyLoss()
        previous_state = {
            name: tensor.detach().cpu().clone()
            for name, tensor in self.model.state_dict().items()
        }

        start_time = time.perf_counter()
        self.model.train()
        optimizer.zero_grad(set_to_none=True)
        accum_steps = 4
        step_count = 0
        for step_count, (features, labels) in enumerate(train_loader, start=1):
            features = features.to(self.device)
            labels = labels.to(self.device)
            autocast_context = (
                torch.amp.autocast("cuda")
                if self.device.type == "cuda"
                else nullcontext()
            )
            with autocast_context:
                outputs = self.model(features)
                loss = criterion(outputs, labels)
                scaled_loss = loss / accum_steps
            self._backward_pass(scaled_loss, scaler)

            if step_count % accum_steps == 0:
                self._step_optimizer(optimizer, scaler)
                scheduler.step()

            if step_count % 50 == 0:
                logger.info(
                    "incremental_training_step",
                    extra={
                        "event": "incremental_training_step",
                        "step": step_count,
                        "loss": float(loss.item()),
                    },
                )

        if step_count and step_count % accum_steps != 0:
            self._step_optimizer(optimizer, scaler)
            scheduler.step()

        self.model.eval()
        eval_losses: list[float] = []
        predictions: list[int] = []
        labels_out: list[int] = []
        probability_rows: list[list[float]] = []
        with torch.no_grad():
            for features, labels in eval_loader:
                features = features.to(self.device)
                labels = labels.to(self.device)
                logits = self.model(features)
                probs = torch.softmax(logits, dim=1)
                eval_losses.append(float(criterion(logits, labels).item()))
                labels_out.extend(labels.cpu().tolist())
                probability_rows.extend(probs.cpu().tolist())

        positive_probabilities = [float(row[1]) for row in probability_rows]
        threshold_metrics = calibrate_positive_threshold(
            labels_out,
            positive_probabilities,
            fallback_threshold=self.positive_threshold,
        )
        positive_threshold = float(threshold_metrics["threshold"])
        predictions = list(threshold_metrics["predictions"])
        prediction_hash = self._hash_predictions(predictions, probability_rows)
        accuracy = float(threshold_metrics["accuracy"])
        precision = float(threshold_metrics["precision"])
        recall = float(threshold_metrics["recall"])
        f1 = float(threshold_metrics["f1"])
        eval_loss = float(sum(eval_losses) / max(len(eval_losses), 1))
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "incremental_threshold_calibrated",
            extra={
                "event": "incremental_threshold_calibrated",
                "threshold": positive_threshold,
                "strategy": str(threshold_metrics["strategy"]),
                "eval_samples": len(labels_out),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "prediction_hash": prediction_hash,
            },
        )

        if accuracy < self.baseline_accuracy - 0.05:
            logger.critical("accuracy dropped > 5%, rolling back")
            metrics_registry.increment("training_rollback", 1.0)
            self._restore_previous_state(previous_state)
            return EpochResult(
                accuracy,
                precision,
                recall,
                f1,
                eval_loss,
                len(samples),
                epoch_number,
                True,
                False,
            )

        early_stopped = False
        best_eval_loss = self.training_state.get("best_eval_loss")
        no_improve_count = int(self.training_state.get("no_improve_count", 0))
        if best_eval_loss is None or eval_loss < float(best_eval_loss):
            best_eval_loss = eval_loss
            no_improve_count = 0
            self._save_model_state(self.model.state_dict(), epoch_number=epoch_number)
            self._persist_checkpoint_metrics(
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1=f1,
                positive_threshold=positive_threshold,
            )
        else:
            no_improve_count += 1
            if no_improve_count >= 3:
                early_stopped = True
                logger.info("early stopping triggered")
                reloaded_state = load_safetensors(
                    str(self.model_path), device=self.device.type
                )
                self.model.load_state_dict(reloaded_state, strict=False)

        gpu_metrics = self.state_manager.get_gpu_metrics(force_emit=True)
        self.state_manager.emit_training_metrics(
            TrainingMetrics(
                status="training",
                elapsed_seconds=duration_ms / 1000.0,
                last_accuracy=accuracy,
                gpu_usage_percent=gpu_metrics.get("gpu_usage_percent"),
                gpu_memory_used_mb=gpu_metrics.get("gpu_memory_used_mb"),
            ),
            calibration_labels=labels_out,
            calibration_probabilities=[row[1] for row in probability_rows],
            distribution=probability_rows,
            epoch_number=epoch_number,
        )
        metrics_registry.set_gauge("model_precision", precision)
        metrics_registry.set_gauge("model_recall", recall)
        metrics_registry.set_gauge("model_f1", f1)
        metrics_registry.set_gauge("training_samples_processed", float(len(samples)))
        metrics_registry.set_gauge("training_epoch_number", float(epoch_number))

        self.training_state = {
            "last_training_time": max(
                sample.ingested_at for sample in samples
            ).isoformat(),
            "epoch_number": epoch_number,
            "best_eval_loss": best_eval_loss,
            "no_improve_count": no_improve_count,
            "prediction_hash": prediction_hash,
        }
        self._atomic_write_json(self.state_path, self.training_state)

        return EpochResult(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1=f1,
            eval_loss=eval_loss,
            samples_processed=len(samples),
            epoch_number=epoch_number,
            rollback=False,
            early_stopped=early_stopped,
            prediction_hash=prediction_hash,
        )


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
