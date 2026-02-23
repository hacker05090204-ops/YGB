"""
unified_safety_gate.py — Unified Final Safety (Phase 7)

Abort if:
- Data corruption
- Determinism mismatch
- Semantic gate fail
- Regression fail
- Cross-field leakage
- Source reliability drop

No auto-promote without passing all gates.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SafetyGateCheck:
    """A single safety gate."""
    gate: str
    passed: bool
    detail: str


@dataclass
class UnifiedSafetyReport:
    """Comprehensive safety report."""
    training_allowed: bool
    promotion_allowed: bool
    gates: List[SafetyGateCheck]
    abort_reason: Optional[str]
    timestamp: str = ""


class UnifiedSafetyGate:
    """All-in-one safety gate for autonomous training.

    6 abort conditions + no auto-promote without all gates.
    """

    def evaluate(
        self,
        data_valid: bool = True,
        determinism_match: bool = True,
        semantic_passed: bool = True,
        regression_passed: bool = True,
        cross_field_ok: bool = True,
        source_reliable: bool = True,
    ) -> UnifiedSafetyReport:
        """Evaluate all 6 safety gates."""
        gates = [
            SafetyGateCheck("data_integrity", data_valid,
                           "OK" if data_valid else "Data corruption detected"),
            SafetyGateCheck("determinism", determinism_match,
                           "OK" if determinism_match else "Determinism mismatch"),
            SafetyGateCheck("semantic_quality", semantic_passed,
                           "OK" if semantic_passed else "Semantic gate failed"),
            SafetyGateCheck("regression", regression_passed,
                           "OK" if regression_passed else "Regression detected"),
            SafetyGateCheck("cross_field", cross_field_ok,
                           "OK" if cross_field_ok else "Cross-field leakage"),
            SafetyGateCheck("source_reliability", source_reliable,
                           "OK" if source_reliable else "Source reliability dropped"),
        ]

        all_ok = all(g.passed for g in gates)
        failed = [g.gate for g in gates if not g.passed]

        report = UnifiedSafetyReport(
            training_allowed=all_ok,
            promotion_allowed=all_ok,  # No promotion without all gates
            gates=gates,
            abort_reason=None if all_ok else f"ABORT: {', '.join(failed)}",
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_ok else "✗"
        logger.info(
            f"[UNIFIED_SAFETY] {icon} "
            f"{'ALL PASS' if all_ok else report.abort_reason}"
        )
        for g in gates:
            gi = "✓" if g.passed else "✗"
            logger.info(f"  {gi} [{g.gate}] {g.detail}")

        return report
