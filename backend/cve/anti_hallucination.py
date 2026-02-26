"""
Anti-Hallucination Controls — Provenance Validation for CVE Pipeline

Rules:
  - No generative inference in canonical pipeline.
  - Every field requires provenance: source, fetched_at, parser_version, confidence.
  - unverifiable_claim_rate must be 0 for production promotion.
  - Audit log for every provenance check.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger("ygb.anti_hallucination")

REQUIRED_PROVENANCE_FIELDS = frozenset([
    "source", "fetched_at", "parser_version", "confidence",
])


@dataclass
class ProvenanceCheckResult:
    """Result of a single provenance validation."""
    cve_id: str
    passed: bool
    missing_fields: List[str]
    confidence: float
    source: str
    detail: str


class AntiHallucinationValidator:
    """Validates that all CVE data has proper provenance and no generative content."""

    def __init__(self):
        self._audit_log: List[Dict[str, Any]] = []
        self._total_checks: int = 0
        self._passed_checks: int = 0
        self._failed_checks: int = 0

    def validate_provenance(
        self,
        cve_id: str,
        provenance: Dict[str, Any],
    ) -> ProvenanceCheckResult:
        """Validate that a provenance record has all required fields.

        Required: source, fetched_at, parser_version, confidence
        """
        self._total_checks += 1

        missing = []
        for field_name in REQUIRED_PROVENANCE_FIELDS:
            val = getattr(provenance, field_name, None) if hasattr(
                provenance, field_name
            ) else provenance.get(field_name)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(field_name)

        confidence = getattr(provenance, "confidence", 0.0) if hasattr(
            provenance, "confidence"
        ) else provenance.get("confidence", 0.0)
        source = getattr(provenance, "source", "") if hasattr(
            provenance, "source"
        ) else provenance.get("source", "")

        passed = len(missing) == 0
        if passed:
            self._passed_checks += 1
            detail = "All provenance fields present"
        else:
            self._failed_checks += 1
            detail = f"Missing provenance fields: {missing}"

        result = ProvenanceCheckResult(
            cve_id=cve_id,
            passed=passed,
            missing_fields=missing,
            confidence=confidence,
            source=source,
            detail=detail,
        )

        self._audit_log.append({
            "cve_id": cve_id,
            "passed": passed,
            "missing_fields": missing,
            "confidence": confidence,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return result

    def validate_record_provenance(
        self,
        cve_id: str,
        provenance_list: List[Any],
    ) -> List[ProvenanceCheckResult]:
        """Validate all provenance entries for a CVE record."""
        results = []
        for prov in provenance_list:
            result = self.validate_provenance(cve_id, prov)
            results.append(result)
        return results

    def compute_unverifiable_claim_rate(self) -> float:
        """Compute the fraction of provenance checks that failed.

        Must be 0.0 for production promotion.
        """
        if self._total_checks == 0:
            return 0.0
        return round(self._failed_checks / self._total_checks, 4)

    def is_production_ready(self) -> tuple:
        """Check if provenance meets production requirements.

        Returns (ready, reason).
        """
        rate = self.compute_unverifiable_claim_rate()
        if rate > 0:
            return False, (
                f"unverifiable_claim_rate={rate} > 0. "
                f"Failed {self._failed_checks}/{self._total_checks} checks."
            )
        if self._total_checks == 0:
            return False, "No provenance checks performed yet."
        return True, (
            f"All {self._total_checks} provenance checks passed. "
            f"unverifiable_claim_rate=0.0"
        )

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def get_status(self) -> Dict[str, Any]:
        return {
            "total_checks": self._total_checks,
            "passed": self._passed_checks,
            "failed": self._failed_checks,
            "unverifiable_claim_rate": self.compute_unverifiable_claim_rate(),
            "production_ready": self.is_production_ready()[0],
        }


# =============================================================================
# SINGLETON
# =============================================================================

_validator: Optional[AntiHallucinationValidator] = None


def get_anti_hallucination_validator() -> AntiHallucinationValidator:
    global _validator
    if _validator is None:
        _validator = AntiHallucinationValidator()
    return _validator
