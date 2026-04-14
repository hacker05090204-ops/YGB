from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

DEFAULT_RUNTIME_STATUS_PATH = Path("data/runtime_status.json")
IncrementalTrainer = None
logger = logging.getLogger("ygb.training.runtime_status_validator")
MIN_PROMOTION_F1 = 0.75
MIN_PROMOTION_PRECISION = 0.70
MIN_PROMOTION_RECALL = 0.65

if TYPE_CHECKING:
    from backend.training.incremental_trainer import AccuracySnapshot


class TrainingGovernanceError(RuntimeError):
    """Raised when a governance gate blocks training or promotion."""

    def __init__(
        self,
        message: str,
        *,
        status: str = "FAILED",
        reasons: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.status = str(status or "FAILED")
        self.reasons = tuple(str(reason) for reason in (reasons or ()))
        super().__init__(message)


class PromotionReadinessError(TrainingGovernanceError):
    """Raised when promotion readiness thresholds are not met."""

    def __init__(self, snapshot: "AccuracySnapshot", failed_reasons: list[str]) -> None:
        self.snapshot = snapshot
        self.failed_reasons = tuple(str(reason) for reason in failed_reasons)
        status = (
            "BLOCKED_LOW_ACCURACY"
            if snapshot.f1 < MIN_PROMOTION_F1
            else "PROMOTION_BLOCKED"
        )
        super().__init__(
            "promotion readiness failed: " + "; ".join(self.failed_reasons),
            status=status,
            reasons=self.failed_reasons,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


def validate_promotion_readiness(snapshot: "AccuracySnapshot") -> bool:
    failed_reasons: list[str] = []
    if snapshot.f1 < MIN_PROMOTION_F1:
        logger.warning(
            "promotion readiness failed: f1=%.4f < min_f1=0.7500",
            snapshot.f1,
        )
        failed_reasons.append(
            f"f1={snapshot.f1:.4f} < min_f1={MIN_PROMOTION_F1:.4f}"
        )
    if snapshot.precision < MIN_PROMOTION_PRECISION:
        logger.warning(
            "promotion readiness failed: precision=%.4f < min_precision=0.7000",
            snapshot.precision,
        )
        failed_reasons.append(
            "precision="
            f"{snapshot.precision:.4f} < min_precision={MIN_PROMOTION_PRECISION:.4f}"
        )
    if snapshot.recall < MIN_PROMOTION_RECALL:
        logger.warning(
            "promotion readiness failed: recall=%.4f < min_recall=0.6500",
            snapshot.recall,
        )
        failed_reasons.append(
            f"recall={snapshot.recall:.4f} < min_recall={MIN_PROMOTION_RECALL:.4f}"
        )
    if failed_reasons:
        error = PromotionReadinessError(snapshot, failed_reasons)
        logger.error(
            "promotion readiness hard block: status=%s reasons=%s",
            error.status,
            "; ".join(error.failed_reasons),
        )
        raise error
    return True


def validate_precision_breach_status(
    runtime_status_path: str | Path = DEFAULT_RUNTIME_STATUS_PATH,
    *,
    max_samples: int | None = None,
    precision_threshold: float | None = None,
) -> dict[str, object]:
    trainer_cls = IncrementalTrainer
    if trainer_cls is None:
        from backend.training.incremental_trainer import IncrementalTrainer as trainer_cls

    status_path = Path(runtime_status_path)
    if not status_path.exists():
        return {"checked": False, "changed": False, "reason": "runtime_status_missing"}

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if not bool(payload.get("precision_breach")):
        return {"checked": False, "changed": False, "reason": "precision_breach_not_set"}

    effective_threshold = float(
        precision_threshold
        if precision_threshold is not None
        else os.environ.get("YGB_RUNTIME_MIN_PRECISION", "0.95")
    )
    effective_samples = int(max_samples or os.environ.get("YGB_RUNTIME_VALIDATION_SAMPLES", "1500"))

    trainer = trainer_cls(num_workers=0)
    benchmark = trainer.benchmark_current_model(max_samples=effective_samples)
    current_precision = float(benchmark["precision"])

    updated = dict(payload)
    updated["current_precision"] = round(current_precision, 6)
    updated["precision_threshold"] = round(effective_threshold, 6)
    updated["decision_threshold"] = round(float(benchmark["threshold"]), 9)
    updated["validation_samples"] = int(benchmark["samples"])
    updated["validation_source"] = str(benchmark["source"])
    updated["validation_checked_at"] = _utc_now()

    if current_precision >= effective_threshold:
        updated["precision_breach"] = False
        if str(updated.get("containment_reason") or "").startswith("precision_breach:"):
            updated["containment_active"] = False
            updated["containment_reason"] = None
        if updated.get("merge_status") == "blocked_precision_breach":
            updated["merge_status"] = None
        state = "cleared"
    else:
        updated["precision_breach"] = True
        updated["containment_active"] = True
        updated["containment_reason"] = (
            f"precision_breach: current_precision={current_precision:.4f} "
            f"< threshold={effective_threshold:.4f}"
        )
        updated["merge_status"] = "blocked_precision_breach"
        state = "blocked"

    changed = updated != payload
    if changed:
        _atomic_write_json(status_path, updated)

    return {
        "checked": True,
        "changed": changed,
        "state": state,
        "current_precision": current_precision,
        "precision_threshold": effective_threshold,
        "decision_threshold": float(benchmark["threshold"]),
        "validation_samples": int(benchmark["samples"]),
        "validation_source": str(benchmark["source"]),
        "recommended_threshold": float(benchmark["recommended_threshold"]),
        "recommended_strategy": str(benchmark["recommended_strategy"]),
    }
