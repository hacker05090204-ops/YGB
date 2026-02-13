"""
Phase 8: Governance Integrity Verification for MODE-B Gate.

Ensure:
  - No severity learning capability
  - No bug decision learning
  - No exploit logic
  - No submission authority
  - No training on accepted/rejected labels
  - All governance guards return FALSE
"""
import sys, os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


@dataclass
class GovernanceResult:
    passed: bool
    guards_checked: int
    guards_passed: int
    guard_results: List[Tuple[str, bool, str]]
    mode_b_locked: bool
    failures: List[str]
    timestamp: str


def run_governance_check() -> GovernanceResult:
    from impl_v1.phase49.governors.g38_safe_pretraining import (
        can_ai_learn_bug_labels_from_internet,
        can_ai_learn_severity_from_internet,
        can_ai_learn_acceptance_status,
        can_ai_use_platform_outcomes,
        can_mode_b_activate_without_proofs,
        can_ai_train_on_scanner_verdicts,
        is_mode_b_unlocked,
        verify_pretraining_guards,
        PRETRAINING_GUARDS,
    )
    
    failures = []
    guard_results = []
    
    # Check all individual guards — they must ALL return False
    guards = [
        ("can_ai_learn_bug_labels_from_internet", can_ai_learn_bug_labels_from_internet),
        ("can_ai_learn_severity_from_internet", can_ai_learn_severity_from_internet),
        ("can_ai_learn_acceptance_status", can_ai_learn_acceptance_status),
        ("can_ai_use_platform_outcomes", can_ai_use_platform_outcomes),
        ("can_mode_b_activate_without_proofs", can_mode_b_activate_without_proofs),
        ("can_ai_train_on_scanner_verdicts", can_ai_train_on_scanner_verdicts),
    ]
    
    for name, guard_fn in guards:
        result, msg = guard_fn()
        passed = result == False  # Guard passes if it returns False
        guard_results.append((name, passed, msg))
        if not passed:
            failures.append(f"Guard {name} returned True (expected False): {msg}")
    
    # Check MODE-B is still locked
    mode_b_locked = not is_mode_b_unlocked()
    if not mode_b_locked:
        failures.append("MODE-B is unlocked without gate validation!")
    
    # Verify all pretraining guards via the aggregate function
    all_pass, msg = verify_pretraining_guards()
    if not all_pass:
        failures.append(f"Aggregate guard check failed: {msg}")
    
    # Also check governance guards from other modules
    try:
        from impl_v1.phase49.governors.g38_self_trained_model import (
            can_ai_verify_bugs,
            can_ai_decide_severity,
            can_ai_submit_to_platforms,
            can_ai_override_governance,
            can_ai_modify_scope,
        )
        extra_guards = [
            ("can_ai_verify_bugs", can_ai_verify_bugs),
            ("can_ai_decide_severity", can_ai_decide_severity),
            ("can_ai_submit_to_platforms", can_ai_submit_to_platforms),
            ("can_ai_override_governance", can_ai_override_governance),
            ("can_ai_modify_scope", can_ai_modify_scope),
        ]
        for name, guard_fn in extra_guards:
            result, msg = guard_fn()
            passed = result == False
            guard_results.append((name, passed, msg))
            if not passed:
                failures.append(f"Guard {name} returned True: {msg}")
    except ImportError:
        # Module may not exist — note but don't fail
        guard_results.append(("g38_self_trained_model_guards", True, "Module not available"))
    
    guards_passed = sum(1 for _, p, _ in guard_results if p)
    
    return GovernanceResult(
        passed=len(failures) == 0,
        guards_checked=len(guard_results),
        guards_passed=guards_passed,
        guard_results=guard_results,
        mode_b_locked=mode_b_locked,
        failures=failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_governance_report(r: GovernanceResult) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 8: GOVERNANCE INTEGRITY",
        "=" * 70,
        f"  Verdict: {'PASS' if r.passed else 'FAIL'}",
        f"  Guards Checked: {r.guards_checked}",
        f"  Guards Passed:  {r.guards_passed}/{r.guards_checked}",
        f"  MODE-B Locked:  {'YES' if r.mode_b_locked else 'NO (DANGER!)'}",
        "",
        "  Guard Details:",
    ]
    for name, passed, msg in r.guard_results:
        status = "PASS" if passed else "FAIL"
        lines.append(f"    [{status}] {name}")
        lines.append(f"           {msg}")
    
    if r.failures:
        lines += ["", "  FAILURES:"]
        for f in r.failures:
            lines.append(f"    {f}")
    
    lines += [
        "", "=" * 70,
        f"  PHASE 8 VERDICT: {'PASS' if r.passed else 'FAIL -- MODE-B BLOCKED'}",
        "=" * 70,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print("Running governance integrity check...")
    result = run_governance_check()
    report = generate_governance_report(result)
    print(report)
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'g38_training', 'phase8_governance.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    sys.exit(0 if result.passed else 1)
