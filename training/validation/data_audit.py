"""
Phase 1: Data Validation Audit for MODE-B Gate.

Statistical audit of dataset composition, feature stability,
and label signal integrity. MODE-B MUST NOT unlock without
this audit passing.
"""
import sys
import os
import math
import json
import random
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np


@dataclass
class AuditResult:
    """Full data audit result."""
    passed: bool
    sections: Dict[str, dict] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "sections": self.sections,
            "warnings": self.warnings,
            "failures": self.failures,
            "timestamp": self.timestamp,
        }


def _compute_kl_divergence(p: np.ndarray, q: np.ndarray, eps: float = 1e-10) -> float:
    """KL(P || Q) with epsilon smoothing."""
    p = np.clip(p, eps, None)
    q = np.clip(q, eps, None)
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum(p * np.log(p / q)))


def _mutual_information(features: np.ndarray, labels: np.ndarray, n_bins: int = 20) -> float:
    """Estimate mutual information between features (1D) and binary labels."""
    # Discretize features
    feat_bins = np.digitize(features, np.linspace(features.min(), features.max(), n_bins))
    
    n = len(features)
    mi = 0.0
    for fb in range(1, n_bins + 1):
        for lb in [0, 1]:
            joint = np.sum((feat_bins == fb) & (labels == lb)) / n
            marginal_f = np.sum(feat_bins == fb) / n
            marginal_l = np.sum(labels == lb) / n
            if joint > 0 and marginal_f > 0 and marginal_l > 0:
                mi += joint * math.log2(joint / (marginal_f * marginal_l))
    return mi


def run_data_audit(features: np.ndarray, labels: np.ndarray,
                   edge_mask: np.ndarray = None) -> AuditResult:
    """
    Run full Phase 1 data validation audit.
    
    Args:
        features: (N, D) feature matrix
        labels: (N,) label vector (0 or 1)
        edge_mask: (N,) boolean mask for edge cases
    
    Returns:
        AuditResult with sections A, B, C
    """
    result = AuditResult(
        passed=True,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    warnings = []
    failures = []

    N, D = features.shape
    pos_mask = labels == 1
    neg_mask = labels == 0
    n_pos = int(pos_mask.sum())
    n_neg = int(neg_mask.sum())
    
    if edge_mask is None:
        edge_mask = np.zeros(N, dtype=bool)
    n_edge = int(edge_mask.sum())
    
    # =================================================================
    # SECTION A — Dataset Composition
    # =================================================================
    
    class_ratio = n_pos / max(n_neg, 1)
    edge_ratio = n_edge / max(N, 1)
    
    # Check class balance (should be roughly 50/50)
    if abs(class_ratio - 1.0) > 0.1:
        warnings.append(f"Class imbalance detected: ratio={class_ratio:.3f}")
    
    # Feature correlation with labels (per dimension)
    correlations = []
    for d in range(D):
        corr = np.corrcoef(features[:, d], labels)[0, 1]
        correlations.append(float(corr) if not np.isnan(corr) else 0.0)
    correlations = np.array(correlations)
    
    # Label leakage detection — any single feature with |corr| > 0.95
    max_corr_idx = int(np.argmax(np.abs(correlations)))
    max_corr_val = float(np.abs(correlations[max_corr_idx]))
    label_leakage = max_corr_val > 0.95
    if label_leakage:
        failures.append(
            f"LABEL LEAKAGE: Feature dim {max_corr_idx} has "
            f"|correlation|={max_corr_val:.4f} > 0.95 with label"
        )
    
    # Feature group correlations  
    group_corrs = {
        "signal_dims_0_63": float(np.mean(np.abs(correlations[0:64]))),
        "response_dims_64_127": float(np.mean(np.abs(correlations[64:128]))),
        "interaction_dims_128_191": float(np.mean(np.abs(correlations[128:192]))),
        "noise_dims_192_255": float(np.mean(np.abs(correlations[192:256]))),
    }
    
    # Noise dims should have near-zero correlation
    if group_corrs["noise_dims_192_255"] > 0.1:
        warnings.append(
            f"Noise dimensions have correlation {group_corrs['noise_dims_192_255']:.4f} "
            f"with labels (expected < 0.1)"
        )
    
    # Overlapping distribution boundary risk
    pos_signal_mean = float(features[pos_mask, 0:64].mean())
    neg_signal_mean = float(features[neg_mask, 0:64].mean())
    signal_gap = pos_signal_mean - neg_signal_mean
    
    overlap_risk = "LOW" if signal_gap > 0.2 else ("MEDIUM" if signal_gap > 0.1 else "HIGH")
    if overlap_risk == "HIGH":
        warnings.append(f"High overlap risk: signal gap = {signal_gap:.4f}")
    
    section_a = {
        "total_samples": N,
        "feature_dimensions": D,
        "positive_samples": n_pos,
        "negative_samples": n_neg,
        "class_ratio": round(class_ratio, 4),
        "edge_case_count": n_edge,
        "edge_case_ratio": round(edge_ratio, 4),
        "synthetic_ratio": 1.0,  # All data is generated
        "label_leakage_detected": label_leakage,
        "max_single_feature_correlation": round(max_corr_val, 4),
        "max_corr_feature_dim": max_corr_idx,
        "feature_group_correlations": group_corrs,
        "signal_gap_between_classes": round(signal_gap, 4),
        "overlap_risk": overlap_risk,
    }
    result.sections["A_dataset_composition"] = section_a
    
    # =================================================================
    # SECTION B — Feature Stability
    # =================================================================
    
    # Per-class statistics
    pos_mean = features[pos_mask].mean(axis=0)
    pos_std = features[pos_mask].std(axis=0)
    neg_mean = features[neg_mask].mean(axis=0)
    neg_std = features[neg_mask].std(axis=0)
    
    # Summary stats by feature group
    groups = [(0, 64, "signal"), (64, 128, "response"), 
              (128, 192, "interaction"), (192, 256, "noise")]
    
    group_stats = {}
    for start, end, name in groups:
        group_stats[name] = {
            "pos_mean": round(float(pos_mean[start:end].mean()), 4),
            "pos_std": round(float(pos_std[start:end].mean()), 4),
            "neg_mean": round(float(neg_mean[start:end].mean()), 4),
            "neg_std": round(float(neg_std[start:end].mean()), 4),
            "mean_diff": round(float((pos_mean[start:end] - neg_mean[start:end]).mean()), 4),
        }
    
    # KL divergence between classes (per feature group, using histograms)
    kl_divergences = {}
    for start, end, name in groups:
        pos_hist, _ = np.histogram(features[pos_mask, start:end].flatten(), bins=50, density=True)
        neg_hist, _ = np.histogram(features[neg_mask, start:end].flatten(), bins=50, density=True)
        kl = _compute_kl_divergence(pos_hist, neg_hist)
        kl_divergences[name] = round(kl, 4)
    
    # Controlled noise variance check
    noise_var = float(features[:, 192:256].var())
    noise_expected_var = 0.05**2  # Expected from gauss(0, 0.05)
    noise_var_ratio = noise_var / max(noise_expected_var, 1e-10)
    
    section_b = {
        "feature_group_statistics": group_stats,
        "kl_divergence_between_classes": kl_divergences,
        "noise_variance": round(noise_var, 6),
        "noise_expected_variance": round(noise_expected_var, 6),
        "noise_variance_ratio": round(noise_var_ratio, 4),
    }
    result.sections["B_feature_stability"] = section_b
    
    # =================================================================
    # SECTION C — Label Signal Integrity
    # =================================================================
    
    # Mutual information per feature group
    mi_scores = {}
    for start, end, name in groups:
        # Average MI across dims in group (sample a few dims for speed)
        dims_to_check = list(range(start, min(start + 8, end)))
        mi_vals = [_mutual_information(features[:, d], labels) for d in dims_to_check]
        mi_scores[name] = round(float(np.mean(mi_vals)), 4)
    
    # Top 10 strongest correlated features
    sorted_indices = np.argsort(np.abs(correlations))[::-1]
    top10 = []
    for idx in sorted_indices[:10]:
        top10.append({
            "dim": int(idx),
            "correlation": round(float(correlations[idx]), 4),
            "group": ("signal" if idx < 64 else 
                     "response" if idx < 128 else 
                     "interaction" if idx < 192 else "noise"),
        })
    
    # Single-feature dominance check
    # If top feature explains >80% more than 2nd feature → shortcut risk
    top_corrs = sorted(np.abs(correlations), reverse=True)
    dominance_gap = top_corrs[0] - top_corrs[1] if len(top_corrs) > 1 else 0
    single_feature_dominance = dominance_gap > 0.3
    if single_feature_dominance:
        warnings.append(
            f"Single-feature dominance: gap between top-1 and top-2 = {dominance_gap:.4f}"
        )
    
    # Shortcut learning check — are all signal from one group?
    top10_groups = [t["group"] for t in top10]
    unique_groups = set(top10_groups)
    shortcut_risk = len(unique_groups) == 1
    if shortcut_risk:
        failures.append(
            f"SHORTCUT RISK: All top-10 features from '{top10_groups[0]}' group"
        )
    
    section_c = {
        "mutual_information_by_group": mi_scores,
        "top_10_correlated_features": top10,
        "single_feature_dominance": single_feature_dominance,
        "dominance_gap": round(dominance_gap, 4),
        "shortcut_learning_risk": shortcut_risk,
        "unique_groups_in_top10": list(unique_groups),
    }
    result.sections["C_label_signal_integrity"] = section_c
    
    # =================================================================
    # FINAL VERDICT
    # =================================================================
    result.warnings = warnings
    result.failures = failures
    result.passed = len(failures) == 0
    
    return result


def generate_audit_report(result: AuditResult) -> str:
    """Generate human-readable audit report."""
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE — PHASE 1: DATA VALIDATION AUDIT",
        "=" * 70,
        f"  Timestamp: {result.timestamp}",
        f"  Verdict: {'✅ PASS' if result.passed else '❌ FAIL'}",
        "",
    ]
    
    # Section A
    a = result.sections.get("A_dataset_composition", {})
    lines += [
        "-" * 70,
        "  SECTION A — Dataset Composition",
        "-" * 70,
        f"  Total Samples:          {a.get('total_samples', 0):,}",
        f"  Feature Dimensions:     {a.get('feature_dimensions', 0)}",
        f"  Positive Samples:       {a.get('positive_samples', 0):,}",
        f"  Negative Samples:       {a.get('negative_samples', 0):,}",
        f"  Class Ratio (pos/neg):  {a.get('class_ratio', 0):.4f}",
        f"  Edge Case Count:        {a.get('edge_case_count', 0):,}",
        f"  Edge Case Ratio:        {a.get('edge_case_ratio', 0):.4f}",
        f"  Synthetic Ratio:        {a.get('synthetic_ratio', 0):.1%}",
        f"  Label Leakage:          {'⚠️  YES' if a.get('label_leakage_detected') else '✅ NO'}",
        f"  Max Feature Correlation: {a.get('max_single_feature_correlation', 0):.4f} (dim {a.get('max_corr_feature_dim', -1)})",
        f"  Signal Gap:             {a.get('signal_gap_between_classes', 0):.4f}",
        f"  Overlap Risk:           {a.get('overlap_risk', 'UNKNOWN')}",
        "",
        "  Feature Group Correlations with Label:",
    ]
    for name, val in a.get("feature_group_correlations", {}).items():
        lines.append(f"    {name:30s}: {val:.4f}")
    
    # Section B
    b = result.sections.get("B_feature_stability", {})
    lines += [
        "",
        "-" * 70,
        "  SECTION B — Feature Stability",
        "-" * 70,
    ]
    for gname, gstats in b.get("feature_group_statistics", {}).items():
        lines += [
            f"  [{gname.upper()}]",
            f"    Positive: mean={gstats['pos_mean']:.4f}, std={gstats['pos_std']:.4f}",
            f"    Negative: mean={gstats['neg_mean']:.4f}, std={gstats['neg_std']:.4f}",
            f"    Mean diff: {gstats['mean_diff']:.4f}",
        ]
    
    lines.append("")
    lines.append("  KL Divergence (Pos || Neg):")
    for name, kl in b.get("kl_divergence_between_classes", {}).items():
        lines.append(f"    {name:20s}: {kl:.4f}")
    
    lines += [
        f"  Noise Variance:         {b.get('noise_variance', 0):.6f}",
        f"  Expected Noise Var:     {b.get('noise_expected_variance', 0):.6f}",
        f"  Noise Var Ratio:        {b.get('noise_variance_ratio', 0):.4f}x",
    ]
    
    # Section C
    c = result.sections.get("C_label_signal_integrity", {})
    lines += [
        "",
        "-" * 70,
        "  SECTION C — Label Signal Integrity",
        "-" * 70,
    ]
    lines.append("  Mutual Information by Group:")
    for name, mi in c.get("mutual_information_by_group", {}).items():
        lines.append(f"    {name:20s}: {mi:.4f} bits")
    
    lines.append("")
    lines.append("  Top 10 Correlated Features:")
    for i, feat in enumerate(c.get("top_10_correlated_features", [])):
        lines.append(f"    #{i+1:2d}: dim={feat['dim']:3d} corr={feat['correlation']:+.4f} ({feat['group']})")
    
    lines += [
        f"",
        f"  Single-Feature Dominance: {'⚠️  YES' if c.get('single_feature_dominance') else '✅ NO'}",
        f"  Dominance Gap:           {c.get('dominance_gap', 0):.4f}",
        f"  Shortcut Learning Risk:  {'❌ YES' if c.get('shortcut_learning_risk') else '✅ NO'}",
        f"  Groups in Top-10:        {', '.join(c.get('unique_groups_in_top10', []))}",
    ]
    
    # Warnings & Failures
    if result.warnings:
        lines += ["", "-" * 70, "  WARNINGS", "-" * 70]
        for w in result.warnings:
            lines.append(f"  ⚠️  {w}")
    
    if result.failures:
        lines += ["", "-" * 70, "  FAILURES", "-" * 70]
        for f in result.failures:
            lines.append(f"  ❌ {f}")
    
    lines += [
        "",
        "=" * 70,
        f"  PHASE 1 VERDICT: {'✅ PASS — Data audit cleared' if result.passed else '❌ FAIL — MODE-B BLOCKED'}",
        "=" * 70,
    ]
    
    return "\n".join(lines)


if __name__ == "__main__":
    """Run standalone data audit."""
    from impl_v1.training.data.scaled_dataset import ScaledDatasetGenerator, DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    
    print("Loading dataset...")
    config = DatasetConfig(total_samples=18000)
    dataset = RealTrainingDataset(config=config)
    
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()
    
    # Build edge mask from samples
    edge_mask = np.array([s.is_edge_case for s in dataset.samples], dtype=bool)
    
    print(f"Dataset loaded: {len(labels)} samples, {features.shape[1]} features")
    print()
    
    result = run_data_audit(features, labels, edge_mask)
    report = generate_audit_report(result)
    print(report)
    
    # Save report
    report_path = os.path.join(os.path.dirname(__file__), '..', '..', 
                               'reports', 'g38_training', 'phase1_data_audit.txt')
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")
    
    # Save JSON
    json_path = report_path.replace('.txt', '.json')
    with open(json_path, 'w') as f:
        json.dump(result.to_dict(), f, indent=2)
    
    sys.exit(0 if result.passed else 1)
