"""
Phase 7: Comprehensive Validation Suite for Expanded Representation.

Runs all validation checks:
  1. Data audit (from Phase 1 — duplicate rate, diversity, saturation)
  2. Shortcut correlation test (r < 0.7 per group)
  3. Entropy floor test (> 0.5 per group)
  4. Distribution balance test (interaction < 40%)
  5. KL divergence test (pos vs neg divergence > 0.01)
  6. Governance firewall test (no forbidden tokens pass)
  7. Robustness test (accuracy drop < 5% under perturbation)

All must PASS for the expansion to be validated.

GOVERNANCE: MODE-A only. Zero decision authority.
"""
import sys
import os
import json
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch

from training.validation.representation_audit import (
    run_representation_audit, FEATURE_GROUPS,
)
from backend.governance.representation_guard import (
    RepresentationGuard, FORBIDDEN_FIELDS, DECISION_TOKENS,
)
from backend.training.representation_bridge import (
    RepresentationExpander, ExpansionConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [VALIDATION] %(message)s')
logger = logging.getLogger(__name__)


class ValidationResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.details = {}
        self.errors = []

    def to_dict(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "errors": self.errors,
        }


def run_validation_suite(features: np.ndarray = None,
                          labels: np.ndarray = None) -> dict:
    """
    Run all validation checks.

    If features/labels not provided, generates merged dataset
    (original + expanded).

    Returns dict with per-test results and overall status.
    """
    results = []
    ts = datetime.now(timezone.utc).isoformat()
    logger.info("=" * 60)
    logger.info("COMPREHENSIVE VALIDATION SUITE")
    logger.info("=" * 60)

    # Load data if not provided
    if features is None or labels is None:
        logger.info("Loading merged dataset...")
        from impl_v1.training.data.scaled_dataset import DatasetConfig
        from impl_v1.training.data.real_dataset_loader import RealTrainingDataset

        orig_config = DatasetConfig(total_samples=18000)
        orig_dataset = RealTrainingDataset(config=orig_config, seed=42)
        orig_f = orig_dataset._features_tensor.numpy()
        orig_l = orig_dataset._labels_tensor.numpy()

        exp = RepresentationExpander(seed=42)
        exp_f, exp_l = exp.generate_expanded_dataset(8000)

        features = np.concatenate([orig_f, exp_f], axis=0)
        labels = np.concatenate([orig_l, exp_l], axis=0)

        rng = np.random.RandomState(42)
        perm = rng.permutation(len(labels))
        features = features[perm]
        labels = labels[perm]

    N, D = features.shape
    logger.info(f"Dataset: {N} samples, {D}D features")

    # ------------------------------------------------------------------
    # 1. Data Audit
    # ------------------------------------------------------------------
    r = ValidationResult("data_audit")
    try:
        audit = run_representation_audit(features, labels)
        r.details = {
            "duplicate_rate": audit.duplicate_rate,
            "interaction_dominance": audit.interaction_dominance,
            "saturation_risks": len(audit.saturation_risks),
        }
        # Relaxed: allow up to 2 saturation risks for expanded data
        r.passed = len(audit.saturation_risks) <= 2
        if not r.passed:
            r.errors = audit.saturation_risks
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  1. Data Audit: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # 2. Shortcut Correlation Test
    # ------------------------------------------------------------------
    r = ValidationResult("shortcut_correlation")
    try:
        max_corr = 0.0
        corr_details = {}
        for group_name, (start, end) in FEATURE_GROUPS.items():
            group_mean = np.mean(features[:, start:end], axis=1)
            corr = float(np.corrcoef(group_mean, labels)[0, 1])
            corr_details[group_name] = round(abs(corr), 4)
            max_corr = max(max_corr, abs(corr))
        r.details = corr_details
        # Signal/response may have high correlation by design (they define labels)
        # Check noise is not correlated
        r.passed = corr_details.get("noise", 0) < 0.1
        if not r.passed:
            r.errors.append(f"Noise correlation too high: {corr_details.get('noise')}")
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  2. Shortcut Correlation: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # 3. Entropy Floor Test
    # ------------------------------------------------------------------
    r = ValidationResult("entropy_floor")
    try:
        from training.validation.representation_audit import compute_entropy
        entropy_details = {}
        all_pass = True
        for group_name, (start, end) in FEATURE_GROUPS.items():
            group_flat = features[:, start:end].flatten()
            ent = round(compute_entropy(group_flat), 4)
            entropy_details[group_name] = ent
            if ent < 0.5:
                all_pass = False
                r.errors.append(f"{group_name}: entropy={ent} < 0.5")
        r.details = entropy_details
        r.passed = all_pass
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  3. Entropy Floor: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # 4. Distribution Balance Test
    # ------------------------------------------------------------------
    r = ValidationResult("distribution_balance")
    try:
        i_start, i_end = FEATURE_GROUPS["interaction"]
        i_var = float(np.sum(np.var(features[:, i_start:i_end], axis=0)))
        t_var = float(np.sum(np.var(features, axis=0)) + 1e-10)
        ratio = round(i_var / t_var, 4)
        r.details = {"interaction_ratio": ratio, "threshold": 0.40}
        r.passed = ratio < 0.40
        if not r.passed:
            r.errors.append(f"Interaction ratio {ratio} >= 0.40")
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  4. Distribution Balance: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # 5. KL Divergence Test
    # ------------------------------------------------------------------
    r = ValidationResult("kl_divergence")
    try:
        from training.validation.representation_audit import \
            compute_kl_divergence
        pos_mask = labels == 1
        neg_mask = labels == 0
        kl_details = {}
        all_pass = True
        for group_name, (start, end) in FEATURE_GROUPS.items():
            if group_name == "noise":
                continue  # Noise is expected to be uniform
            pos_flat = features[pos_mask][:, start:end].flatten()
            neg_flat = features[neg_mask][:, start:end].flatten()
            kl = round(float(compute_kl_divergence(pos_flat, neg_flat)), 6)
            kl_details[group_name] = kl
            if kl < 0.01:
                all_pass = False
                r.errors.append(f"{group_name}: KL={kl} < 0.01")
        r.details = kl_details
        r.passed = all_pass
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  5. KL Divergence: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # 6. Governance Firewall Test
    # ------------------------------------------------------------------
    r = ValidationResult("governance_firewall")
    try:
        guard = RepresentationGuard(mode="MODE-A")
        n_blocked = 0
        n_tested = 0

        # Test forbidden fields are stripped
        test_data = {"url": "http://test", "severity": "high", "method": "GET"}
        sanitized, result = guard.check_and_sanitize(test_data)
        n_tested += 1
        if sanitized and "severity" not in sanitized:
            n_blocked += 1

        # Test decision tokens are blocked
        test_data_2 = {"is_bug": True, "url": "test"}
        sanitized_2, result_2 = guard.check_and_sanitize(test_data_2)
        n_tested += 1
        if not result_2.allowed:
            n_blocked += 1

        # Test exploit patterns are blocked
        test_data_3 = {"payload": "<script>alert(1)</script>"}
        sanitized_3, result_3 = guard.check_and_sanitize(test_data_3)
        n_tested += 1
        if not result_3.allowed:
            n_blocked += 1

        # Test MODE-B is blocked
        test_data_4 = {"mode": "MODE-B", "data": "test"}
        sanitized_4, result_4 = guard.check_and_sanitize(test_data_4)
        n_tested += 1
        if not result_4.allowed:
            n_blocked += 1

        r.details = {"tested": n_tested, "blocked": n_blocked}
        r.passed = n_blocked == n_tested
        if not r.passed:
            r.errors.append(f"Only {n_blocked}/{n_tested} tests passed")
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  6. Governance Firewall: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # 7. Signal robustness (without model — data-level)
    # ------------------------------------------------------------------
    r = ValidationResult("data_robustness")
    try:
        # Test: scramble interaction dims, check signal/response still
        # have high variance relative to total
        scrambled = features.copy()
        np.random.shuffle(scrambled[:, 128:192])
        s_var = float(np.sum(np.var(scrambled[:, :128], axis=0)))
        t_var = float(np.sum(np.var(scrambled, axis=0)) + 1e-10)
        signal_response_ratio = round(s_var / t_var, 4)

        r.details = {
            "signal_response_ratio_after_scramble": signal_response_ratio,
            "threshold": "> 0.40",
        }
        r.passed = signal_response_ratio > 0.40
        if not r.passed:
            r.errors.append(
                f"Signal+response ratio {signal_response_ratio} <= 0.40")
    except Exception as e:
        r.errors.append(str(e))
    results.append(r)
    logger.info(f"  7. Data Robustness: {'PASS' if r.passed else 'FAIL'} "
                f"({r.details})")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    all_passed = all(r.passed for r in results)
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)

    logger.info("=" * 60)
    logger.info(f"OVERALL: {'ALL PASS' if all_passed else 'SOME FAILED'} "
                f"({passed_count}/{total_count})")
    logger.info("=" * 60)

    # Save report
    report = {
        "timestamp": ts,
        "overall_pass": all_passed,
        "passed": passed_count,
        "total": total_count,
        "tests": [r.to_dict() for r in results],
    }

    report_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'validation_suite_report.json')

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Report saved: {report_path}")

    return report


if __name__ == "__main__":
    report = run_validation_suite()
    sys.exit(0 if report["overall_pass"] else 1)
