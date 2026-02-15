"""
Phase 1: Representation Space Audit for MODE-A Expansion.

Computes:
  1. Feature group distribution coverage
  2. Protocol diversity coverage
  3. DOM topology diversity coverage
  4. API schema diversity coverage
  5. Auth flow state graph diversity
  6. Duplicate rate (FNV-1a)
  7. Shortcut correlation matrix
  8. Entropy per feature group
  9. KL divergence across sample groups

Flags saturation risk if:
  - duplicate_rate > 5%
  - interaction dominance > 40%
  - KL divergence < 0.05 between groups
"""
import sys
import os
import json
import math
import struct
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np


# =============================================================================
# FNV-1a HASH (64-bit)
# =============================================================================

FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = (1 << 64) - 1


def fnv1a_hash(data: bytes) -> int:
    """FNV-1a 64-bit hash."""
    h = FNV_OFFSET
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & FNV_MASK
    return h


def feature_vector_hash(vec: np.ndarray) -> int:
    """Hash a feature vector using FNV-1a."""
    return fnv1a_hash(vec.astype(np.float32).tobytes())


# =============================================================================
# FEATURE GROUP DEFINITIONS
# =============================================================================

FEATURE_GROUPS = {
    "signal": (0, 64),
    "response": (64, 128),
    "interaction": (128, 192),
    "noise": (192, 256),
}

PROTOCOL_DIMS = (0, 32)      # HTTP method/status encoded in first signal dims
DOM_DIMS = (32, 64)           # DOM topology in remaining signal dims
API_DIMS = (64, 96)           # API schema in first response dims
AUTH_DIMS = (96, 128)         # Auth flow in remaining response dims


# =============================================================================
# AUDIT RESULT
# =============================================================================

@dataclass
class RepresentationAuditResult:
    """Full representation space audit result."""
    passed: bool = True
    saturation_risks: List[str] = field(default_factory=list)
    feature_group_coverage: Dict[str, dict] = field(default_factory=dict)
    protocol_diversity: Dict[str, float] = field(default_factory=dict)
    dom_diversity: Dict[str, float] = field(default_factory=dict)
    api_diversity: Dict[str, float] = field(default_factory=dict)
    auth_diversity: Dict[str, float] = field(default_factory=dict)
    duplicate_rate: float = 0.0
    shortcut_correlation: Dict[str, float] = field(default_factory=dict)
    entropy_per_group: Dict[str, float] = field(default_factory=dict)
    kl_divergence: Dict[str, float] = field(default_factory=dict)
    interaction_dominance: float = 0.0
    timestamp: str = ""

    def to_dict(self):
        return asdict(self)


# =============================================================================
# ENTROPY CALCULATION
# =============================================================================

def compute_entropy(values: np.ndarray, n_bins: int = 50) -> float:
    """Shannon entropy of a 1D distribution (binned)."""
    hist, _ = np.histogram(values, bins=n_bins, density=True)
    hist = hist[hist > 0]
    bin_width = (values.max() - values.min() + 1e-10) / n_bins
    probs = hist * bin_width
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs + 1e-10)))


def compute_kl_divergence(p: np.ndarray, q: np.ndarray,
                          n_bins: int = 50, eps: float = 1e-10) -> float:
    """KL(P || Q) with epsilon smoothing."""
    all_vals = np.concatenate([p, q])
    bins = np.linspace(all_vals.min(), all_vals.max(), n_bins + 1)

    p_hist, _ = np.histogram(p, bins=bins, density=False)
    q_hist, _ = np.histogram(q, bins=bins, density=False)

    p_hist = (p_hist + eps) / (p_hist.sum() + eps * n_bins)
    q_hist = (q_hist + eps) / (q_hist.sum() + eps * n_bins)

    return float(np.sum(p_hist * np.log(p_hist / q_hist)))


# =============================================================================
# DIVERSITY METRICS
# =============================================================================

def compute_diversity_metrics(features: np.ndarray,
                              dim_start: int, dim_end: int) -> dict:
    """Compute diversity metrics for a feature subspace."""
    sub = features[:, dim_start:dim_end]

    # Unique value coverage
    n_unique_per_dim = np.array([len(np.unique(np.round(sub[:, d], 4)))
                                  for d in range(sub.shape[1])])

    # Variance per dim
    var_per_dim = np.var(sub, axis=0)

    # Mean pairwise distance (sample 500 pairs for speed)
    rng = np.random.RandomState(42)
    n_pairs = min(500, len(sub) * (len(sub) - 1) // 2)
    dists = []
    for _ in range(n_pairs):
        i, j = rng.choice(len(sub), 2, replace=False)
        dists.append(float(np.linalg.norm(sub[i] - sub[j])))

    return {
        "mean_unique_values_per_dim": float(np.mean(n_unique_per_dim)),
        "mean_variance": float(np.mean(var_per_dim)),
        "min_variance": float(np.min(var_per_dim)),
        "max_variance": float(np.max(var_per_dim)),
        "mean_pairwise_distance": float(np.mean(dists)) if dists else 0.0,
        "std_pairwise_distance": float(np.std(dists)) if dists else 0.0,
        "active_dims": int(np.sum(var_per_dim > 1e-6)),
        "total_dims": int(dim_end - dim_start),
    }


# =============================================================================
# MAIN AUDIT
# =============================================================================

def run_representation_audit(features: np.ndarray,
                              labels: np.ndarray) -> RepresentationAuditResult:
    """
    Run full representation space audit.

    Args:
        features: (N, 256) feature matrix
        labels: (N,) label vector

    Returns:
        RepresentationAuditResult
    """
    result = RepresentationAuditResult()
    result.timestamp = datetime.now(timezone.utc).isoformat()
    N, D = features.shape

    # -----------------------------------------------------------------
    # 1. Feature group distribution coverage
    # -----------------------------------------------------------------
    for group_name, (start, end) in FEATURE_GROUPS.items():
        sub = features[:, start:end]
        var_ratio = float(np.sum(np.var(sub, axis=0)) /
                          (np.sum(np.var(features, axis=0)) + 1e-10))
        result.feature_group_coverage[group_name] = {
            "variance_ratio": round(var_ratio, 4),
            "mean": round(float(np.mean(sub)), 4),
            "std": round(float(np.std(sub)), 4),
            "min": round(float(np.min(sub)), 4),
            "max": round(float(np.max(sub)), 4),
        }

    # -----------------------------------------------------------------
    # 2-5. Protocol / DOM / API / Auth diversity
    # -----------------------------------------------------------------
    result.protocol_diversity = compute_diversity_metrics(
        features, *PROTOCOL_DIMS)
    result.dom_diversity = compute_diversity_metrics(
        features, *DOM_DIMS)
    result.api_diversity = compute_diversity_metrics(
        features, *API_DIMS)
    result.auth_diversity = compute_diversity_metrics(
        features, *AUTH_DIMS)

    # -----------------------------------------------------------------
    # 6. Duplicate rate (FNV-1a)
    # -----------------------------------------------------------------
    hashes = set()
    n_dupes = 0
    for i in range(N):
        h = feature_vector_hash(features[i])
        if h in hashes:
            n_dupes += 1
        else:
            hashes.add(h)
    result.duplicate_rate = round(n_dupes / N, 4)

    # -----------------------------------------------------------------
    # 7. Shortcut correlation matrix
    # -----------------------------------------------------------------
    for group_name, (start, end) in FEATURE_GROUPS.items():
        group_mean = np.mean(features[:, start:end], axis=1)
        corr = float(np.corrcoef(group_mean, labels)[0, 1])
        result.shortcut_correlation[group_name] = round(corr, 4)

    # -----------------------------------------------------------------
    # 8. Entropy per feature group
    # -----------------------------------------------------------------
    for group_name, (start, end) in FEATURE_GROUPS.items():
        group_flat = features[:, start:end].flatten()
        result.entropy_per_group[group_name] = round(
            compute_entropy(group_flat), 4)

    # -----------------------------------------------------------------
    # 9. KL divergence across sample groups
    # -----------------------------------------------------------------
    pos_mask = labels == 1
    neg_mask = labels == 0

    for group_name, (start, end) in FEATURE_GROUPS.items():
        pos_flat = features[pos_mask][:, start:end].flatten()
        neg_flat = features[neg_mask][:, start:end].flatten()
        kl = compute_kl_divergence(pos_flat, neg_flat)
        result.kl_divergence[f"{group_name}_pos_vs_neg"] = round(kl, 6)

    # Edge vs normal KL
    edge_mask = np.arange(N) < int(N * 0.10)
    normal_mask = ~edge_mask
    edge_flat = features[edge_mask].flatten()
    normal_flat = features[normal_mask].flatten()
    result.kl_divergence["edge_vs_normal"] = round(
        compute_kl_divergence(edge_flat, normal_flat), 6)

    # -----------------------------------------------------------------
    # Interaction dominance
    # -----------------------------------------------------------------
    i_start, i_end = FEATURE_GROUPS["interaction"]
    interaction_var = float(np.sum(np.var(features[:, i_start:i_end], axis=0)))
    total_var = float(np.sum(np.var(features, axis=0)) + 1e-10)
    result.interaction_dominance = round(interaction_var / total_var, 4)

    # -----------------------------------------------------------------
    # Saturation risk flags
    # -----------------------------------------------------------------
    if result.duplicate_rate > 0.05:
        result.saturation_risks.append(
            f"DUPLICATE_RATE={result.duplicate_rate:.2%} > 5%")
        result.passed = False

    if result.interaction_dominance > 0.40:
        result.saturation_risks.append(
            f"INTERACTION_DOMINANCE={result.interaction_dominance:.2%} > 40%")
        result.passed = False

    for key, val in result.kl_divergence.items():
        if val < 0.05:
            result.saturation_risks.append(
                f"LOW_KL_DIVERGENCE: {key}={val:.6f} < 0.05")
            result.passed = False

    return result


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import (
        ScaledDatasetGenerator, DatasetConfig,
    )
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset

    print("=" * 60)
    print("REPRESENTATION SPACE AUDIT — PHASE 1")
    print("=" * 60)

    # Load dataset
    config = DatasetConfig(total_samples=20000)
    dataset = RealTrainingDataset(config=config, seed=42)
    stats = dataset.get_statistics()
    print(f"\nDataset: {stats['total']} samples, "
          f"{stats['feature_dim']}D features")

    # Extract features and labels
    features = np.array([dataset[i][0].numpy() for i in range(len(dataset))])
    labels = np.array([dataset[i][1].item() for i in range(len(dataset))])

    print(f"Features shape: {features.shape}")
    print(f"Labels shape: {labels.shape}")
    print(f"Positive ratio: {np.mean(labels):.4f}")

    # Run audit
    result = run_representation_audit(features, labels)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"AUDIT RESULT: {'PASS' if result.passed else 'FAIL — SATURATION RISK'}")
    print(f"{'=' * 60}")

    print(f"\n--- Feature Group Coverage ---")
    for grp, info in result.feature_group_coverage.items():
        print(f"  {grp:15s}: var_ratio={info['variance_ratio']:.4f}  "
              f"mean={info['mean']:.4f}  std={info['std']:.4f}")

    print(f"\n--- Diversity ---")
    for name, div in [("Protocol", result.protocol_diversity),
                       ("DOM", result.dom_diversity),
                       ("API", result.api_diversity),
                       ("Auth", result.auth_diversity)]:
        print(f"  {name:10s}: unique={div['mean_unique_values_per_dim']:.0f}  "
              f"var={div['mean_variance']:.4f}  "
              f"dist={div['mean_pairwise_distance']:.4f}  "
              f"active={div['active_dims']}/{div['total_dims']}")

    print(f"\n--- Duplicate Rate: {result.duplicate_rate:.2%} ---")

    print(f"\n--- Shortcut Correlation ---")
    for grp, corr in result.shortcut_correlation.items():
        flag = " [!] HIGH" if abs(corr) > 0.7 else ""
        print(f"  {grp:15s}: r={corr:.4f}{flag}")

    print(f"\n--- Entropy per Group ---")
    for grp, ent in result.entropy_per_group.items():
        print(f"  {grp:15s}: {ent:.4f} bits")

    print(f"\n--- KL Divergence ---")
    for key, kl in result.kl_divergence.items():
        flag = " [!] LOW" if kl < 0.05 else ""
        print(f"  {key:30s}: {kl:.6f}{flag}")

    print(f"\n--- Interaction Dominance: {result.interaction_dominance:.2%} ---")

    if result.saturation_risks:
        print(f"\n{'!' * 60}")
        print("SATURATION RISKS:")
        for risk in result.saturation_risks:
            print(f"  [!] {risk}")
        print(f"{'!' * 60}")

    # Save report
    report_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'representation_audit.json')

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(result.to_dict(), f, indent=2)

    print(f"\nReport saved to: {report_path}")
    sys.exit(0 if result.passed else 1)
