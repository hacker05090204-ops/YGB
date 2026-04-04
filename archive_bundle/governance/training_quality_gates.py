"""
Training Quality Gates — Comprehensive Data Quality Validation

10 gates that ALL must pass before training promotion:
  1. label_quality_gate          - Bad/missing/multi-label inconsistencies
  2. class_imbalance_guard       - Class distribution skew
  3. duplicate_intelligence_guard - Duplicate/near-duplicate samples
  4. distribution_shift_guard    - Feature distribution shift between splits
  5. feature_mismatch_guard      - Feature schema mismatch
  6. drift_guard                 - Data drift over time
  7. regression_gate             - Performance regression check
  8. determinism_check           - Reproducibility verification
  9. backtest_gate               - Holdout backtesting
 10. mode_promotion_gate         - LAB → PRODUCTION promotion eligibility

Each gate returns (passed, reason, metrics).
evaluate_all_gates() blocks promotion if ANY gate fails.
"""

import os
import logging
from typing import Tuple, Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("ygb.training_gates")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Minimum samples per field (production vs lab)
MIN_SAMPLES_PRODUCTION = int(os.environ.get("YGB_MIN_REAL_SAMPLES", "125000"))
MIN_SAMPLES_LAB = int(os.environ.get("YGB_MIN_LAB_SAMPLES", "125000"))

# Gate thresholds
MAX_MISSING_LABEL_RATIO = 0.01       # Max 1% missing labels
MAX_MULTI_LABEL_RATIO = 0.005        # Max 0.5% multi-label inconsistency
MAX_CLASS_IMBALANCE_RATIO = 0.10     # Max 10% imbalance between classes
MAX_DUPLICATE_RATIO = 0.02           # Max 2% exact duplicates
MAX_NEAR_DUPLICATE_RATIO = 0.05      # Max 5% near-duplicates
MAX_DISTRIBUTION_SHIFT = 0.15        # Max 15% KL divergence
MAX_FEATURE_MISMATCH = 0             # Zero tolerance for schema mismatch
MAX_DRIFT_SCORE = 0.20               # Max 20% drift score
MAX_REGRESSION_LOSS = 0.02           # Max 2% performance regression
DETERMINISM_TOLERANCE = 1e-6         # Float tolerance for determinism
BACKTEST_MIN_ACCURACY = 0.85         # Min 85% backtest accuracy


GateResult = Tuple[bool, str, Dict[str, Any]]


# =============================================================================
# GATE IMPLEMENTATIONS
# =============================================================================

def label_quality_gate(
    total_samples: int,
    missing_labels: int = 0,
    bad_labels: int = 0,
    multi_label_conflicts: int = 0,
) -> GateResult:
    """Gate 1: Check label quality — missing, bad, multi-label inconsistencies."""
    if total_samples == 0:
        return False, "EMPTY_DATASET", {"total": 0}

    missing_ratio = missing_labels / total_samples
    bad_ratio = bad_labels / total_samples
    multi_ratio = multi_label_conflicts / total_samples

    metrics = {
        "total_samples": total_samples,
        "missing_labels": missing_labels,
        "missing_ratio": round(missing_ratio, 4),
        "bad_labels": bad_labels,
        "bad_ratio": round(bad_ratio, 4),
        "multi_label_conflicts": multi_label_conflicts,
        "multi_label_ratio": round(multi_ratio, 4),
    }

    if missing_ratio > MAX_MISSING_LABEL_RATIO:
        return False, f"MISSING_LABELS: {missing_ratio:.2%} exceeds {MAX_MISSING_LABEL_RATIO:.2%}", metrics
    if bad_ratio > MAX_MISSING_LABEL_RATIO:
        return False, f"BAD_LABELS: {bad_ratio:.2%} exceeds threshold", metrics
    if multi_ratio > MAX_MULTI_LABEL_RATIO:
        return False, f"MULTI_LABEL_CONFLICT: {multi_ratio:.2%} exceeds {MAX_MULTI_LABEL_RATIO:.2%}", metrics

    return True, "Label quality OK", metrics


def class_imbalance_guard(
    class_counts: Dict[str, int],
) -> GateResult:
    """Gate 2: Check class distribution balance."""
    if not class_counts:
        return False, "NO_CLASSES", {}

    counts = list(class_counts.values())
    total = sum(counts)
    if total == 0:
        return False, "EMPTY_DATASET", {"classes": class_counts}

    expected = total / len(counts)
    max_deviation = max(abs(c - expected) / expected for c in counts)

    metrics = {
        "class_counts": class_counts,
        "total_samples": total,
        "num_classes": len(counts),
        "max_deviation": round(max_deviation, 4),
        "threshold": MAX_CLASS_IMBALANCE_RATIO,
    }

    if max_deviation > MAX_CLASS_IMBALANCE_RATIO:
        return False, f"CLASS_IMBALANCE: {max_deviation:.2%} deviation exceeds {MAX_CLASS_IMBALANCE_RATIO:.2%}", metrics

    return True, "Class balance OK", metrics


def duplicate_intelligence_guard(
    total_samples: int,
    exact_duplicates: int = 0,
    near_duplicates: int = 0,
) -> GateResult:
    """Gate 3: Check for duplicate samples."""
    if total_samples == 0:
        return False, "EMPTY_DATASET", {}

    exact_ratio = exact_duplicates / total_samples
    near_ratio = near_duplicates / total_samples

    metrics = {
        "total_samples": total_samples,
        "exact_duplicates": exact_duplicates,
        "exact_ratio": round(exact_ratio, 4),
        "near_duplicates": near_duplicates,
        "near_ratio": round(near_ratio, 4),
    }

    if exact_ratio > MAX_DUPLICATE_RATIO:
        return False, f"EXACT_DUPLICATES: {exact_ratio:.2%} exceeds {MAX_DUPLICATE_RATIO:.2%}", metrics
    if near_ratio > MAX_NEAR_DUPLICATE_RATIO:
        return False, f"NEAR_DUPLICATES: {near_ratio:.2%} exceeds {MAX_NEAR_DUPLICATE_RATIO:.2%}", metrics

    return True, "Duplicate check OK", metrics


def distribution_shift_guard(
    kl_divergence: float,
    feature_name: str = "default",
) -> GateResult:
    """Gate 4: Check feature distribution shift between train/val splits."""
    metrics = {
        "feature": feature_name,
        "kl_divergence": round(kl_divergence, 4),
        "threshold": MAX_DISTRIBUTION_SHIFT,
    }

    if kl_divergence > MAX_DISTRIBUTION_SHIFT:
        return False, f"DISTRIBUTION_SHIFT: KL={kl_divergence:.4f} on '{feature_name}' exceeds {MAX_DISTRIBUTION_SHIFT}", metrics

    return True, f"Distribution '{feature_name}' OK", metrics


def feature_mismatch_guard(
    expected_features: List[str],
    actual_features: List[str],
) -> GateResult:
    """Gate 5: Check feature schema matches expected schema."""
    expected_set = set(expected_features)
    actual_set = set(actual_features)

    missing = expected_set - actual_set
    extra = actual_set - expected_set

    metrics = {
        "expected_count": len(expected_features),
        "actual_count": len(actual_features),
        "missing_features": sorted(missing),
        "extra_features": sorted(extra),
    }

    if missing or extra:
        return False, f"FEATURE_MISMATCH: {len(missing)} missing, {len(extra)} extra", metrics

    return True, "Feature schema matches", metrics


def drift_guard(
    drift_score: float,
    window_name: str = "default",
) -> GateResult:
    """Gate 6: Check data drift score over time."""
    metrics = {
        "drift_score": round(drift_score, 4),
        "window": window_name,
        "threshold": MAX_DRIFT_SCORE,
    }

    if drift_score > MAX_DRIFT_SCORE:
        return False, f"DATA_DRIFT: score={drift_score:.4f} in window '{window_name}' exceeds {MAX_DRIFT_SCORE}", metrics

    return True, f"Drift '{window_name}' OK", metrics


def regression_gate(
    baseline_metric: float,
    current_metric: float,
    metric_name: str = "accuracy",
) -> GateResult:
    """Gate 7: Check for performance regression."""
    if baseline_metric <= 0:
        return False, "INVALID_BASELINE", {"baseline": baseline_metric}

    regression = (baseline_metric - current_metric) / baseline_metric

    metrics = {
        "metric_name": metric_name,
        "baseline": round(baseline_metric, 4),
        "current": round(current_metric, 4),
        "regression": round(regression, 4),
        "threshold": MAX_REGRESSION_LOSS,
    }

    if regression > MAX_REGRESSION_LOSS:
        return False, f"REGRESSION: {metric_name} dropped {regression:.2%} (>{MAX_REGRESSION_LOSS:.2%})", metrics

    return True, f"No regression in {metric_name}", metrics


def determinism_check(
    run1_output: float,
    run2_output: float,
) -> GateResult:
    """Gate 8: Check training reproducibility."""
    diff = abs(run1_output - run2_output)

    metrics = {
        "run1": run1_output,
        "run2": run2_output,
        "absolute_diff": diff,
        "tolerance": DETERMINISM_TOLERANCE,
    }

    if diff > DETERMINISM_TOLERANCE:
        return False, f"NON_DETERMINISTIC: diff={diff} exceeds tolerance={DETERMINISM_TOLERANCE}", metrics

    return True, "Determinism verified", metrics


def backtest_gate(
    backtest_accuracy: float,
    holdout_size: int = 0,
) -> GateResult:
    """Gate 9: Check holdout backtesting accuracy."""
    metrics = {
        "backtest_accuracy": round(backtest_accuracy, 4),
        "min_required": BACKTEST_MIN_ACCURACY,
        "holdout_size": holdout_size,
    }

    if backtest_accuracy < BACKTEST_MIN_ACCURACY:
        return False, f"BACKTEST_FAIL: accuracy={backtest_accuracy:.4f} below {BACKTEST_MIN_ACCURACY}", metrics

    return True, f"Backtest accuracy {backtest_accuracy:.4f} >= {BACKTEST_MIN_ACCURACY}", metrics


def mode_promotion_gate(
    current_mode: str,
    target_mode: str,
    total_samples: int,
    all_gates_passed: bool,
) -> GateResult:
    """Gate 10: Check if mode promotion is allowed (LAB → PRODUCTION)."""
    is_production = target_mode.upper() in ("PRODUCTION", "PROD", "REAL")
    min_samples = MIN_SAMPLES_PRODUCTION if is_production else MIN_SAMPLES_LAB

    metrics = {
        "current_mode": current_mode,
        "target_mode": target_mode,
        "total_samples": total_samples,
        "min_required": min_samples,
        "sample_delta": max(0, min_samples - total_samples),
        "all_gates_passed": all_gates_passed,
    }

    if total_samples < min_samples:
        return False, (
            f"INSUFFICIENT_SAMPLES: {total_samples} < {min_samples} "
            f"(need {min_samples - total_samples} more)"
        ), metrics

    if not all_gates_passed:
        return False, "GATES_NOT_PASSED: cannot promote with failing gates", metrics

    return True, f"Promotion {current_mode} → {target_mode} approved", metrics


# =============================================================================
# ORCHESTRATOR
# =============================================================================

@dataclass
class GateReport:
    """Result of evaluating all gates."""
    all_passed: bool
    passed_count: int
    failed_count: int
    blocked_reason: Optional[str]
    gate_results: Dict[str, Dict[str, Any]]
    total_samples: int
    min_required: int
    sample_delta: int


def evaluate_all_gates(
    total_samples: int,
    missing_labels: int = 0,
    bad_labels: int = 0,
    multi_label_conflicts: int = 0,
    class_counts: Optional[Dict[str, int]] = None,
    exact_duplicates: int = 0,
    near_duplicates: int = 0,
    kl_divergence: float = 0.0,
    expected_features: Optional[List[str]] = None,
    actual_features: Optional[List[str]] = None,
    drift_score: float = 0.0,
    baseline_metric: float = 1.0,
    current_metric: float = 1.0,
    run1_output: float = 0.0,
    run2_output: float = 0.0,
    backtest_accuracy: float = 1.0,
    holdout_size: int = 0,
    current_mode: str = "LAB",
    target_mode: str = "PRODUCTION",
) -> GateReport:
    """Evaluate ALL training quality gates. Blocks promotion if ANY fails."""
    results: Dict[str, Dict[str, Any]] = {}
    all_pass = True

    # Run each gate
    gates = [
        ("label_quality", label_quality_gate(total_samples, missing_labels, bad_labels, multi_label_conflicts)),
        ("class_imbalance", class_imbalance_guard(class_counts or {"default": total_samples})),
        ("duplicate_intelligence", duplicate_intelligence_guard(total_samples, exact_duplicates, near_duplicates)),
        ("distribution_shift", distribution_shift_guard(kl_divergence)),
        ("feature_mismatch", feature_mismatch_guard(expected_features or [], actual_features or expected_features or [])),
        ("drift", drift_guard(drift_score)),
        ("regression", regression_gate(baseline_metric, current_metric)),
        ("determinism", determinism_check(run1_output, run2_output)),
        ("backtest", backtest_gate(backtest_accuracy, holdout_size)),
    ]

    first_failure = None
    passed = 0
    failed = 0

    for name, (gate_pass, reason, metrics) in gates:
        results[name] = {
            "passed": gate_pass,
            "reason": reason,
            "metrics": metrics,
        }
        if gate_pass:
            passed += 1
        else:
            failed += 1
            all_pass = False
            if first_failure is None:
                first_failure = f"{name}: {reason}"

    # Mode promotion gate (depends on all_pass)
    promo_pass, promo_reason, promo_metrics = mode_promotion_gate(
        current_mode, target_mode, total_samples, all_pass,
    )
    results["mode_promotion"] = {
        "passed": promo_pass,
        "reason": promo_reason,
        "metrics": promo_metrics,
    }
    if promo_pass:
        passed += 1
    else:
        failed += 1
        all_pass = False
        if first_failure is None:
            first_failure = f"mode_promotion: {promo_reason}"

    min_required = MIN_SAMPLES_PRODUCTION if target_mode.upper() in ("PRODUCTION", "PROD", "REAL") else MIN_SAMPLES_LAB

    return GateReport(
        all_passed=all_pass,
        passed_count=passed,
        failed_count=failed,
        blocked_reason=first_failure,
        gate_results=results,
        total_samples=total_samples,
        min_required=min_required,
        sample_delta=max(0, min_required - total_samples),
    )
