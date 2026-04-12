from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from backend.reporting.report_engine import ReportEngine
from backend.tasks.industrial_agent import AutonomousWorkflowOrchestrator
from backend.training.incremental_trainer import AccuracySnapshot


def _grab_result(
    *,
    cycle_id: str,
    sources_attempted: int,
    sources_succeeded: int,
    samples_fetched: int,
    samples_accepted: int,
    samples_rejected: int,
    bridge_published: int,
    errors: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        cycle_id=cycle_id,
        sources_attempted=sources_attempted,
        sources_succeeded=sources_succeeded,
        samples_fetched=samples_fetched,
        samples_accepted=samples_accepted,
        samples_rejected=samples_rejected,
        bridge_published=bridge_published,
        errors=list(errors),
    )


def _reportable_samples(batch_id: str) -> list[dict[str, str]]:
    return [
        {
            "sha256_hash": "sha-001",
            "endpoint": "CVE-2026-4100",
            "exploit_vector": (
                "Server-side request forgery in the metadata proxy allows remote "
                "access to cloud credentials and downstream secrets."
            ),
            "impact": "CRITICAL|CVSS:9.8",
            "source_tag": "nvd",
            "ingestion_batch_id": batch_id,
        },
        {
            "sha256_hash": "sha-002",
            "endpoint": "CVE-2026-4101",
            "exploit_vector": (
                "Broken object-level authorization on the administrative API exposes "
                "tenant data and cross-account mutation paths without additional checks."
            ),
            "impact": "HIGH|CVSS:8.1",
            "source_tag": "cisa",
            "ingestion_batch_id": batch_id,
        },
    ]


def _worker_status(*, batch_id: str | None, bridge_count: int) -> dict[str, object]:
    last_batch = None
    if batch_id is not None:
        last_batch = {
            "batch_id": batch_id,
            "ingested": bridge_count,
            "mode": "autograbber",
        }
    return {
        "bridge_count": bridge_count,
        "bridge_verified_count": bridge_count,
        "last_batch": last_batch,
    }


class _StaticController:
    def __init__(
        self,
        *,
        run_id: str,
        status: str,
        promoted: bool,
        snapshots: list[AccuracySnapshot] | None = None,
    ) -> None:
        self._run_id = run_id
        self._status = status
        self._promoted = promoted
        self.trainer = SimpleNamespace(
            get_accuracy_history=lambda: list(snapshots or []),
        )

    def check_and_train(self, *, trigger: str = "manual") -> SimpleNamespace:
        return SimpleNamespace(
            run_id=self._run_id,
            status=self._status,
            promoted=self._promoted,
            trigger=trigger,
        )


class _SequenceGrabber:
    def __init__(self, *results: SimpleNamespace) -> None:
        self._results = list(results)

    def run_cycle(self) -> SimpleNamespace:
        return self._results.pop(0)


def test_workflow_partial_on_grab_success_train_skip(tmp_path):
    batch_id = "CBI-100001"
    orchestrator = AutonomousWorkflowOrchestrator(
        root=tmp_path / "workflow-partial",
        autograbber=SimpleNamespace(
            run_cycle=lambda: _grab_result(
                cycle_id="grab-100001",
                sources_attempted=2,
                sources_succeeded=2,
                samples_fetched=3,
                samples_accepted=2,
                samples_rejected=1,
                bridge_published=2,
            )
        ),
        auto_train_controller=_StaticController(
            run_id="train-skip-100001",
            status="SKIPPED",
            promoted=False,
        ),
        report_engine=ReportEngine(output_dir=tmp_path / "reports"),
        worker_status_loader=lambda: _worker_status(batch_id=batch_id, bridge_count=2),
        bridge_samples_loader=lambda max_samples=0: _reportable_samples(batch_id),
    )

    result = orchestrator.run_cycle(trigger="manual")

    assert result.status == "PARTIAL"
    assert result.ingest_cycle_id == "grab-100001"
    assert result.training_status == "SKIPPED"
    assert result.training_promoted is False
    assert result.bridge_batch_id == batch_id
    assert result.report_generated is True
    assert result.report_findings == 2
    assert result.report_path is not None
    assert Path(result.report_path).exists()


def test_workflow_full_on_grab_and_train(tmp_path):
    orchestrator = AutonomousWorkflowOrchestrator(
        root=tmp_path / "workflow-full",
        autograbber=SimpleNamespace(
            run_cycle=lambda: _grab_result(
                cycle_id="grab-200001",
                sources_attempted=3,
                sources_succeeded=3,
                samples_fetched=5,
                samples_accepted=4,
                samples_rejected=1,
                bridge_published=4,
            )
        ),
        auto_train_controller=_StaticController(
            run_id="train-200001",
            status="COMPLETED",
            promoted=True,
            snapshots=[
                AccuracySnapshot(
                    epoch=7,
                    accuracy=0.9421,
                    precision=0.9142,
                    recall=0.9011,
                    f1=0.9076,
                    auc_roc=0.9614,
                    taken_at="2026-04-10T00:00:00+00:00",
                )
            ],
        ),
        report_engine=ReportEngine(output_dir=tmp_path / "reports"),
        worker_status_loader=lambda: _worker_status(
            batch_id="CBI-200001",
            bridge_count=4,
        ),
        bridge_samples_loader=lambda max_samples=0: [],
    )

    result = orchestrator.run_cycle(trigger="scheduled")

    assert result.status == "FULL_CYCLE"
    assert result.training_run_id == "train-200001"
    assert result.training_status == "COMPLETED"
    assert result.training_promoted is True
    assert result.report_generated is True
    assert result.report_findings == 1
    assert result.report_path is not None
    assert Path(result.report_path).exists()


def test_workflow_failed_on_grab_failure(tmp_path):
    orchestrator = AutonomousWorkflowOrchestrator(
        root=tmp_path / "workflow-failed",
        autograbber=SimpleNamespace(
            run_cycle=lambda: _grab_result(
                cycle_id="grab-300001",
                sources_attempted=1,
                sources_succeeded=0,
                samples_fetched=0,
                samples_accepted=0,
                samples_rejected=0,
                bridge_published=0,
                errors=("source_failed:nvd",),
            )
        ),
        auto_train_controller=_StaticController(
            run_id="train-skip-300001",
            status="SKIPPED",
            promoted=False,
        ),
        report_engine=ReportEngine(output_dir=tmp_path / "reports"),
        worker_status_loader=lambda: _worker_status(batch_id=None, bridge_count=0),
        bridge_samples_loader=lambda max_samples=0: [],
    )

    result = orchestrator.run_cycle(trigger="manual")

    assert result.status == "FAILED"
    assert result.training_status == "SKIPPED"
    assert result.report_generated is False
    assert result.report_reason == "no_published_samples"
    assert "source_failed:nvd" in result.errors


def test_workflow_stores_history(tmp_path):
    batch_id = "CBI-400001"
    orchestrator = AutonomousWorkflowOrchestrator(
        root=tmp_path / "workflow-history",
        autograbber=_SequenceGrabber(
            _grab_result(
                cycle_id="grab-400001",
                sources_attempted=1,
                sources_succeeded=1,
                samples_fetched=1,
                samples_accepted=1,
                samples_rejected=0,
                bridge_published=1,
            ),
            _grab_result(
                cycle_id="grab-400002",
                sources_attempted=1,
                sources_succeeded=1,
                samples_fetched=1,
                samples_accepted=1,
                samples_rejected=0,
                bridge_published=1,
            ),
        ),
        auto_train_controller=_StaticController(
            run_id="train-skip-400001",
            status="SKIPPED",
            promoted=False,
        ),
        report_engine=ReportEngine(output_dir=tmp_path / "reports"),
        worker_status_loader=lambda: _worker_status(batch_id=batch_id, bridge_count=1),
        bridge_samples_loader=lambda max_samples=0: _reportable_samples(batch_id)[:1],
    )

    first = orchestrator.run_cycle(trigger="manual")
    second = orchestrator.run_cycle(trigger="manual")

    history = orchestrator.get_history()
    status_payload = json.loads(
        (tmp_path / "workflow-history" / "status.json").read_text(encoding="utf-8")
    )
    history_payload = json.loads(
        (tmp_path / "workflow-history" / "history.json").read_text(encoding="utf-8")
    )

    assert len(history) == 2
    assert [item["cycle_id"] for item in history] == [first.cycle_id, second.cycle_id]
    assert len(history_payload) == 2
    assert status_payload["history_size"] == 2
    assert status_payload["last_cycle"]["cycle_id"] == second.cycle_id
