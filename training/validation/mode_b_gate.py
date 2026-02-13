"""
Phase 9: Final MODE-B Gate Decision.

Runs ALL phases (1-8) and produces consolidated gate report.
If ANY phase fails, MODE-B remains LOCKED.
If ALL pass, MODE-B is allowed in SHADOW-ONLY mode.
"""
import sys, os, json, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def run_all_gates():
    """Run all 9 phases and produce gate decision."""
    print("=" * 70)
    print("  G38 MODE-B GATE — FULL VALIDATION PROTOCOL")
    print("=" * 70)
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    # Load dataset once
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    import numpy as np
    
    print("[INIT] Loading dataset...")
    config = DatasetConfig(total_samples=18000)
    dataset = RealTrainingDataset(config=config)
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()
    edge_mask = np.array([s.is_edge_case for s in dataset.samples], dtype=bool)
    print(f"[INIT] Dataset: {len(labels)} samples, {features.shape[1]} dims")
    print()
    
    gate_results = {}
    reports = {}
    report_dir = os.path.join(os.path.dirname(__file__), '..', '..', 
                              'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    
    # ===== PHASE 1: Data Audit =====
    print("[PHASE 1] Data Validation Audit...")
    t0 = time.time()
    from training.validation.data_audit import run_data_audit, generate_audit_report
    p1 = run_data_audit(features, labels, edge_mask)
    reports["phase1"] = generate_audit_report(p1)
    gate_results["Data Audit"] = p1.passed
    print(f"  -> {'PASS' if p1.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p1.passed:
        for f in p1.failures:
            print(f"     {f}")
    
    # ===== PHASE 2: Cross Validation =====
    print("[PHASE 2] 5-Fold Cross Validation...")
    t0 = time.time()
    from training.validation.cross_validation import run_cross_validation, generate_cv_report
    p2 = run_cross_validation(features, labels, n_folds=5, epochs=15)
    reports["phase2"] = generate_cv_report(p2)
    gate_results["Cross Validation"] = p2.passed
    print(f"  -> {'PASS' if p2.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p2.passed:
        for f in p2.failures:
            print(f"     {f}")
    
    # ===== PHASE 3: Stress Test =====
    print("[PHASE 3] Generalization Stress Test...")
    t0 = time.time()
    from training.validation.stress_test import run_stress_tests, generate_stress_report
    p3 = run_stress_tests(features, labels)
    reports["phase3"] = generate_stress_report(p3)
    gate_results["Stress Test"] = p3.passed
    print(f"  -> {'PASS' if p3.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p3.passed:
        for f in p3.failures:
            print(f"     {f}")
    
    # ===== PHASE 4: Calibration =====
    print("[PHASE 4] Calibration Proof...")
    t0 = time.time()
    from training.validation.calibration_report import run_calibration, generate_calibration_report
    p4 = run_calibration(features, labels)
    reports["phase4"] = generate_calibration_report(p4)
    gate_results["Calibration"] = p4.passed
    print(f"  -> {'PASS' if p4.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p4.passed:
        for f in p4.failures:
            print(f"     {f}")
    
    # ===== PHASE 5: Rare Class =====
    print("[PHASE 5] Rare Class Protection...")
    t0 = time.time()
    from training.validation.rare_class_protection import run_rare_class_test, generate_rare_report
    p5 = run_rare_class_test(features, labels)
    reports["phase5"] = generate_rare_report(p5)
    gate_results["Rare Class"] = p5.passed
    print(f"  -> {'PASS' if p5.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p5.passed:
        for f in p5.failures:
            print(f"     {f}")
    
    # ===== PHASE 6: Drift Simulation =====
    print("[PHASE 6] Drift Simulation...")
    t0 = time.time()
    from training.validation.drift_simulation import run_drift_simulation, generate_drift_report
    p6 = run_drift_simulation(features, labels)
    reports["phase6"] = generate_drift_report(p6)
    gate_results["Drift Simulation"] = p6.passed
    print(f"  -> {'PASS' if p6.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p6.passed:
        for f in p6.failures:
            print(f"     {f}")
    
    # ===== PHASE 7: Shadow Mode =====
    print("[PHASE 7] Shadow Mode Simulation...")
    t0 = time.time()
    from training.validation.shadow_mode_simulation import run_shadow_mode, generate_shadow_report
    p7 = run_shadow_mode(features, labels, n_decisions=1000)
    reports["phase7"] = generate_shadow_report(p7)
    gate_results["Shadow Mode"] = p7.passed
    print(f"  -> {'PASS' if p7.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p7.passed:
        for f in p7.failures:
            print(f"     {f}")
    
    # ===== PHASE 8: Governance =====
    print("[PHASE 8] Governance Integrity...")
    t0 = time.time()
    from training.validation.governance_check import run_governance_check, generate_governance_report
    p8 = run_governance_check()
    reports["phase8"] = generate_governance_report(p8)
    gate_results["Governance Integrity"] = p8.passed
    print(f"  -> {'PASS' if p8.passed else 'FAIL'} ({time.time()-t0:.1f}s)")
    if not p8.passed:
        for f in p8.failures:
            print(f"     {f}")
    
    # ===== PHASE 9: Final Decision =====
    print()
    all_pass = all(gate_results.values())
    
    # Save consolidated report
    consolidated = [
        "=" * 70,
        "  G38 MODE-B GATE -- CONSOLIDATED DECISION REPORT",
        "=" * 70,
        f"  Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "  GATE STATUS TABLE:",
        f"  {'Phase':<25} {'Result':>8}",
        "  " + "-" * 35,
    ]
    for name, passed in gate_results.items():
        consolidated.append(f"  {name:<25} {'PASS' if passed else 'FAIL':>8}")
    
    n_pass = sum(1 for v in gate_results.values() if v)
    n_total = len(gate_results)
    
    consolidated += [
        "  " + "-" * 35,
        f"  Total: {n_pass}/{n_total} gates passed",
        "",
        "=" * 70,
    ]
    
    if all_pass:
        consolidated += [
            "  DECISION: MODE-B ALLOWED (SHADOW-ONLY)",
            "",
            "  CONDITIONS:",
            "    - No authority unlocked",
            "    - No decision capability granted",
            "    - No severity labeling",
            "    - No submission logic",
            "    - No exploit reasoning",
            "    - Shadow-only proof classification readiness",
        ]
    else:
        consolidated += [
            "  DECISION: MODE-B REMAINS LOCKED",
            "",
            "  REASON: One or more validation gates failed.",
            "  ACTION: Fix failures and re-run validation.",
        ]
    
    consolidated += ["", "=" * 70]
    consolidated_text = "\n".join(consolidated)
    
    print(consolidated_text)
    
    # Save all reports
    with open(os.path.join(report_dir, 'phase9_gate_decision.txt'), 'w', encoding='utf-8') as f:
        f.write(consolidated_text)
    
    for phase_name, report_text in reports.items():
        with open(os.path.join(report_dir, f'{phase_name}_report.txt'), 'w', encoding='utf-8') as f:
            f.write(report_text)
    
    # Save JSON summary
    json_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "all_passed": all_pass,
        "gates": {k: v for k, v in gate_results.items()},
        "decision": "SHADOW_ONLY" if all_pass else "LOCKED",
    }
    with open(os.path.join(report_dir, 'phase9_gate_decision.json'), 'w', encoding='utf-8') as f:
        json.dump(json_summary, f, indent=2)
    
    print(f"\nReports saved to: {report_dir}")
    return all_pass


if __name__ == "__main__":
    result = run_all_gates()
    sys.exit(0 if result else 1)
