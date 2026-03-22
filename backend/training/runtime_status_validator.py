from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from backend.training.incremental_trainer import IncrementalTrainer

DEFAULT_RUNTIME_STATUS_PATH = Path("data/runtime_status.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


def validate_precision_breach_status(
    runtime_status_path: str | Path = DEFAULT_RUNTIME_STATUS_PATH,
    *,
    max_samples: int | None = None,
    precision_threshold: float | None = None,
) -> dict[str, object]:
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

    trainer = IncrementalTrainer(num_workers=0)
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
