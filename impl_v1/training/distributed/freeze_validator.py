"""
freeze_validator.py — Freeze Validation Gate (Phase 6)

Only freeze new model if ALL pass:
1. Determinism check
2. Drift check
3. Regression check

Gate returns FREEZE or REJECT.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FreezeCheck:
    """A single freeze gate check."""
    check_name: str
    passed: bool
    detail: str


@dataclass
class FreezeValidationResult:
    """Result of freeze validation gate."""
    freeze_allowed: bool
    checks: List[FreezeCheck]
    reason: str
    model_version: str
    timestamp: str = ""


class FreezeValidator:
    """Gate: determinism + drift + regression must all pass.

    If any check fails → freeze rejected.
    """

    def validate_freeze(
        self,
        model_version: str,
        determinism_passed: bool,
        determinism_detail: str = "",
        drift_passed: bool = True,
        drift_detail: str = "",
        regression_passed: bool = True,
        regression_detail: str = "",
    ) -> FreezeValidationResult:
        """Run all freeze checks.

        Returns FreezeValidationResult with FREEZE or REJECT.
        """
        checks = []

        # Check 1: Determinism
        checks.append(FreezeCheck(
            check_name="determinism",
            passed=determinism_passed,
            detail=determinism_detail or (
                "Weight hashes match" if determinism_passed
                else "Weight hashes DO NOT match"
            ),
        ))

        # Check 2: Drift
        checks.append(FreezeCheck(
            check_name="drift_guard",
            passed=drift_passed,
            detail=drift_detail or (
                "No training anomalies" if drift_passed
                else "Training anomalies detected"
            ),
        ))

        # Check 3: Regression
        checks.append(FreezeCheck(
            check_name="regression",
            passed=regression_passed,
            detail=regression_detail or (
                "No regression beyond threshold" if regression_passed
                else "Model regressed beyond threshold"
            ),
        ))

        all_passed = all(c.passed for c in checks)

        if all_passed:
            reason = "FREEZE APPROVED: all 3 checks passed"
            logger.info(f"[FREEZE] ✓ {model_version}: {reason}")
        else:
            failed = [c.check_name for c in checks if not c.passed]
            reason = f"FREEZE REJECTED: failed checks = {', '.join(failed)}"
            logger.error(f"[FREEZE] ✗ {model_version}: {reason}")

        result = FreezeValidationResult(
            freeze_allowed=all_passed,
            checks=checks,
            reason=reason,
            model_version=model_version,
            timestamp=datetime.now().isoformat(),
        )

        # Log each check
        for c in checks:
            icon = "✓" if c.passed else "✗"
            logger.info(
                f"  {icon} [{c.check_name}] {c.detail}"
            )

        return result
