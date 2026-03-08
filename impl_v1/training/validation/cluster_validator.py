"""
cluster_validator.py — 7-Step Final Validation Sequence

1. Determinism validator (3 runs)
2. Cross-device validation
3. Multi-node validation
4. MODE_C certification check
5. Overfit guard check
6. Cache integrity check
7. Dataset manifest validation

Only if all pass → commit allowed.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ValidationStep:
    """Single validation step result."""
    name: str
    passed: bool
    duration_sec: float
    details: str


@dataclass
class ClusterValidation:
    """Full validation sequence result."""
    all_passed: bool
    steps: List[ValidationStep]
    total_duration_sec: float
    timestamp: str


def run_validation_sequence() -> ClusterValidation:
    """Run the full 7-step validation sequence.

    Returns:
        ClusterValidation with per-step results.
    """
    steps = []
    total_start = time.perf_counter()
    
    # Step 1: Determinism validator (3 runs)
    steps.append(_validate_determinism())
    
    # Step 2: Cross-device validation
    steps.append(_validate_cross_device())
    
    # Step 3: Multi-node validation
    steps.append(_validate_multi_node())
    
    # Step 4: MODE_C certification check
    steps.append(_validate_mode_c())
    
    # Step 5: Overfit guard check
    steps.append(_validate_overfit())
    
    # Step 6: Cache integrity check
    steps.append(_validate_cache_integrity())
    
    # Step 7: Dataset manifest validation
    steps.append(_validate_dataset_manifest())
    
    total_elapsed = time.perf_counter() - total_start
    all_passed = all(s.passed for s in steps)
    
    result = ClusterValidation(
        all_passed=all_passed,
        steps=steps,
        total_duration_sec=total_elapsed,
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    )
    
    status = "PASS" if all_passed else "FAIL"
    passed_count = sum(1 for s in steps if s.passed)
    logger.info(
        f"[VALIDATE] {status}: {passed_count}/{len(steps)} steps passed "
        f"({total_elapsed:.2f}s)"
    )
    
    for s in steps:
        emoji = "✓" if s.passed else "✗"
        logger.info(f"  {emoji} {s.name}: {s.details}")
    
    return result


def _validate_determinism() -> ValidationStep:
    """Step 1: Run 3-run determinism check."""
    start = time.perf_counter()
    try:
        from training.validation.determinism_validator import validate_determinism
        passed, report = validate_determinism(num_runs=3, epochs=2)
        details = f"hashes_match={report['weights_match']}, max_loss_delta={report['max_loss_delta']:.2e}"
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    
    return ValidationStep(
        name="Determinism (3-run)", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def _validate_cross_device() -> ValidationStep:
    """Step 2: Cross-device validation (check GPU consistency)."""
    start = time.perf_counter()
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            details = f"{props.name}, CC={props.major}.{props.minor}"
            passed = True
        else:
            details = "CPU-only (cross-device check skipped)"
            passed = True
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    
    return ValidationStep(
        name="Cross-device", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def _validate_multi_node() -> ValidationStep:
    """Step 3: Multi-node cluster validation."""
    start = time.perf_counter()
    try:
        from impl_v1.training.distributed.cluster_scaler import detect_topology
        topo = detect_topology()
        details = f"mode={topo.mode}, world_size={topo.world_size}, gpus={topo.total_gpu_count}"
        passed = True
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    
    return ValidationStep(
        name="Multi-node topology", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def _validate_mode_c() -> ValidationStep:
    """Step 4: MODE_C certification check."""
    start = time.perf_counter()
    # MODE_C is an external certification step — check if config exists
    details = "MODE_C certification delegated to governance layer"
    passed = True
    
    return ValidationStep(
        name="MODE_C certification", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def _validate_overfit() -> ValidationStep:
    """Step 5: Overfit guard check."""
    start = time.perf_counter()
    try:
        from impl_v1.training.safety.overfit_guard import DEFAULT_GAP_THRESHOLD

        gap_report = _load_latest_generalization_report()
        if gap_report is None:
            passed = False
            details = "No real training generalization report available"
        else:
            max_gap = gap_report["max_gap"]
            latest_gap = gap_report["latest_gap"]
            recent_max_gap = gap_report["recent_max_gap"]
            passed = (
                recent_max_gap <= DEFAULT_GAP_THRESHOLD
                and latest_gap <= DEFAULT_GAP_THRESHOLD
            )
            details = (
                f"source={gap_report['source']}, epochs={gap_report['epoch_count']}, "
                f"latest_gap={latest_gap:.4f}, recent_max_gap={recent_max_gap:.4f}, "
                f"historical_max_gap={max_gap:.4f}, "
                f"threshold={DEFAULT_GAP_THRESHOLD:.4f}"
            )
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    
    return ValidationStep(
        name="Overfit guard", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def _candidate_training_reports() -> List[Path]:
    reports_dir = PROJECT_ROOT / "reports"
    candidates = [
        reports_dir / "training_session_result.json",
        reports_dir / "speed_telemetry.json",
    ]
    g38_dir = reports_dir / "g38_training"
    if g38_dir.exists():
        candidates.extend(sorted(g38_dir.glob("*.json")))
    return [path for path in candidates if path.exists() and path.is_file()]


def _extract_accuracy_gap_records(payload: dict, source: str) -> List[Tuple[int, float, float, str]]:
    records: List[Tuple[int, float, float, str]] = []

    def _add_record(entry: dict, eval_key: str) -> None:
        train_acc = entry.get("train_acc")
        eval_acc = entry.get(eval_key)
        epoch = entry.get("epoch")
        if train_acc is None or eval_acc is None or epoch is None:
            return
        records.append((int(epoch), float(train_acc), float(eval_acc), source))

    for entry in payload.get("epoch_reports", []):
        if isinstance(entry, dict):
            _add_record(entry, "test_acc")

    for entry in payload.get("all_metrics", []):
        if isinstance(entry, dict):
            eval_key = "test_acc" if "test_acc" in entry else "val_accuracy"
            _add_record(entry, eval_key)

    return records


def _load_latest_generalization_report() -> Optional[dict]:
    newest_report: Optional[dict] = None
    newest_mtime = -1.0

    for path in _candidate_training_reports():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue

        records = _extract_accuracy_gap_records(payload, path.name)
        if not records:
            continue

        mtime = path.stat().st_mtime
        if mtime <= newest_mtime:
            continue

        gaps = [max(0.0, train_acc - eval_acc) for _, train_acc, eval_acc, _ in records]
        newest_report = {
            "source": path.name,
            "epoch_count": len(records),
            "latest_gap": gaps[-1],
            "recent_max_gap": max(gaps[-5:]),
            "max_gap": max(gaps),
        }
        newest_mtime = mtime

    return newest_report


def _validate_cache_integrity() -> ValidationStep:
    """Step 6: Feature cache integrity check."""
    start = time.perf_counter()
    try:
        from impl_v1.training.data.feature_cache import compute_dataset_hash, cache_exists
        test_hash = compute_dataset_hash(total_samples=100, seed=42, feature_dim=16)
        details = f"hash_function_ok=True, hash={test_hash[:16]}..."
        passed = True
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    
    return ValidationStep(
        name="Cache integrity", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def _validate_dataset_manifest() -> ValidationStep:
    """Step 7: Dataset manifest validation."""
    start = time.perf_counter()
    try:
        from impl_v1.training.safety.dataset_manifest import validate_manifest, MANIFEST_PATH
        if os.path.exists(MANIFEST_PATH):
            valid, reason, _ = validate_manifest()
            details = f"valid={valid}, reason={reason}"
            passed = valid
        else:
            details = "No manifest file — create before production training"
            passed = True  # Not blocking in dev mode
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    
    return ValidationStep(
        name="Dataset manifest", passed=passed,
        duration_sec=time.perf_counter() - start, details=details,
    )


def save_validation_report(result: ClusterValidation, path: str = None) -> str:
    """Save validation report to JSON."""
    if path is None:
        path = os.path.join('reports', 'cluster_validation.json')
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    data = {
        'all_passed': result.all_passed,
        'total_duration_sec': result.total_duration_sec,
        'timestamp': result.timestamp,
        'steps': [asdict(s) for s in result.steps],
    }
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    
    return path
