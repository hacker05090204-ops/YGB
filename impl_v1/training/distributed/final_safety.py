"""
final_safety.py — Final Safety Gate (Phase 5)

Unified abort gate. Abort only if:
- Dataset corruption
- Determinism mismatch
- Regression > 2%
- 3 consecutive crashes
- Semantic quality failure

Everything else: auto-heal or continue.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CRASHES = 3
REGRESSION_THRESHOLD = 0.02


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    check_name: str
    passed: bool
    severity: str       # info / warning / abort
    detail: str


@dataclass
class FinalSafetyReport:
    """Unified safety report."""
    training_allowed: bool
    checks: List[SafetyCheckResult]
    abort_reason: Optional[str]
    crash_count: int
    timestamp: str = ""


class FinalSafetyGate:
    """Unified production safety gate.

    Hard abort:
    - Dataset corruption
    - Determinism mismatch
    - Regression > 2%
    - 3+ consecutive crashes
    - Semantic quality failure

    Auto-heal only:
    - Single crash → resume
    - Shard repair → peer
    """

    def __init__(self, max_crashes: int = MAX_CRASHES):
        self.max_crashes = max_crashes
        self._crash_count = 0
        self._aborted = False
        self._abort_reason: Optional[str] = None

    def run_checks(
        self,
        dataset_valid: bool = True,
        determinism_match: bool = True,
        regression_delta: float = 0.0,
        semantic_passed: bool = True,
        crash_count: int = 0,
    ) -> FinalSafetyReport:
        """Run all safety checks at once."""
        checks = []
        self._crash_count = crash_count

        # 1. Dataset
        checks.append(SafetyCheckResult(
            check_name="dataset_integrity",
            passed=dataset_valid,
            severity="abort" if not dataset_valid else "info",
            detail="Dataset valid" if dataset_valid else "Dataset corrupted",
        ))

        # 2. Determinism
        checks.append(SafetyCheckResult(
            check_name="determinism",
            passed=determinism_match,
            severity="abort" if not determinism_match else "info",
            detail="Determinism OK" if determinism_match else "Determinism mismatch",
        ))

        # 3. Regression
        reg_ok = regression_delta >= -REGRESSION_THRESHOLD
        checks.append(SafetyCheckResult(
            check_name="regression",
            passed=reg_ok,
            severity="abort" if not reg_ok else "info",
            detail=(
                f"Δ={regression_delta:+.4f}" if reg_ok
                else f"Regression {regression_delta:+.4f} > {REGRESSION_THRESHOLD}"
            ),
        ))

        # 4. Crashes
        crash_ok = crash_count < self.max_crashes
        checks.append(SafetyCheckResult(
            check_name="crash_limit",
            passed=crash_ok,
            severity="abort" if not crash_ok else (
                "warning" if crash_count > 0 else "info"
            ),
            detail=(
                f"Crashes: {crash_count}/{self.max_crashes}"
            ),
        ))

        # 5. Semantic quality
        checks.append(SafetyCheckResult(
            check_name="semantic_quality",
            passed=semantic_passed,
            severity="abort" if not semantic_passed else "info",
            detail=(
                "Semantic quality OK" if semantic_passed
                else "Semantic quality FAILED"
            ),
        ))

        # Decision
        all_passed = all(c.passed for c in checks)
        abort_reason = None
        if not all_passed:
            failed = [c.check_name for c in checks if not c.passed]
            abort_reason = f"ABORT: {', '.join(failed)}"
            self._aborted = True
            self._abort_reason = abort_reason

        report = FinalSafetyReport(
            training_allowed=all_passed,
            checks=checks,
            abort_reason=abort_reason,
            crash_count=crash_count,
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_passed else "✗"
        logger.info(f"[SAFETY] {icon} Final: {'PASS' if all_passed else abort_reason}")
        for c in checks:
            ci = "✓" if c.passed else "✗"
            logger.info(f"  {ci} [{c.check_name}] {c.detail}")

        return report

    @property
    def is_safe(self) -> bool:
        return not self._aborted

    def reset(self):
        """Reset for next training cycle."""
        self._aborted = False
        self._abort_reason = None
        self._crash_count = 0
