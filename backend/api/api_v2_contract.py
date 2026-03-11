"""
API v2 Contract — JSON Schema Validation + Null-Safe Response Builder

Addresses:
  - Change Management Risk: API v2 returning null for unmeasured metrics
  - Observability Risk: dashboards may interpret null-heavy responses incorrectly
  - Compatibility Risk: frontend clients may not handle null safely

Provides:
  - RUNTIME_STATUS_SCHEMA: JSON Schema for /runtime/status responses
  - validate_response(): validates response dicts against a schema
  - NullSafeResponseBuilder: ensures all expected fields are present
  - ContractViolationError: typed exception for contract failures
"""

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("ygb.api.contract")


class ContractViolationError(Exception):
    """Raised when an API response violates its contract schema."""

    def __init__(self, violations: List[str], schema_name: str = "unknown"):
        self.violations = violations
        self.schema_name = schema_name
        msg = f"Contract '{schema_name}' violated: {'; '.join(violations[:5])}"
        if len(violations) > 5:
            msg += f" (+{len(violations) - 5} more)"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Runtime Status Schema (describes /runtime/status response)
# ---------------------------------------------------------------------------

RUNTIME_STATUS_SCHEMA: Dict[str, Any] = {
    "name": "runtime_status_v2",
    "required_fields": {
        "status",
        "storage_engine_status",
        "dataset_readiness",
        "training_ready",
        "timestamp",
    },
    "nullable_fields": {
        # These fields MAY be null in v2 when not yet measured
        "runtime",
        "signature",
        "stale",
        "determinism_ok",
        "message",
    },
    "metric_fields": [
        "total_epochs", "completed_epochs", "current_loss", "best_loss",
        "precision", "ece", "drift_kl", "duplicate_rate",
        "gpu_util", "cpu_util", "temperature",
        "progress_pct", "loss_trend", "total_errors",
    ],
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_response(
    data: Dict[str, Any],
    schema: Dict[str, Any],
) -> List[str]:
    """Validate a response dict against a contract schema.

    Returns a list of violation descriptions. Empty list means valid.
    Does NOT raise — caller decides whether to raise or log.
    """
    violations: List[str] = []
    schema_name = schema.get("name", "unknown")

    # Check required fields
    required: Set[str] = schema.get("required_fields", set())
    for field in required:
        if field not in data:
            violations.append(f"missing required field '{field}'")

    # Check that nullable fields are at least present (even if null)
    nullable: Set[str] = schema.get("nullable_fields", set())
    # nullable fields are optional — they don't need to be present,
    # but if present may be null

    # Check for unexpected null in required fields
    for field in required:
        if field in data and data[field] is None:
            violations.append(f"required field '{field}' is null")

    return violations


def validate_response_strict(
    data: Dict[str, Any],
    schema: Dict[str, Any],
) -> None:
    """Validate and raise on violations."""
    violations = validate_response(data, schema)
    if violations:
        raise ContractViolationError(violations, schema.get("name", "unknown"))


# ---------------------------------------------------------------------------
# Null-Safe Response Builder
# ---------------------------------------------------------------------------

class NullSafeResponseBuilder:
    """Builds API responses that explicitly include all expected fields.

    Ensures:
      - Required fields are always present
      - Nullable fields are present as null if not provided
      - No fields silently disappear between versions
    """

    def __init__(self, schema: Dict[str, Any]):
        self._schema = schema
        self._required: Set[str] = schema.get("required_fields", set())
        self._nullable: Set[str] = schema.get("nullable_fields", set())
        self._all_fields = self._required | self._nullable

    def build(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a response ensuring all schema fields are present.

        Required fields that are missing will raise ContractViolationError.
        Nullable fields that are missing will be set to None.
        Extra fields not in schema are preserved (forward-compatible).
        """
        result = dict(data)

        # Ensure nullable fields default to None
        for field in self._nullable:
            if field not in result:
                result[field] = None

        # Validate required fields
        missing_required = [f for f in self._required if f not in result]
        if missing_required:
            raise ContractViolationError(
                [f"missing required field '{f}'" for f in missing_required],
                self._schema.get("name", "unknown"),
            )

        return result

    def get_field_diff(
        self,
        actual_fields: Set[str],
    ) -> Dict[str, List[str]]:
        """Compare actual response fields against schema.

        Returns:
            {
                "missing": fields in schema but not in response,
                "extra": fields in response but not in schema,
            }
        """
        expected = self._all_fields
        return {
            "missing": sorted(expected - actual_fields),
            "extra": sorted(actual_fields - expected),
        }


def get_measurement_completeness(
    data: Dict[str, Any],
    metric_fields: Optional[List[str]] = None,
) -> float:
    """Calculate measurement completeness ratio.

    Returns 0.0–1.0: fraction of metric fields that are non-null.
    Defaults to RUNTIME_STATUS_SCHEMA['metric_fields'] if not specified.
    """
    fields = metric_fields or RUNTIME_STATUS_SCHEMA.get("metric_fields", [])
    if not fields:
        return 1.0

    non_null = sum(1 for f in fields if data.get(f) is not None)
    return round(non_null / len(fields), 4)
