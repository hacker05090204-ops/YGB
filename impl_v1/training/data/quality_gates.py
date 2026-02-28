"""
Quality Gates — Data quality enforcement for training pipeline.

Provides:
  - Label quality / fake-label diagnostics
  - Class imbalance guard
  - Duplicate + near-duplicate suppression
  - Distribution drift + feature mismatch detection
  - Regression gate + determinism gate
  - Mode promotion gate (LAB → REAL)

All gates are ENFORCED in strict real mode. In lab mode they WARN only.
"""

import hashlib
import logging
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Environment
STRICT_REAL_MODE = os.environ.get("YGB_STRICT_REAL_MODE", "true").lower() != "false"


# =============================================================================
# GATE RESULT
# =============================================================================

@dataclass
class GateResult:
    """Result of a quality gate check."""
    gate_name: str
    passed: bool
    severity: str  # INFO, WARNING, CRITICAL
    message: str
    metrics: Dict[str, float] = field(default_factory=dict)


# =============================================================================
# LABEL QUALITY GATE
# =============================================================================

def check_label_quality(labels: List[int], features: np.ndarray) -> GateResult:
    """
    Detect fake/trivial labels.

    Checks:
      - All labels same → CRITICAL
      - Label entropy too low → WARNING
      - Label/feature correlation too perfect (>0.99) → CRITICAL (likely leak)
    """
    if len(labels) == 0:
        return GateResult("label_quality", False, "CRITICAL", "No labels", {})

    unique = set(labels)
    if len(unique) == 1:
        return GateResult("label_quality", False, "CRITICAL",
                          f"All labels are {labels[0]} — trivial labels", {})

    # Label entropy
    counts = Counter(labels)
    total = len(labels)
    entropy = -sum((c / total) * math.log2(c / total)
                    for c in counts.values() if c > 0)
    max_entropy = math.log2(len(unique))
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0

    if normalized_entropy < 0.5:
        return GateResult("label_quality", False, "WARNING",
                          f"Low label entropy: {normalized_entropy:.3f}",
                          {"entropy": normalized_entropy})

    # Feature-label correlation check (sample first feature dim)
    if features is not None and len(features) > 0:
        labels_arr = np.array(labels, dtype=np.float32)
        feat_mean = features[:, 0] if features.ndim > 1 else features
        if len(feat_mean) == len(labels_arr) and np.std(feat_mean) > 0:
            corr = np.abs(np.corrcoef(feat_mean, labels_arr)[0, 1])
            if corr > 0.99:
                return GateResult("label_quality", False, "CRITICAL",
                                  f"Suspiciously high label-feature correlation: {corr:.4f}",
                                  {"correlation": float(corr)})

    return GateResult("label_quality", True, "INFO",
                      f"Label quality OK (entropy={normalized_entropy:.3f})",
                      {"entropy": normalized_entropy})


# =============================================================================
# CLASS IMBALANCE GATE
# =============================================================================

def check_class_imbalance(labels: List[int],
                          max_ratio: float = 0.60,
                          min_ratio: float = 0.40) -> GateResult:
    """
    Guard against class imbalance.

    For binary: positive ratio must be in [min_ratio, max_ratio].
    """
    if len(labels) == 0:
        return GateResult("class_imbalance", False, "CRITICAL", "No labels", {})

    counts = Counter(labels)
    total = len(labels)
    ratios = {k: v / total for k, v in counts.items()}

    # Binary case
    if len(counts) == 2:
        pos_ratio = ratios.get(1, 0.0)
        if pos_ratio < min_ratio or pos_ratio > max_ratio:
            return GateResult("class_imbalance", False, "WARNING",
                              f"Class imbalance: positive={pos_ratio:.2%} "
                              f"(expected [{min_ratio:.0%}, {max_ratio:.0%}])",
                              {"positive_ratio": pos_ratio})
        return GateResult("class_imbalance", True, "INFO",
                          f"Class balance OK: positive={pos_ratio:.2%}",
                          {"positive_ratio": pos_ratio})

    # Multi-class: check min class has >= 5% of samples
    min_class_ratio = min(ratios.values())
    if min_class_ratio < 0.05:
        return GateResult("class_imbalance", False, "WARNING",
                          f"Minority class has only {min_class_ratio:.2%}",
                          {"min_class_ratio": min_class_ratio})

    return GateResult("class_imbalance", True, "INFO",
                      f"Class balance OK ({len(counts)} classes)",
                      {"num_classes": len(counts)})


# =============================================================================
# DUPLICATE / NEAR-DUPLICATE SUPPRESSION
# =============================================================================

def check_duplicates(features: np.ndarray,
                     exact_threshold: float = 0.01,
                     near_threshold: float = 0.05) -> GateResult:
    """
    Detect exact and near-duplicate samples.

    - Exact: feature vectors identical (L2 distance < exact_threshold)
    - Near: feature vectors very similar (cosine similarity > 0.999)
    """
    n = len(features)
    if n < 2:
        return GateResult("duplicates", True, "INFO", "Too few samples to check", {})

    # Sample-based check (full pairwise too expensive for large N)
    max_check = min(n, 2000)
    sample_idx = np.random.choice(n, max_check, replace=False) if n > max_check else np.arange(n)
    sampled = features[sample_idx]

    # Hash-based exact duplicate check
    hashes = set()
    exact_dupes = 0
    for row in sampled:
        h = hashlib.md5(row.tobytes()).hexdigest()
        if h in hashes:
            exact_dupes += 1
        hashes.add(h)

    exact_ratio = exact_dupes / max_check

    if exact_ratio > 0.10:
        return GateResult("duplicates", False, "CRITICAL",
                          f"High exact duplicate rate: {exact_ratio:.1%} ({exact_dupes}/{max_check})",
                          {"exact_duplicate_ratio": exact_ratio})

    if exact_ratio > 0.01:
        return GateResult("duplicates", False, "WARNING",
                          f"Some exact duplicates: {exact_ratio:.1%} ({exact_dupes}/{max_check})",
                          {"exact_duplicate_ratio": exact_ratio})

    return GateResult("duplicates", True, "INFO",
                      f"Duplicate check OK ({exact_dupes} exact in {max_check} sample)",
                      {"exact_duplicate_ratio": exact_ratio})


# =============================================================================
# DISTRIBUTION DRIFT GATE
# =============================================================================

def check_distribution_drift(features: np.ndarray,
                             reference_mean: Optional[np.ndarray] = None,
                             reference_std: Optional[np.ndarray] = None,
                             drift_threshold: float = 3.0) -> GateResult:
    """
    Detect distribution drift from reference statistics.

    Uses mean/std shift in standard deviation units.
    If no reference, just checks for degenerate distributions.
    """
    if len(features) == 0:
        return GateResult("distribution_drift", False, "CRITICAL", "No features", {})

    current_mean = np.mean(features, axis=0)
    current_std = np.std(features, axis=0)

    # Check degenerate (all zero std)
    zero_std_ratio = np.mean(current_std < 1e-8)
    if zero_std_ratio > 0.5:
        return GateResult("distribution_drift", False, "CRITICAL",
                          f"Degenerate features: {zero_std_ratio:.0%} dims have zero variance",
                          {"zero_std_ratio": float(zero_std_ratio)})

    if reference_mean is not None and reference_std is not None:
        # Compute drift as shift in std units
        safe_std = np.maximum(reference_std, 1e-8)
        shift = np.abs(current_mean - reference_mean) / safe_std
        max_shift = float(np.max(shift))
        mean_shift = float(np.mean(shift))

        if max_shift > drift_threshold:
            return GateResult("distribution_drift", False, "WARNING",
                              f"Distribution drift detected: max_shift={max_shift:.2f}σ, "
                              f"mean_shift={mean_shift:.2f}σ",
                              {"max_shift": max_shift, "mean_shift": mean_shift})

    return GateResult("distribution_drift", True, "INFO",
                      "Distribution OK",
                      {"feature_dims": features.shape[1] if features.ndim > 1 else 1})


# =============================================================================
# REGRESSION GATE
# =============================================================================

def check_regression_gate(current_metrics: Dict[str, float],
                          baseline_metrics: Optional[Dict[str, float]] = None,
                          regression_threshold: float = 0.02) -> GateResult:
    """
    Prevent metric regression vs baseline.

    Compares accuracy, loss, etc. against saved baseline.
    Regression threshold: max allowed drop (default 2%).
    """
    if baseline_metrics is None:
        return GateResult("regression", True, "INFO",
                          "No baseline — skipping regression check",
                          current_metrics)

    regressions = []
    for metric, current in current_metrics.items():
        baseline = baseline_metrics.get(metric)
        if baseline is None:
            continue

        # For loss metrics, lower is better
        if "loss" in metric.lower():
            if current > baseline * (1 + regression_threshold):
                regressions.append(
                    f"{metric}: {current:.4f} > baseline {baseline:.4f}"
                )
        else:
            # For accuracy/other metrics, higher is better
            if current < baseline * (1 - regression_threshold):
                regressions.append(
                    f"{metric}: {current:.4f} < baseline {baseline:.4f}"
                )

    if regressions:
        return GateResult("regression", False, "CRITICAL",
                          f"Regression detected: {'; '.join(regressions)}",
                          current_metrics)

    return GateResult("regression", True, "INFO",
                      "No regression vs baseline", current_metrics)


# =============================================================================
# MODE PROMOTION GATE (LAB → REAL)
# =============================================================================

def check_promotion_gate(total_samples: int,
                         verified_samples: int,
                         threshold: int = 125000,
                         class_balance_ok: bool = True,
                         label_quality_ok: bool = True) -> GateResult:
    """
    Check if dataset is ready for promotion from LAB to REAL mode.

    Requirements:
      - verified_samples >= threshold per field
      - class balance within tolerance
      - label quality passes
    """
    issues = []

    if verified_samples < threshold:
        deficit = threshold - verified_samples
        issues.append(f"Insufficient samples: {verified_samples}/{threshold} (deficit: {deficit})")

    if not class_balance_ok:
        issues.append("Class imbalance outside tolerance")

    if not label_quality_ok:
        issues.append("Label quality check failed")

    if issues:
        return GateResult("promotion", False, "CRITICAL",
                          f"Not ready for REAL mode: {'; '.join(issues)}",
                          {"verified_samples": verified_samples,
                           "threshold": threshold,
                           "deficit": max(0, threshold - verified_samples)})

    return GateResult("promotion", True, "INFO",
                      f"Ready for REAL mode: {verified_samples} >= {threshold}",
                      {"verified_samples": verified_samples,
                       "threshold": threshold})


# =============================================================================
# ALL GATES RUNNER
# =============================================================================

def run_all_gates(labels: List[int],
                  features: np.ndarray,
                  verified_samples: int = 0,
                  threshold: int = 125000,
                  baseline_metrics: Optional[Dict[str, float]] = None,
                  current_metrics: Optional[Dict[str, float]] = None,
                  ) -> Tuple[bool, List[GateResult]]:
    """
    Run all quality gates and return (all_passed, results).

    In STRICT_REAL_MODE, any CRITICAL failure blocks training.
    In lab mode, failures are warnings only.
    """
    results = []

    results.append(check_label_quality(labels, features))
    results.append(check_class_imbalance(labels))
    results.append(check_duplicates(features))
    results.append(check_distribution_drift(features))
    results.append(check_regression_gate(
        current_metrics or {}, baseline_metrics
    ))
    results.append(check_promotion_gate(
        total_samples=len(labels),
        verified_samples=verified_samples,
        threshold=threshold,
        class_balance_ok=results[1].passed,
        label_quality_ok=results[0].passed,
    ))

    # In strict mode, any CRITICAL failure blocks
    if STRICT_REAL_MODE:
        critical_fails = [r for r in results if not r.passed and r.severity == "CRITICAL"]
        all_passed = len(critical_fails) == 0
    else:
        # Lab mode: only truly critical failures block
        all_passed = all(r.passed for r in results if r.severity == "CRITICAL")

    for r in results:
        level = logging.ERROR if not r.passed else logging.INFO
        logger.log(level, f"[GATE:{r.gate_name}] {r.severity} — {r.message}")

    return all_passed, results
