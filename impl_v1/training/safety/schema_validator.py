"""
Canonical 23-Field Dataset Schema Validator
===========================================

Defines the required 23 fields for production dataset records
with type, constraints, and forbidden extras.

Usage:
    from impl_v1.training.safety.schema_validator import validate_record
    result = validate_record(record_dict)
    if not result.valid:
        print(result.violations)
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# CANONICAL SCHEMA — 23 REQUIRED FIELDS
# =============================================================================

SCHEMA_VERSION = "1.0.0"

REQUIRED_FIELDS = {
    # Field name → (type, required, constraints_description)
    "record_id":          (str,   True,  "Non-empty UUID or stable identifier"),
    "source_url":         (str,   True,  "Full URL of source endpoint"),
    "source_domain":      (str,   True,  "Domain extracted from source_url"),
    "endpoint_path":      (str,   True,  "URL path component"),
    "http_method":        (str,   True,  "GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD"),
    "response_code":      (int,   True,  "HTTP response code (100-599)"),
    "response_body_hash": (str,   True,  "SHA-256 hex of response body"),
    "content_type":       (str,   True,  "MIME type of response"),
    "timestamp_utc":      (str,   True,  "ISO 8601 UTC timestamp"),
    "bug_class":          (str,   True,  "Bug classification label"),
    "severity":           (str,   True,  "CRITICAL|HIGH|MEDIUM|LOW|INFO"),
    "confidence_score":   (float, True,  "0.0-1.0 model confidence"),
    "is_verified":        (bool,  True,  "Human verification flag"),
    "verification_hash":  (str,   True,  "SHA-256 of verification evidence"),
    "feature_vector":     (list,  True,  "Embedding vector (dim >= 16)"),
    "label":              (int,   True,  "Class label (non-negative integer)"),
    "reproduction_steps":  (str,  True,  "Steps to reproduce"),
    "impact_description":  (str,  True,  "Impact or exploit description"),
    "remediation_hint":    (str,  True,  "Suggested fix approach"),
    "duplicate_group_id":  (str,  True,  "Duplicate group identifier, 'NONE' if unique"),
    "ingestion_batch_id":  (str,  True,  "Batch ID of ingestion run"),
    "data_source_trust":   (float, True, "Source trust score 0.0-1.0"),
    "schema_version":      (str,  True,  "Schema version (e.g. 1.0.0)"),
}

VALID_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}

# Fields that MUST NOT appear in production records
FORBIDDEN_FIELDS = {
    "synthetic", "mock", "test_only", "debug_override",
    "bypass_governance", "force_pass", "skip_validation",
    "admin_override", "raw_password", "session_token",
}


# =============================================================================
# VALIDATION RESULT
# =============================================================================

@dataclass
class SchemaViolation:
    """Single schema violation."""
    field_name: str
    violation_type: str     # MISSING, WRONG_TYPE, CONSTRAINT_FAIL, FORBIDDEN
    expected: str
    actual: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SchemaValidationResult:
    """Result of schema validation."""
    valid: bool
    record_id: str = ""
    violations: List[SchemaViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checked_fields: int = 0
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "record_id": self.record_id,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": self.warnings,
            "checked_fields": self.checked_fields,
            "schema_version": self.schema_version,
        }


# =============================================================================
# VALIDATOR
# =============================================================================

def validate_record(record: Dict[str, Any]) -> SchemaValidationResult:
    """
    Validate a single dataset record against the canonical 23-field schema.
    
    Returns SchemaValidationResult. If invalid, violations list details each failure.
    """
    violations = []
    warnings = []
    record_id = str(record.get("record_id", "UNKNOWN"))

    # Check required fields
    for field_name, (expected_type, required, constraint) in REQUIRED_FIELDS.items():
        if field_name not in record:
            if required:
                violations.append(SchemaViolation(
                    field_name=field_name,
                    violation_type="MISSING",
                    expected=f"{expected_type.__name__} (required)",
                    actual="<absent>",
                    message=f"Required field '{field_name}' is missing",
                ))
            continue

        value = record[field_name]

        # Type check (allow int for float fields)
        if expected_type == float and isinstance(value, int):
            value = float(value)
        elif not isinstance(value, expected_type):
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="WRONG_TYPE",
                expected=expected_type.__name__,
                actual=type(value).__name__,
                message=f"Field '{field_name}' expected {expected_type.__name__}, got {type(value).__name__}",
            ))
            continue

        # Constraint checks
        if field_name == "record_id" and len(value.strip()) == 0:
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected="Non-empty string",
                actual=repr(value),
                message="record_id must not be empty",
            ))

        elif field_name == "http_method" and value.upper() not in VALID_HTTP_METHODS:
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected=f"One of {VALID_HTTP_METHODS}",
                actual=value,
                message=f"Invalid HTTP method: {value}",
            ))

        elif field_name == "response_code" and not (100 <= value <= 599):
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected="100-599",
                actual=str(value),
                message=f"Invalid HTTP response code: {value}",
            ))

        elif field_name == "severity" and value.upper() not in VALID_SEVERITIES:
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected=f"One of {VALID_SEVERITIES}",
                actual=value,
                message=f"Invalid severity: {value}",
            ))

        elif field_name == "confidence_score" and not (0.0 <= value <= 1.0):
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected="0.0-1.0",
                actual=str(value),
                message=f"Confidence score out of range: {value}",
            ))

        elif field_name == "data_source_trust" and not (0.0 <= value <= 1.0):
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected="0.0-1.0",
                actual=str(value),
                message=f"Trust score out of range: {value}",
            ))

        elif field_name == "feature_vector":
            if not isinstance(value, list) or len(value) < 16:
                violations.append(SchemaViolation(
                    field_name=field_name,
                    violation_type="CONSTRAINT_FAIL",
                    expected="list with dim >= 16",
                    actual=f"list(len={len(value) if isinstance(value, list) else 'N/A'})",
                    message=f"Feature vector must have at least 16 dimensions",
                ))

        elif field_name == "label" and value < 0:
            violations.append(SchemaViolation(
                field_name=field_name,
                violation_type="CONSTRAINT_FAIL",
                expected="non-negative integer",
                actual=str(value),
                message=f"Label must be non-negative: {value}",
            ))

    # Check for forbidden fields
    for forbidden in FORBIDDEN_FIELDS:
        if forbidden in record:
            violations.append(SchemaViolation(
                field_name=forbidden,
                violation_type="FORBIDDEN",
                expected="<absent>",
                actual=str(record[forbidden]),
                message=f"Forbidden field '{forbidden}' found in record",
            ))

    # Check for unknown extra fields (warning, not violation)
    known_fields = set(REQUIRED_FIELDS.keys()) | FORBIDDEN_FIELDS
    for key in record.keys():
        if key not in known_fields:
            warnings.append(f"Unknown extra field: '{key}'")

    valid = len(violations) == 0
    if not valid:
        logger.warning(
            f"[SCHEMA] Record {record_id}: {len(violations)} violations — REJECTED"
        )
    else:
        logger.debug(f"[SCHEMA] Record {record_id}: valid")

    return SchemaValidationResult(
        valid=valid,
        record_id=record_id,
        violations=violations,
        warnings=warnings,
        checked_fields=len(REQUIRED_FIELDS),
        schema_version=SCHEMA_VERSION,
    )


def validate_batch(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Validate a batch of records and return summary statistics.
    
    Returns:
        dict with: total, valid_count, rejected_count, rejection_reasons (counter)
    """
    total = len(records)
    valid_count = 0
    rejected_count = 0
    rejection_reasons: Dict[str, int] = {}
    rejected_records: List[SchemaValidationResult] = []

    for record in records:
        result = validate_record(record)
        if result.valid:
            valid_count += 1
        else:
            rejected_count += 1
            rejected_records.append(result)
            for v in result.violations:
                key = f"{v.violation_type}:{v.field_name}"
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

    logger.info(
        f"[SCHEMA_BATCH] {valid_count}/{total} valid, "
        f"{rejected_count} rejected"
    )

    return {
        "total": total,
        "valid_count": valid_count,
        "rejected_count": rejected_count,
        "valid_ratio": valid_count / total if total > 0 else 0.0,
        "rejection_reasons": rejection_reasons,
        "schema_version": SCHEMA_VERSION,
    }
