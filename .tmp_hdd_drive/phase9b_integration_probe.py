from __future__ import annotations

import json
import os
import shutil
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, TensorDataset

from backend.ingestion.autograbber import AutoGrabber, AutoGrabberConfig
from backend.ingestion.models import normalize_severity
from backend.training.adaptive_learner import AdaptiveLearner
from backend.training.incremental_trainer import IncrementalTrainer


def _severity_counts(samples: list[object]) -> dict[str, int]:
    counts = Counter()
    for sample in samples:
        counts[normalize_severity(sample.severity)] += 1
    return dict(sorted(counts.items()))


def _build_train_loader(
    trainer: IncrementalTrainer,
    samples: list[object],
    *,
    batch_size: int = 8,
) -> DataLoader:
    feature_rows = []
    label_rows = []
    for sample in samples:
        feature_rows.append(
            trainer._load_or_compute_feature(sample).detach().cpu().to(dtype=torch.float32)
        )
        label_rows.append(trainer._label_for_sample(sample))
    features = torch.stack(feature_rows)
    labels = torch.tensor(label_rows, dtype=torch.long)
    dataset = TensorDataset(features, labels)
    return DataLoader(
        dataset,
        batch_size=min(batch_size, max(1, len(dataset) // 2)),
        shuffle=False,
    )


def _run_epoch(trainer: IncrementalTrainer, samples: list[object]) -> dict[str, float | int]:
    loader = _build_train_loader(trainer, samples)
    optimizer = AdamW(trainer.model.parameters(), lr=1e-3)
    scheduler = LambdaLR(optimizer, lr_lambda=lambda _: 1.0)
    criterion = torch.nn.CrossEntropyLoss(reduction="none")
    train_loss = trainer._train_single_epoch(
        loader,
        optimizer,
        scheduler,
        criterion,
        None,
        sample_weights=None,
        accumulation_steps=1,
        gradient_clip_norm=1.0,
        amp_enabled=False,
    )
    return {
        "train_loss": float(train_loss),
        "mean_ewc_loss": float(getattr(trainer, "_last_epoch_mean_ewc_loss", 0.0)),
        "batch_count": len(loader),
        "sample_count": len(loader.dataset),
    }


def _store_cycle(grabber: AutoGrabber, samples: list[object]) -> tuple[tuple[str, ...], list[object]]:
    previous_shards = tuple(grabber._feature_store.list_shards())
    accepted_samples = []
    for sample in samples:
        grabber._store_feature_artifact(sample)
        accepted_samples.append(sample)
    return previous_shards, accepted_samples


def main() -> int:
    workspace = Path.cwd()
    runtime_root = workspace / ".tmp_hdd_drive" / "phase9b_integration_runtime"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)

    os.environ["YGB_CVE_DEDUP_STORE_PATH"] = str(runtime_root / "dedup_store.json")
    os.environ["YGB_AUTOGRABBER_FEATURE_STORE_PATH"] = str(runtime_root / "autograbber_features")
    os.environ["YGB_PREVIOUS_SEVERITIES_PATH"] = str(runtime_root / "previous_severities.json")

    trainer = IncrementalTrainer(
        model_path=runtime_root / "checkpoints" / "model.safetensors",
        state_path=runtime_root / "checkpoints" / "training_state.json",
        baseline_path=runtime_root / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=workspace / "data" / "raw",
        num_workers=0,
        feature_store_root=runtime_root / "trainer_features",
    )
    adaptive = AdaptiveLearner(
        state_path=runtime_root / "checkpoints" / "adaptive_learning_state.json",
        ewc_state_path=runtime_root / "checkpoints" / "adaptive_ewc_state.safetensors",
        history_size=3,
        shift_threshold=0.15,
        ewc_lambda=0.1,
        fisher_max_batches=64,
    )
    trainer.adaptive_learner = adaptive
    adaptive.attach_model(trainer.model)

    grabber = AutoGrabber(AutoGrabberConfig(sources=["nvd"], max_per_cycle=1))
    grabber._adaptive_learner = adaptive
    grabber._adaptive_learner.attach_model(trainer.model)

    indexed_samples = trainer._get_indexed_raw_samples(refresh=False)
    pools: dict[str, list[object]] = defaultdict(list)
    for _, sample in indexed_samples:
        pools[normalize_severity(sample.severity)].append(sample)
    for severity, samples in list(pools.items()):
        pools[severity] = sorted(samples, key=lambda item: (item.source, item.sha256_hash))

    real_counts = {severity: len(samples) for severity, samples in sorted(pools.items())}
    baseline_severities = [
        severity for severity in ("LOW", "MEDIUM", "HIGH") if len(pools.get(severity, [])) >= 8
    ]
    if not baseline_severities:
        baseline_severities = [
            severity
            for severity, samples in sorted(pools.items())
            if severity != "CRITICAL" and len(samples) >= 8
        ]
    if not baseline_severities:
        raise RuntimeError(f"unable to build baseline cycles from real data counts={real_counts}")
    selected_baseline = baseline_severities[: max(1, min(3, len(baseline_severities)))]
    baseline_per_severity = min(8, min(len(pools[severity]) // 2 for severity in selected_baseline))
    if baseline_per_severity < 2:
        raise RuntimeError(
            f"insufficient baseline severity coverage counts={real_counts} selected={selected_baseline}"
        )

    cycle1 = []
    cycle2 = []
    for severity in selected_baseline:
        cycle1.extend(pools[severity][:baseline_per_severity])
        cycle2.extend(pools[severity][baseline_per_severity : baseline_per_severity * 2])

    critical_pool = list(pools.get("CRITICAL", []))
    if len(critical_pool) < 4:
        raise RuntimeError(f"insufficient CRITICAL samples for shifted cycle counts={real_counts}")
    cycle3 = critical_pool[: min(len(critical_pool), max(8, len(cycle1)))]
    shift_tail_budget = max(0, min(len(cycle1) // 4, 4))
    for severity in reversed(selected_baseline):
        if shift_tail_budget <= 0:
            break
        tail = pools[severity][baseline_per_severity * 2 : baseline_per_severity * 2 + shift_tail_budget]
        cycle3.extend(tail)
        shift_tail_budget -= len(tail)

    unique_cycle3 = []
    seen_hashes: set[str] = set()
    for sample in cycle3:
        if sample.sha256_hash in seen_hashes:
            continue
        seen_hashes.add(sample.sha256_hash)
        unique_cycle3.append(sample)
    cycle3 = unique_cycle3

    pre_shift_train = _run_epoch(trainer, cycle1)

    cycle_records = []
    for cycle_id, samples in (("cycle-1", cycle1), ("cycle-2", cycle2), ("cycle-3", cycle3)):
        previous_shards, accepted_samples = _store_cycle(grabber, samples)
        event_count_before = len(adaptive.get_events())
        fisher_before = adaptive.regularizer.has_fisher()
        grabber._run_adaptive_learning_hook(
            cycle_id=cycle_id,
            accepted_samples=accepted_samples,
            previous_shard_names=previous_shards,
            errors=[],
        )
        cycle_records.append(
            {
                "cycle_id": cycle_id,
                "accepted_count": len(accepted_samples),
                "previous_shard_count": len(previous_shards),
                "severity_counts": _severity_counts(accepted_samples),
                "event_count_before": event_count_before,
                "event_count_after": len(adaptive.get_events()),
                "fisher_before": bool(fisher_before),
                "fisher_after": bool(adaptive.regularizer.has_fisher()),
            }
        )

    events = adaptive.get_events()
    if not events:
        raise RuntimeError("expected a distribution shift event after cycle-3, but no event was recorded")
    last_event = events[-1]
    if last_event.fisher_sample_count <= 0:
        raise RuntimeError(
            f"expected fisher samples after shift, got {last_event.fisher_sample_count}"
        )

    post_shift_train = _run_epoch(trainer, cycle3)
    if post_shift_train["mean_ewc_loss"] <= 0.0:
        raise RuntimeError(
            f"expected post-shift training to use EWC loss, got {post_shift_train['mean_ewc_loss']}"
        )

    state_path = runtime_root / "checkpoints" / "adaptive_learning_state.json"
    ewc_state_path = runtime_root / "checkpoints" / "adaptive_ewc_state.safetensors"
    if not state_path.exists():
        raise RuntimeError(f"adaptive state file was not persisted: {state_path}")
    if not ewc_state_path.exists():
        raise RuntimeError(f"ewc state file was not persisted: {ewc_state_path}")

    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    persisted_events = state_payload.get("events", [])
    if not persisted_events:
        raise RuntimeError("adaptive state payload did not persist any events")

    report = {
        "runtime_root": str(runtime_root),
        "real_data_counts": real_counts,
        "selected_baseline_severities": list(selected_baseline),
        "cycle_records": cycle_records,
        "pre_shift_train": pre_shift_train,
        "last_event": asdict(last_event),
        "post_shift_train": post_shift_train,
        "adaptive_state_path": str(state_path),
        "ewc_state_path": str(ewc_state_path),
        "persisted_event_count": len(persisted_events),
        "persisted_last_event_id": persisted_events[-1].get("event_id"),
        "shift_detected": bool(last_event.js_distance > last_event.threshold),
        "fisher_computed_after_shift": bool(
            last_event.fisher_sample_count > 0 and adaptive.regularizer.has_fisher()
        ),
        "ewc_used_in_training": bool(post_shift_train["mean_ewc_loss"] > 0.0),
    }
    report_path = runtime_root / "phase9b_integration_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT_PATH={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
