from __future__ import annotations

import json
import math
import re
import shutil
import time
from dataclasses import replace
from pathlib import Path

import torch
from torch.optim import AdamW

from backend.training.incremental_trainer import IncrementalTrainer
from backend.training.training_optimizer import WarmupCosineScheduler


def _sanitize(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


def main() -> None:
    work_root = Path(".tmp_hdd_drive/phase8b_runtime/artifacts")
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    result_path = work_root / "phase8b_result.json"

    canonical_cve = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
    trainer = IncrementalTrainer(
        model_path=work_root / "model.safetensors",
        state_path=work_root / "training_state.json",
        baseline_path=work_root / "baseline_accuracy.json",
        raw_data_root=Path("data/raw"),
        feature_store_root=work_root / "feature_store",
        num_workers=0,
    )

    indexed_samples = trainer._get_indexed_raw_samples(refresh=False)
    real_cve_samples = [
        sample
        for _, sample in indexed_samples
        if canonical_cve.fullmatch(str(sample.cve_id or "").strip())
    ]
    available_real_cve_samples = len(real_cve_samples)
    requested_sample_count = 500
    selected_sample_count = min(requested_sample_count, available_real_cve_samples)
    if selected_sample_count <= 0:
        raise RuntimeError("No real CVE samples available for Phase 8 integration")

    selected_indices = trainer._deterministic_indices(
        available_real_cve_samples,
        selected_sample_count,
    )
    selected_samples = [real_cve_samples[index] for index in selected_indices]
    slice_note = (
        "exact_500_real_cve_samples"
        if selected_sample_count == requested_sample_count
        else f"closest_honest_real_data_slice_{selected_sample_count}_real_cve_samples"
    )

    train_loader, val_loader = trainer.build_dataset(
        selected_samples,
        include_train_dataset_indices=True,
    )
    config = replace(trainer.optimizer_config, max_epochs=5)
    optimizer = AdamW(
        trainer.model.parameters(),
        lr=config.learning_rate,
        weight_decay=0.01,
    )
    optimizer_steps_per_epoch = max(
        1,
        math.ceil(max(len(train_loader), 1) / config.accumulation_steps),
    )
    total_scheduler_steps = max(1, optimizer_steps_per_epoch * config.max_epochs)
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=total_scheduler_steps,
        warmup_steps=config.resolved_warmup_steps(total_scheduler_steps),
        min_lr=config.min_learning_rate,
        warmup_start_factor=config.warmup_start_factor,
    )
    amp_used = config.amp_enabled(trainer.device)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    scaler = torch.cuda.amp.GradScaler(enabled=True) if amp_used else None
    class_weight_tensor = trainer._current_class_weight_tensor()
    train_criterion = torch.nn.CrossEntropyLoss(
        weight=class_weight_tensor,
        reduction="none",
    )
    eval_criterion = torch.nn.CrossEntropyLoss()

    train_start = time.perf_counter()
    summary = trainer.train(
        train_loader,
        optimizer,
        scheduler,
        train_criterion,
        scaler,
        sample_weights=None,
        val_loader=val_loader,
        eval_criterion=eval_criterion,
        optimiser_config=config,
        return_history=True,
    )
    train_seconds = time.perf_counter() - train_start
    trainer.positive_threshold = float(summary.positive_threshold)

    effective_training_samples = int(summary.epochs_completed * len(train_loader.dataset))
    training_throughput_sps = (
        float(effective_training_samples / train_seconds) if train_seconds > 0.0 else None
    )
    gpu_memory_mb = (
        float(torch.cuda.max_memory_allocated() / (1024.0 * 1024.0))
        if torch.cuda.is_available()
        else None
    )

    trainer.load_evaluation_samples = lambda max_samples=selected_sample_count: (
        selected_samples[: min(selected_sample_count, max_samples)],
        slice_note,
    )
    benchmark_start = time.perf_counter()
    benchmark = trainer.benchmark_current_model(max_samples=selected_sample_count)
    benchmark_seconds = time.perf_counter() - benchmark_start
    benchmark_inference_throughput_sps = (
        float(benchmark["samples"] / benchmark_seconds)
        if benchmark_seconds > 0.0
        else None
    )

    metrics_report = summary.metrics_report.to_dict() if summary.metrics_report is not None else None
    result = {
        "integration": {
            "available_real_cve_samples": available_real_cve_samples,
            "selected_sample_count": selected_sample_count,
            "slice_note": slice_note,
            "train_dataset_size_after_real_sample_oversampling": len(train_loader.dataset),
            "validation_dataset_size": len(val_loader.dataset),
            "validation_f1": summary.f1,
            "validation_precision": summary.precision,
            "validation_recall": summary.recall,
            "validation_accuracy": summary.accuracy,
            "validation_auc_roc": summary.auc_roc,
            "epochs_completed": summary.epochs_completed,
            "early_stopping_available": True,
            "early_stopped": bool(summary.early_stopped),
            "class_weights_applied_in_loss_path": class_weight_tensor is not None,
            "class_weights": class_weight_tensor.detach().cpu().tolist() if class_weight_tensor is not None else None,
            "metrics_emitted": metrics_report is not None,
            "metrics_report": metrics_report,
        },
        "benchmark": {
            "device": str(trainer.device),
            "cpu_only": not torch.cuda.is_available(),
            "amp_requested": bool(config.use_amp),
            "amp_used": bool(amp_used),
            "gpu_memory_mb": gpu_memory_mb,
            "training_seconds": train_seconds,
            "training_throughput_samples_per_second": training_throughput_sps,
            "effective_training_samples_processed": effective_training_samples,
            "observed_5_epoch_outcome": {
                "epochs_completed": summary.epochs_completed,
                "early_stopped": bool(summary.early_stopped),
                "validation_f1": summary.f1,
            },
            "benchmark_seconds": benchmark_seconds,
            "benchmark_inference_throughput_samples_per_second": benchmark_inference_throughput_sps,
            "benchmark_metrics": benchmark,
        },
    }

    result_path.write_text(
        json.dumps(_sanitize(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    assert summary.f1 > 0.50, f"Validation F1 gate failed: {summary.f1:.4f}"
    assert class_weight_tensor is not None and bool(torch.count_nonzero(class_weight_tensor).item()), (
        "Class weights not applied in loss path"
    )
    assert hasattr(summary, "early_stopped"), "Early stopping behavior unavailable"
    assert summary.metrics_report is not None and len(summary.metrics_report.per_class) >= 2, (
        "Detailed per-class metrics missing"
    )
    print(result_path.as_posix())
    print(result_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
