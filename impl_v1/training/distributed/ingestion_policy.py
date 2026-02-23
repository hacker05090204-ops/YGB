"""
ingestion_policy.py — Ingestion Policy Gate (Phase 1)

Require:
- Exploit reproducibility
- Impact classification
- Real-world confirmation signal
If missing → discard.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IngestionCandidate:
    """A data sample candidate for ingestion."""
    sample_id: str
    endpoint: str
    exploit_vector: str
    impact: str
    source_id: str
    reproducible: bool
    impact_classified: bool
    real_world_confirmed: bool
    severity: str = ""    # critical / high / medium / low


@dataclass
class PolicyResult:
    """Result of ingestion policy check."""
    accepted: bool
    sample_id: str
    checks_passed: int
    checks_total: int
    reason: str


class IngestionPolicy:
    """Policy gate for data ingestion.

    3 mandatory checks:
    1. Exploit reproducibility
    2. Impact classification
    3. Real-world confirmation
    """

    def check(self, candidate: IngestionCandidate) -> PolicyResult:
        """Check if candidate meets ingestion policy."""
        passed = 0
        total = 3
        failures = []

        if candidate.reproducible:
            passed += 1
        else:
            failures.append("not_reproducible")

        if candidate.impact_classified:
            passed += 1
        else:
            failures.append("no_impact_classification")

        if candidate.real_world_confirmed:
            passed += 1
        else:
            failures.append("no_real_world_confirmation")

        accepted = passed == total

        result = PolicyResult(
            accepted=accepted,
            sample_id=candidate.sample_id,
            checks_passed=passed,
            checks_total=total,
            reason="All policy checks passed" if accepted
                   else f"Failed: {', '.join(failures)}",
        )

        icon = "✓" if accepted else "✗"
        logger.info(
            f"[POLICY] {icon} {candidate.sample_id}: "
            f"{passed}/{total} — {result.reason}"
        )
        return result

    def batch_check(self, candidates: List[IngestionCandidate]) -> Dict[str, PolicyResult]:
        """Check batch of candidates."""
        results = {}
        for c in candidates:
            results[c.sample_id] = self.check(c)
        accepted = sum(1 for r in results.values() if r.accepted)
        logger.info(
            f"[POLICY] Batch: {accepted}/{len(candidates)} accepted"
        )
        return results
