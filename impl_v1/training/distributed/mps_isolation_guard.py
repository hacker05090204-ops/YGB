"""
mps_isolation_guard.py — MPS Isolation Guarantee (Phase 8)

MPS shard workers:
  - Cannot directly modify global weights
  - Send delta only
  - Authority validates:
      delta_norm
      validation_improvement
      loss_stability
  - Reject outlier deltas

Builds on existing mps_shard_worker.py.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# THRESHOLDS
# =============================================================================

DEFAULT_MAX_DELTA_NORM = 10.0
DEFAULT_MAX_LOSS_INCREASE = 0.50     # 50% increase = diverged
DEFAULT_MIN_VAL_IMPROVEMENT = -0.02  # Allow up to 2% val acc drop
DEFAULT_OUTLIER_SIGMA = 3.0          # Z-score for outlier detection


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class MPSDeltaSubmission:
    """Delta submission from an MPS worker."""
    node_id: str
    delta: dict                      # param_name -> delta_tensor
    delta_norm: float
    loss_before: float
    loss_after: float
    val_acc_before: float
    val_acc_after: float
    epoch: int


@dataclass
class MPSValidationResult:
    """Authority's validation of an MPS delta."""
    node_id: str
    accepted: bool
    delta_norm_ok: bool
    loss_stability_ok: bool
    val_improvement_ok: bool
    outlier_ok: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class MPSIsolationReport:
    """Report on all MPS delta validations for one epoch."""
    epoch: int
    total_submissions: int
    accepted: int
    rejected: int
    validated: List[MPSValidationResult] = field(default_factory=list)
    rejected_nodes: List[str] = field(default_factory=list)


# =============================================================================
# DELTA VALIDATION
# =============================================================================

def validate_mps_delta(
    submission: MPSDeltaSubmission,
    max_delta_norm: float = DEFAULT_MAX_DELTA_NORM,
    max_loss_increase: float = DEFAULT_MAX_LOSS_INCREASE,
    min_val_improvement: float = DEFAULT_MIN_VAL_IMPROVEMENT,
) -> MPSValidationResult:
    """Validate a single MPS delta submission.

    Checks:
      1. delta_norm <= max threshold
      2. loss didn't diverge (loss_after <= loss_before * (1 + max_loss_increase))
      3. validation accuracy didn't collapse

    Args:
        submission: The MPS delta to validate.
        max_delta_norm: Max allowed L2 norm.
        max_loss_increase: Max fractional loss increase.
        min_val_improvement: Min allowed change in val accuracy (negative = slight drop ok).

    Returns:
        MPSValidationResult.
    """
    errors = []

    # 1. Delta norm
    norm_ok = submission.delta_norm <= max_delta_norm
    if not norm_ok:
        errors.append(
            f"Delta norm {submission.delta_norm:.4f} > max {max_delta_norm}"
        )

    # 2. Loss stability
    loss_ok = True
    if submission.loss_before > 0:
        max_allowed = submission.loss_before * (1.0 + max_loss_increase)
        if submission.loss_after > max_allowed:
            loss_ok = False
            errors.append(
                f"Loss diverged: {submission.loss_before:.4f} → "
                f"{submission.loss_after:.4f} (max allowed {max_allowed:.4f})"
            )

    # 3. Validation improvement
    val_ok = True
    val_change = submission.val_acc_after - submission.val_acc_before
    if val_change < min_val_improvement:
        val_ok = False
        errors.append(
            f"Val accuracy dropped: {submission.val_acc_before:.4f} → "
            f"{submission.val_acc_after:.4f} (change={val_change:.4f} "
            f"< min {min_val_improvement})"
        )

    accepted = norm_ok and loss_ok and val_ok

    result = MPSValidationResult(
        node_id=submission.node_id,
        accepted=accepted,
        delta_norm_ok=norm_ok,
        loss_stability_ok=loss_ok,
        val_improvement_ok=val_ok,
        outlier_ok=True,  # Set by batch outlier check
        errors=errors,
    )

    if accepted:
        logger.info(
            f"[MPS_GUARD] Delta ACCEPTED from {submission.node_id[:16]}...: "
            f"norm={submission.delta_norm:.4f}, "
            f"loss={submission.loss_before:.4f}→{submission.loss_after:.4f}"
        )
    else:
        logger.error(
            f"[MPS_GUARD] Delta REJECTED from {submission.node_id[:16]}...: "
            f"{errors}"
        )

    return result


# =============================================================================
# OUTLIER DETECTION
# =============================================================================

def detect_outlier_deltas(
    submissions: List[MPSDeltaSubmission],
    sigma_threshold: float = DEFAULT_OUTLIER_SIGMA,
) -> List[str]:
    """Detect outlier deltas using Z-score on delta norms.

    If a node's delta norm is > sigma_threshold standard deviations
    from the mean, it's flagged as an outlier.

    Args:
        submissions: All MPS delta submissions for one epoch.
        sigma_threshold: Z-score threshold.

    Returns:
        List of outlier node_ids.
    """
    if len(submissions) < 2:
        return []

    norms = [s.delta_norm for s in submissions]
    mean_norm = np.mean(norms)
    std_norm = np.std(norms)

    if std_norm < 1e-8:
        return []  # All identical

    outliers = []
    for s in submissions:
        z = abs(s.delta_norm - mean_norm) / std_norm
        if z > sigma_threshold:
            outliers.append(s.node_id)
            logger.warning(
                f"[MPS_GUARD] OUTLIER: {s.node_id[:16]}... "
                f"norm={s.delta_norm:.4f}, z={z:.2f} > {sigma_threshold}"
            )

    return outliers


# =============================================================================
# BATCH VALIDATION
# =============================================================================

def validate_all_mps_deltas(
    submissions: List[MPSDeltaSubmission],
    epoch: int,
    max_delta_norm: float = DEFAULT_MAX_DELTA_NORM,
    max_loss_increase: float = DEFAULT_MAX_LOSS_INCREASE,
    min_val_improvement: float = DEFAULT_MIN_VAL_IMPROVEMENT,
    sigma_threshold: float = DEFAULT_OUTLIER_SIGMA,
) -> MPSIsolationReport:
    """Validate all MPS delta submissions for one epoch.

    1. Validate each delta individually
    2. Run outlier detection across the batch
    3. Reject any outliers even if they passed individual checks

    Args:
        submissions: All MPS deltas.
        epoch: Epoch number.
        max_delta_norm: Max norm threshold.
        max_loss_increase: Max loss increase fraction.
        min_val_improvement: Min val accuracy change.
        sigma_threshold: Outlier Z-score threshold.

    Returns:
        MPSIsolationReport.
    """
    results = []
    rejected_nodes = []

    # Step 1: Individual validation
    for sub in submissions:
        r = validate_mps_delta(sub, max_delta_norm, max_loss_increase, min_val_improvement)
        results.append(r)
        if not r.accepted:
            rejected_nodes.append(sub.node_id)

    # Step 2: Outlier detection
    outliers = detect_outlier_deltas(submissions, sigma_threshold)
    for r in results:
        if r.node_id in outliers:
            r.outlier_ok = False
            r.accepted = False
            r.errors.append("Detected as outlier by Z-score")
            if r.node_id not in rejected_nodes:
                rejected_nodes.append(r.node_id)

    accepted_count = sum(1 for r in results if r.accepted)
    rejected_count = len(results) - accepted_count

    report = MPSIsolationReport(
        epoch=epoch,
        total_submissions=len(submissions),
        accepted=accepted_count,
        rejected=rejected_count,
        validated=results,
        rejected_nodes=rejected_nodes,
    )

    logger.info(
        f"[MPS_GUARD] Epoch {epoch}: "
        f"{accepted_count} accepted, {rejected_count} rejected "
        f"out of {len(submissions)} MPS deltas"
    )

    return report
