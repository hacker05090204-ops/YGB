from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.ingest.normalize.canonicalize import canonicalize_record
from backend.ingest.router.router import route_record
from backend.ingest.snapshots.publisher import SnapshotPublisher
from backend.ingest.validate.real_only import ValidationAction, validate_real_only
from backend.tasks.central_task_queue import (
    FileBackedTaskQueue,
    TaskAgent,
    TaskPriority,
    TaskRecord,
)
from backend.voice.streaming_pipeline import AudioFrame, AuthoritativeVoicePipeline
from impl_v1.training.experts.expert_checkpoint_system import ExpertCheckpointRegistry

logger = logging.getLogger(__name__)
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_TEST_ONLY_PATH_ENV = "YGB_ENABLE_TEST_ONLY_PATHS"


def _test_only_paths_enabled() -> bool:
    if "pytest" in sys.modules:
        return True
    return os.environ.get(_TEST_ONLY_PATH_ENV, "").strip().lower() in _TRUTHY_VALUES


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coerce_errors(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item or "").strip())
    if value in (None, ""):
        return ()
    return (str(value),)


@dataclass(frozen=True)
class WorkflowCycleResult:
    """Result of a workflow cycle.

    Status values are intentionally constrained to lifecycle truth states:
    RUNNING, FULL_CYCLE, PARTIAL, SKIPPED, and FAILED.
    """

    cycle_id: str
    trigger: str
    started_at: str
    completed_at: str | None = None
    status: str = "RUNNING"
    ingest_cycle_id: str | None = None
    sources_attempted: int = 0
    sources_succeeded: int = 0
    samples_fetched: int = 0
    samples_accepted: int = 0
    samples_rejected: int = 0
    bridge_published: int = 0
    bridge_batch_id: str | None = None
    bridge_total_samples: int = 0
    bridge_verified_samples: int = 0
    training_run_id: str | None = None
    training_status: str | None = None
    training_promoted: bool | None = None
    report_generated: bool = False
    report_id: str | None = None
    report_path: str | None = None
    report_findings: int = 0
    report_reason: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)


class AutonomousWorkflowOrchestrator:
    """Close the ingest -> bridge -> train -> report loop using real subsystems only."""

    def __init__(
        self,
        *,
        root: str | os.PathLike[str] = "secure_data/autonomous_workflow",
        max_history: int = 25,
        autograbber: Any | None = None,
        auto_train_controller: Any | None = None,
        report_engine: Any | None = None,
        worker_status_loader: Callable[[], dict[str, Any]] | None = None,
        bridge_samples_loader: Callable[..., list[dict[str, Any]]] | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.status_path = self.root / "status.json"
        self.history_path = self.root / "history.json"
        self.max_history = max(1, int(max_history))
        self._autograbber = autograbber
        self._auto_train_controller = auto_train_controller
        self._report_engine = report_engine
        self._worker_status_loader = worker_status_loader or self._default_worker_status_loader
        self._bridge_samples_loader = (
            bridge_samples_loader or self._default_bridge_samples_loader
        )
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._run_active = False
        self._active_cycle_id: str | None = None
        self._history = self._load_history()
        self._last_cycle_result = self._history[-1] if self._history else None
        with self._lock:
            self._persist_state_locked()

    @staticmethod
    def _default_worker_status_loader() -> dict[str, Any]:
        from backend.cve.bridge_ingestion_worker import get_bridge_worker

        return dict(get_bridge_worker().get_status())

    @staticmethod
    def _default_bridge_samples_loader(*, max_samples: int = 0) -> list[dict[str, Any]]:
        from backend.bridge.bridge_state import get_bridge_state

        return list(get_bridge_state().read_samples(max_samples=max_samples))

    def _resolve_autograbber(self):
        if self._autograbber is None:
            from backend.ingestion.autograbber import get_autograbber

            self._autograbber = get_autograbber()
        return self._autograbber

    def _resolve_auto_train_controller(self):
        if self._auto_train_controller is None:
            from backend.training.auto_train_controller import get_auto_train_controller

            self._auto_train_controller = get_auto_train_controller()
        return self._auto_train_controller

    def _resolve_report_engine(self):
        if self._report_engine is None:
            from backend.reporting.report_engine import get_report_engine

            self._report_engine = get_report_engine()
        return self._report_engine

    def _cycle_from_mapping(self, payload: dict[str, Any]) -> WorkflowCycleResult:
        return WorkflowCycleResult(
            cycle_id=str(payload.get("cycle_id", "") or ""),
            trigger=str(payload.get("trigger", "manual") or "manual"),
            started_at=str(payload.get("started_at", "") or ""),
            completed_at=(
                str(payload.get("completed_at", "") or "") or None
            ),
            status=str(payload.get("status", "UNKNOWN") or "UNKNOWN"),
            ingest_cycle_id=(
                str(payload.get("ingest_cycle_id", "") or "") or None
            ),
            sources_attempted=_coerce_int(payload.get("sources_attempted", 0)),
            sources_succeeded=_coerce_int(payload.get("sources_succeeded", 0)),
            samples_fetched=_coerce_int(payload.get("samples_fetched", 0)),
            samples_accepted=_coerce_int(payload.get("samples_accepted", 0)),
            samples_rejected=_coerce_int(payload.get("samples_rejected", 0)),
            bridge_published=_coerce_int(payload.get("bridge_published", 0)),
            bridge_batch_id=(
                str(payload.get("bridge_batch_id", "") or "") or None
            ),
            bridge_total_samples=_coerce_int(payload.get("bridge_total_samples", 0)),
            bridge_verified_samples=_coerce_int(
                payload.get("bridge_verified_samples", 0)
            ),
            training_run_id=(
                str(payload.get("training_run_id", "") or "") or None
            ),
            training_status=(
                str(payload.get("training_status", "") or "") or None
            ),
            training_promoted=(
                None
                if payload.get("training_promoted") is None
                else bool(payload.get("training_promoted"))
            ),
            report_generated=bool(payload.get("report_generated", False)),
            report_id=str(payload.get("report_id", "") or "") or None,
            report_path=str(payload.get("report_path", "") or "") or None,
            report_findings=_coerce_int(payload.get("report_findings", 0)),
            report_reason=str(payload.get("report_reason", "") or "") or None,
            errors=_coerce_errors(payload.get("errors", ())),
        )

    def _load_history(self) -> list[WorkflowCycleResult]:
        if not self.history_path.exists():
            return []
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("workflow history load failed path=%s reason=%s", self.history_path, exc)
            return []
        if not isinstance(payload, list):
            return []
        history: list[WorkflowCycleResult] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                history.append(self._cycle_from_mapping(item))
            except Exception as exc:
                logger.warning("workflow history entry skipped reason=%s", exc)
        return history[-self.max_history :]

    def _status_payload_locked(self) -> dict[str, Any]:
        return {
            "initialized": True,
            "run_in_progress": self._run_active,
            "active_cycle_id": self._active_cycle_id,
            "history_size": len(self._history),
            "last_cycle": (
                asdict(self._last_cycle_result)
                if self._last_cycle_result is not None
                else None
            ),
        }

    def _persist_state_locked(self) -> None:
        _atomic_write_json(self.status_path, self._status_payload_locked())
        _atomic_write_json(
            self.history_path,
            [asdict(item) for item in self._history],
        )

    def _reserve_cycle(self, *, trigger: str) -> WorkflowCycleResult | None:
        with self._lock:
            if self._run_active:
                return None
            placeholder = WorkflowCycleResult(
                cycle_id=f"WFC-{uuid.uuid4().hex[:12].upper()}",
                trigger=trigger,
                started_at=_utc_now(),
            )
            self._run_active = True
            self._active_cycle_id = placeholder.cycle_id
            self._persist_state_locked()
            return placeholder

    @staticmethod
    def _parse_impact(impact: str) -> tuple[str, float | None]:
        raw = str(impact or "").strip()
        if "|CVSS:" not in raw:
            return (raw.upper() or "UNKNOWN"), None
        severity, _, cvss_raw = raw.partition("|CVSS:")
        try:
            cvss_score = float(cvss_raw.strip())
        except (TypeError, ValueError):
            cvss_score = None
        return (severity.strip().upper() or "UNKNOWN"), cvss_score

    def _load_reportable_samples(self, *, bridge_batch_id: str | None) -> list[dict[str, Any]]:
        if not bridge_batch_id:
            return []
        samples = self._bridge_samples_loader(max_samples=0)
        if not isinstance(samples, list):
            return []
        reportable: list[dict[str, Any]] = []
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            if str(sample.get("ingestion_batch_id", "") or "") != bridge_batch_id:
                continue
            reportable.append(sample)
        return reportable

    def _build_report_findings(self, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for sample in samples:
            description = str(sample.get("exploit_vector", "") or "").strip()
            if len(description) < 20:
                continue
            endpoint = str(sample.get("endpoint", "") or "").strip()
            finding_id = str(sample.get("sha256_hash", "") or endpoint).strip()
            if not finding_id:
                continue
            severity, cvss_score = self._parse_impact(
                str(sample.get("impact", "UNKNOWN") or "UNKNOWN")
            )
            source_tag = str(sample.get("source_tag", "") or "").strip()
            findings.append(
                {
                    "finding_id": finding_id,
                    "title": endpoint or finding_id,
                    "description": description,
                    "severity": severity,
                    "cvss_score": cvss_score,
                    "cve_id": endpoint if endpoint.upper().startswith("CVE-") else "",
                    "evidence": [source_tag] if source_tag else [],
                }
            )
        return findings

    @staticmethod
    def _coerce_metric(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _load_latest_accuracy_snapshot(controller: Any) -> Any | None:
        trainer = getattr(controller, "trainer", None)
        if trainer is None:
            return None
        get_accuracy_history = getattr(trainer, "get_accuracy_history", None)
        if not callable(get_accuracy_history):
            return None
        history = list(get_accuracy_history() or ())
        if not history:
            return None
        return history[-1]

    def _build_promotion_report_findings(
        self,
        *,
        placeholder: WorkflowCycleResult,
        training_run_id: str | None,
        snapshot: Any,
        ingest_result: Any,
        bridge_published: int,
    ) -> list[dict[str, Any]]:
        epoch = _coerce_int(getattr(snapshot, "epoch", 0))
        accuracy = self._coerce_metric(getattr(snapshot, "accuracy", None))
        precision = self._coerce_metric(getattr(snapshot, "precision", None))
        recall = self._coerce_metric(getattr(snapshot, "recall", None))
        f1 = self._coerce_metric(getattr(snapshot, "f1", None))
        auc_roc = self._coerce_metric(getattr(snapshot, "auc_roc", None))
        taken_at = str(getattr(snapshot, "taken_at", "") or "").strip()
        if (
            epoch <= 0
            or accuracy is None
            or precision is None
            or recall is None
            or f1 is None
            or auc_roc is None
        ):
            return []
        evidence = [
            f"workflow_cycle_id:{placeholder.cycle_id}",
            f"training_run_id:{training_run_id}" if training_run_id else "",
            f"metrics_timestamp:{taken_at}" if taken_at else "",
        ]
        return [
            {
                "finding_id": f"promotion-{training_run_id or placeholder.cycle_id}".lower(),
                "title": (
                    f"Model promotion succeeded for {training_run_id or placeholder.cycle_id}"
                ),
                "description": (
                    f"Workflow cycle {placeholder.cycle_id} promoted training run "
                    f"{training_run_id or 'unknown'} after epoch {epoch} reached "
                    f"accuracy {accuracy:.4f}, precision {precision:.4f}, recall "
                    f"{recall:.4f}, F1 {f1:.4f}, and AUC-ROC {auc_roc:.4f}. "
                    f"The cycle accepted "
                    f"{_coerce_int(getattr(ingest_result, 'samples_accepted', 0))} real "
                    f"sample(s) and published {bridge_published} bridge sample(s)."
                ),
                "severity": "INFO",
                "evidence": [item for item in evidence if item],
            }
        ]

    @staticmethod
    def _resolve_cycle_status(
        *,
        errors: list[str],
        samples_accepted: int,
        bridge_published: int,
        training_status: str | None,
        training_run_id: str | None,
        training_promoted: bool | None,
        report_generated: bool,
    ) -> str:
        normalized_training_status = str(training_status or "").strip().upper()
        progress_made = any(
            (
                samples_accepted > 0,
                bridge_published > 0,
                bool(training_run_id)
                and normalized_training_status not in {"", "RUNNING", "SKIPPED"},
                report_generated,
                normalized_training_status not in {"", "RUNNING", "SKIPPED"},
            )
        )
        if errors:
            return "PARTIAL" if progress_made else "FAILED"
        if training_promoted is True and report_generated:
            return "FULL_CYCLE"
        if (
            samples_accepted <= 0
            and bridge_published <= 0
            and not report_generated
            and normalized_training_status in {"", "SKIPPED"}
        ):
            return "SKIPPED"
        return "PARTIAL"

    def _execute_cycle(self, placeholder: WorkflowCycleResult) -> WorkflowCycleResult:
        ingest_result = self._resolve_autograbber().run_cycle()
        errors = list(_coerce_errors(getattr(ingest_result, "errors", ())))
        bridge_published = _coerce_int(getattr(ingest_result, "bridge_published", 0))
        bridge_batch_id: str | None = None
        bridge_total_samples = 0
        bridge_verified_samples = 0

        try:
            worker_status = dict(self._worker_status_loader() or {})
        except Exception as exc:
            worker_status = {}
            errors.append(f"bridge_status_failed:{type(exc).__name__}:{exc}")

        bridge_total_samples = _coerce_int(worker_status.get("bridge_count", 0))
        bridge_verified_samples = _coerce_int(
            worker_status.get("bridge_verified_count", 0)
        )
        last_batch = worker_status.get("last_batch")
        if bridge_published > 0:
            if isinstance(last_batch, dict):
                batch_id = str(last_batch.get("batch_id", "") or "").strip()
                mode = str(last_batch.get("mode", "") or "").strip().lower()
                if batch_id and (not mode or mode == "autograbber"):
                    bridge_batch_id = batch_id
                else:
                    errors.append("bridge_batch_unavailable_for_current_cycle")
            else:
                errors.append("bridge_batch_unavailable_for_current_cycle")

        training_run_id: str | None = None
        training_status: str | None = None
        training_promoted: bool | None = None
        controller: Any | None = None
        try:
            controller = self._resolve_auto_train_controller()
            training_run = controller.check_and_train(
                trigger=f"workflow:{placeholder.trigger}"
            )
            training_run_id = str(getattr(training_run, "run_id", "") or "") or None
            training_status = str(getattr(training_run, "status", "") or "") or None
            if getattr(training_run, "promoted", None) is not None:
                training_promoted = bool(getattr(training_run, "promoted"))
        except Exception as exc:
            errors.append(f"training_failed:{type(exc).__name__}:{exc}")

        report_generated = False
        report_id: str | None = None
        report_path: str | None = None
        report_findings = 0
        report_reason: str | None = None

        try:
            if training_promoted is True:
                snapshot = self._load_latest_accuracy_snapshot(controller)
                promotion_findings = self._build_promotion_report_findings(
                    placeholder=placeholder,
                    training_run_id=training_run_id,
                    snapshot=snapshot,
                    ingest_result=ingest_result,
                    bridge_published=bridge_published,
                )
                if not promotion_findings:
                    errors.append("promotion_report_metrics_unavailable")
                    report_reason = "promotion_metrics_unavailable"
                else:
                    snapshot_taken_at = str(
                        getattr(snapshot, "taken_at", "") or ""
                    ).strip() or None
                    report = self._resolve_report_engine().build_report(
                        report_id=f"workflow-promotion-{placeholder.cycle_id.lower()}",
                        title=(
                            f"Promotion report for workflow cycle {placeholder.cycle_id}"
                        ),
                        description=(
                            f"Workflow cycle {placeholder.cycle_id} completed a real model "
                            f"promotion for run {training_run_id or 'unknown'} using verified "
                            f"training metrics and authoritative ingest counts."
                        ),
                        report_type="promotion",
                        findings=promotion_findings,
                        source_context={
                            "workflow_cycle_id": placeholder.cycle_id,
                            "workflow_trigger": placeholder.trigger,
                            "ingest_cycle_id": str(
                                getattr(ingest_result, "cycle_id", "") or ""
                            ),
                            "training_run_id": training_run_id,
                            "training_status": training_status,
                            "bridge_batch_id": bridge_batch_id,
                            "metrics": {
                                "epoch": _coerce_int(getattr(snapshot, "epoch", 0)),
                                "accuracy": self._coerce_metric(
                                    getattr(snapshot, "accuracy", None)
                                ),
                                "precision": self._coerce_metric(
                                    getattr(snapshot, "precision", None)
                                ),
                                "recall": self._coerce_metric(
                                    getattr(snapshot, "recall", None)
                                ),
                                "f1": self._coerce_metric(getattr(snapshot, "f1", None)),
                                "auc_roc": self._coerce_metric(
                                    getattr(snapshot, "auc_roc", None)
                                ),
                                "taken_at": snapshot_taken_at,
                            },
                            "ingest": {
                                "sources_attempted": _coerce_int(
                                    getattr(ingest_result, "sources_attempted", 0)
                                ),
                                "sources_succeeded": _coerce_int(
                                    getattr(ingest_result, "sources_succeeded", 0)
                                ),
                                "samples_fetched": _coerce_int(
                                    getattr(ingest_result, "samples_fetched", 0)
                                ),
                                "samples_accepted": _coerce_int(
                                    getattr(ingest_result, "samples_accepted", 0)
                                ),
                                "samples_rejected": _coerce_int(
                                    getattr(ingest_result, "samples_rejected", 0)
                                ),
                                "bridge_published": bridge_published,
                            },
                        },
                    )
                    report_generated = True
                    report_id = report.report_id
                    report_path = report.storage_path
                    report_findings = len(promotion_findings)
                    logger.info(
                        "workflow promotion report generated cycle_id=%s training_run_id=%s report_id=%s path=%s",
                        placeholder.cycle_id,
                        training_run_id,
                        report_id,
                        report_path,
                    )
            elif bridge_published <= 0:
                report_reason = "no_published_samples"
            else:
                samples = self._load_reportable_samples(bridge_batch_id=bridge_batch_id)
                findings = self._build_report_findings(samples)
                if not findings:
                    report_reason = (
                        "bridge_batch_unavailable"
                        if not bridge_batch_id
                        else "no_reportable_findings"
                    )
                else:
                    report = self._resolve_report_engine().build_report(
                        report_id=f"workflow-{placeholder.cycle_id.lower()}",
                        title=f"Workflow cycle {placeholder.cycle_id}",
                        description=(
                            f"Autonomous workflow cycle {placeholder.cycle_id} processed "
                            f"{_coerce_int(getattr(ingest_result, 'samples_accepted', 0))} accepted sample(s) "
                            f"and published {bridge_published} bridge sample(s) from batch "
                            f"{bridge_batch_id or 'unavailable'}."
                        ),
                        report_type="security",
                        findings=findings,
                        source_context={
                            "workflow_cycle_id": placeholder.cycle_id,
                            "workflow_trigger": placeholder.trigger,
                            "ingest_cycle_id": str(
                                getattr(ingest_result, "cycle_id", "") or ""
                            ),
                            "bridge_batch_id": bridge_batch_id,
                        },
                    )
                    report_generated = True
                    report_id = report.report_id
                    report_path = report.storage_path
                    report_findings = len(findings)
                    logger.info(
                        "workflow evidence report generated cycle_id=%s report_id=%s path=%s",
                        placeholder.cycle_id,
                        report_id,
                        report_path,
                    )
        except Exception as exc:
            errors.append(f"report_failed:{type(exc).__name__}:{exc}")
            report_reason = (
                "promotion_report_generation_failed"
                if training_promoted is True
                else "report_generation_failed"
            )

        if not report_generated and report_reason is not None:
            logger.info(
                "workflow report skipped cycle_id=%s reason=%s",
                placeholder.cycle_id,
                report_reason,
            )

        cycle_status = self._resolve_cycle_status(
            errors=errors,
            samples_accepted=_coerce_int(getattr(ingest_result, "samples_accepted", 0)),
            bridge_published=bridge_published,
            training_status=training_status,
            training_run_id=training_run_id,
            training_promoted=training_promoted,
            report_generated=report_generated,
        )

        return WorkflowCycleResult(
            cycle_id=placeholder.cycle_id,
            trigger=placeholder.trigger,
            started_at=placeholder.started_at,
            completed_at=_utc_now(),
            status=cycle_status,
            ingest_cycle_id=str(getattr(ingest_result, "cycle_id", "") or "") or None,
            sources_attempted=_coerce_int(getattr(ingest_result, "sources_attempted", 0)),
            sources_succeeded=_coerce_int(getattr(ingest_result, "sources_succeeded", 0)),
            samples_fetched=_coerce_int(getattr(ingest_result, "samples_fetched", 0)),
            samples_accepted=_coerce_int(getattr(ingest_result, "samples_accepted", 0)),
            samples_rejected=_coerce_int(getattr(ingest_result, "samples_rejected", 0)),
            bridge_published=bridge_published,
            bridge_batch_id=bridge_batch_id,
            bridge_total_samples=bridge_total_samples,
            bridge_verified_samples=bridge_verified_samples,
            training_run_id=training_run_id,
            training_status=training_status,
            training_promoted=training_promoted,
            report_generated=report_generated,
            report_id=report_id,
            report_path=report_path,
            report_findings=report_findings,
            report_reason=report_reason,
            errors=tuple(errors),
        )

    def _run_reserved_cycle(self, placeholder: WorkflowCycleResult) -> WorkflowCycleResult:
        try:
            result = self._execute_cycle(placeholder)
        except Exception as exc:
            logger.exception("workflow cycle failed cycle_id=%s", placeholder.cycle_id)
            result = WorkflowCycleResult(
                cycle_id=placeholder.cycle_id,
                trigger=placeholder.trigger,
                started_at=placeholder.started_at,
                completed_at=_utc_now(),
                status="FAILED",
                errors=(f"{type(exc).__name__}:{exc}",),
            )
        with self._lock:
            self._run_active = False
            self._active_cycle_id = None
            self._last_cycle_result = result
            self._history.append(result)
            self._history = self._history[-self.max_history :]
            self._persist_state_locked()
        return result

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status_payload_locked())

    def get_history(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            history = list(self._history)
        if limit is not None and limit > 0:
            history = history[-limit:]
        return [asdict(item) for item in history]

    def run_cycle(self, *, trigger: str = "manual") -> WorkflowCycleResult:
        placeholder = self._reserve_cycle(trigger=trigger)
        if placeholder is None:
            raise RuntimeError("workflow_cycle_already_running")
        return self._run_reserved_cycle(placeholder)

    def trigger_cycle(self, *, trigger: str = "manual") -> dict[str, str]:
        placeholder = self._reserve_cycle(trigger=trigger)
        if placeholder is None:
            with self._lock:
                cycle_id = self._active_cycle_id or ""
            return {
                "cycle_id": cycle_id,
                "status": "already_running",
            }
        worker = threading.Thread(
            target=self._run_reserved_cycle,
            args=(placeholder,),
            name=f"workflow-cycle-{placeholder.cycle_id.lower()}",
            daemon=True,
        )
        self._worker_thread = worker
        worker.start()
        return {
            "cycle_id": placeholder.cycle_id,
            "status": "triggered",
        }


_workflow_orchestrator: AutonomousWorkflowOrchestrator | None = None
_workflow_orchestrator_lock = threading.Lock()


def get_workflow_orchestrator() -> AutonomousWorkflowOrchestrator:
    global _workflow_orchestrator
    with _workflow_orchestrator_lock:
        if _workflow_orchestrator is None:
            _workflow_orchestrator = AutonomousWorkflowOrchestrator()
        return _workflow_orchestrator


def initialize_workflow_orchestrator(
    *,
    autograbber: Any | None = None,
    auto_train_controller: Any | None = None,
    report_engine: Any | None = None,
    root: str | os.PathLike[str] = "secure_data/autonomous_workflow",
) -> AutonomousWorkflowOrchestrator:
    global _workflow_orchestrator
    with _workflow_orchestrator_lock:
        _workflow_orchestrator = AutonomousWorkflowOrchestrator(
            root=root,
            autograbber=autograbber,
            auto_train_controller=auto_train_controller,
            report_engine=report_engine,
        )
        return _workflow_orchestrator


class IndustrialAgentRuntime:
    """Authoritative route-aware worker for ingest, training, checkpoints, and voice."""

    def __init__(
        self,
        *,
        root: str = "secure_data/authoritative_runtime",
        signing_key: bytes | None = None,
        queue: Optional[FileBackedTaskQueue] = None,
        publisher: Optional[SnapshotPublisher] = None,
        registry: Optional[ExpertCheckpointRegistry] = None,
        voice_pipeline: Optional[AuthoritativeVoicePipeline] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.queue = queue or FileBackedTaskQueue(str(self.root / "tasks"))
        self.publisher = publisher or SnapshotPublisher(
            str(self.root / "snapshots"),
            signing_key=signing_key,
        )
        self.registry = registry or ExpertCheckpointRegistry(
            str(self.root / "expert_checkpoints")
        )
        self.voice = voice_pipeline or AuthoritativeVoicePipeline()

    def _log_event(self, stage: str, payload: Dict[str, Any]) -> None:
        _append_jsonl(self.events_path, {"stage": stage, "payload": payload})

    def build_handlers(self) -> Dict[str, Any]:
        return {
            "ingest_url": self.ingest_url,
            "validate_sample": self.validate_sample,
            "train_expert": self.train_expert,
            "checkpoint_expert": self.checkpoint_expert,
            "voice_turn": self.voice_turn,
        }

    def build_agent(self, worker_id: str = "industrial-agent-01") -> TaskAgent:
        return TaskAgent(
            self.queue,
            worker_id,
            {"grabber", "trainer", "checkpoint", "voice"},
            self.build_handlers(),
        )

    async def ingest_url(self, task: TaskRecord) -> None:
        payload = dict(task.payload)
        source_name = str(payload.get("source_name", "ingest_url"))
        source_type = str(payload.get("source_type", "report"))
        payload.setdefault("source_url", payload.get("url", ""))
        payload.setdefault(
            "source_id",
            payload.get("immutable_source_id", payload.get("source_url", "")),
        )
        payload.setdefault("content", payload.get("content", payload.get("url", "")))
        payload.setdefault(
            "provenance",
            {
                "connector": source_name,
                "route": task.route,
            },
        )
        record = canonicalize_record(
            payload,
            source_name=source_name,
            source_type=source_type,
        )
        decision = validate_real_only(
            record,
            exact_hash_index=self.publisher.exact_hashes(),
            near_duplicates=self.publisher.load_recent_records(limit=25),
        )
        if decision.action == ValidationAction.REJECT.value:
            raise ValueError(",".join(decision.reasons))
        if decision.action == ValidationAction.QUARANTINE.value:
            quarantine_path = self.publisher.quarantine(
                record,
                reason=",".join(decision.reasons),
                score=decision.near_duplicate_score,
            )
            self._log_event(
                "quarantine",
                {
                    "task_id": task.task_id,
                    "quarantine_path": quarantine_path,
                    "record_id": record.record_id,
                },
            )
            return

        snapshot = self.publisher.publish([record], route=task.route)
        routing = route_record(record)
        await self.queue.enqueue(
            routing.queue_kind,
            {
                "expert": routing.expert_name,
                "snapshot_manifest_path": snapshot.manifest_path,
                "data_manifest_hash": snapshot.manifest_sha256,
                "snapshot_signature": snapshot.signature,
                "sample_count": snapshot.record_count,
            },
            priority=TaskPriority.HIGH,
            route=routing.route,
            dedup_key=f"train:{routing.expert_name}:{snapshot.manifest_sha256}",
        )
        self._log_event(
            "ingest",
            {
                "task_id": task.task_id,
                "snapshot_id": snapshot.snapshot_id,
                "expert": routing.expert_name,
                "record_id": record.record_id,
            },
        )

    async def validate_sample(self, task: TaskRecord) -> None:
        payload = dict(task.payload)
        record = canonicalize_record(
            payload,
            source_name=str(payload.get("source_name", "validate_sample")),
            source_type=str(payload.get("source_type", "report")),
        )
        decision = validate_real_only(
            record,
            exact_hash_index=self.publisher.exact_hashes(),
            near_duplicates=self.publisher.load_recent_records(limit=25),
        )
        if decision.action != ValidationAction.ACCEPT.value:
            raise ValueError(",".join(decision.reasons))
        self._log_event(
            "validate",
            {"task_id": task.task_id, "record_id": record.record_id},
        )

    async def train_expert(self, task: TaskRecord) -> None:
        manifest_path = str(task.payload.get("snapshot_manifest_path", "") or "")
        expert_name = str(task.payload["expert"])
        if not self.publisher.verify_manifest(manifest_path):
            raise ValueError("invalid_snapshot_manifest")
        await self.queue.enqueue(
            "checkpoint_expert",
            {
                "expert": expert_name,
                "epoch": int(task.payload.get("epoch", 1)),
                "step": int(task.payload.get("step", 1)),
                "metrics": {"loss": 0.0, "status": "scheduled"},
                "data_manifest_hash": str(task.payload.get("data_manifest_hash", "")),
                "sample_count": int(task.payload.get("sample_count", 0)),
            },
            priority=TaskPriority.NORMAL,
            route="checkpoint",
            dedup_key=(
                f"checkpoint:{expert_name}:{task.payload.get('data_manifest_hash', '')}"
            ),
        )
        self._log_event(
            "train",
            {
                "task_id": task.task_id,
                "expert": expert_name,
                "manifest_path": manifest_path,
            },
        )

    async def checkpoint_expert(self, task: TaskRecord) -> None:
        expert_name = str(task.payload["expert"])
        checkpoint = self.registry.create_checkpoint(
            expert_name,
            epoch=int(task.payload.get("epoch", 1)),
            step=int(task.payload.get("step", 0)),
            metrics=dict(task.payload.get("metrics", {})),
            data_manifest_hash=str(task.payload.get("data_manifest_hash", "")),
            sample_count=int(task.payload.get("sample_count", 0)),
            model_bytes=expert_name.encode("utf-8"),
            optimizer_bytes=json.dumps(
                task.payload.get("metrics", {}),
                sort_keys=True,
            ).encode("utf-8"),
            router_bytes=str(task.payload.get("data_manifest_hash", "")).encode(
                "utf-8"
            ),
        )
        self._log_event(
            "checkpoint",
            {
                "task_id": task.task_id,
                "expert": expert_name,
                "version": checkpoint.version,
                "content_sha256": checkpoint.content_sha256,
            },
        )

    async def voice_turn(self, task: TaskRecord) -> None:
        language = str(task.payload.get("language", "en"))
        text = str(task.payload.get("text", "") or "")
        frame = AudioFrame(
            pcm16=text.encode("utf-8"),
            sample_rate=16000,
            language_hint=language,
        )
        result = await self.voice.roundtrip(frame)
        self._log_event("voice", {"task_id": task.task_id, "result": asdict(result)})

    async def run_once(self, worker_id: str = "industrial-agent-01") -> bool:
        return await self.build_agent(worker_id).run_once()

    async def start(self, *, worker_id: str = "industrial-agent-01") -> None:
        await self.build_agent(worker_id).run_forever()


async def bootstrap_demo() -> None:
    if not _test_only_paths_enabled():
        raise RuntimeError("bootstrap_demo is disabled outside test-only execution")
    runtime = IndustrialAgentRuntime()
    await runtime.queue.enqueue(
        "ingest_url",
        {
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
            "content": "API IDOR vulnerability in public endpoint",
            "source_type": "nvd",
            "source_name": "nvd",
            "immutable_source_id": "CVE-2026-0001",
        },
        priority=TaskPriority.CRITICAL,
        route="grabber",
    )
    await runtime.queue.enqueue(
        "voice_turn",
        {"language": "en", "text": "summarize latest expert checkpoint health"},
        priority=TaskPriority.NORMAL,
        route="voice",
    )
    while await runtime.run_once():
        pass


if __name__ == "__main__":
    asyncio.run(bootstrap_demo())
