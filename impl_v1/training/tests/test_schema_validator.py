"""
Tests for 23-field canonical schema validator.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))


def _make_valid_record(**overrides):
    """Create a minimal valid record for testing."""
    record = {
        "record_id": "REC-001",
        "source_url": "https://example.com/api/users",
        "source_domain": "example.com",
        "endpoint_path": "/api/users",
        "http_method": "GET",
        "response_code": 200,
        "response_body_hash": "a" * 64,
        "content_type": "application/json",
        "timestamp_utc": "2026-02-24T20:00:00Z",
        "bug_class": "XSS",
        "severity": "HIGH",
        "confidence_score": 0.85,
        "is_verified": True,
        "verification_hash": "b" * 64,
        "feature_vector": [0.1] * 256,
        "label": 1,
        "reproduction_steps": "1. Navigate to /api/users 2. Submit payload",
        "impact_description": "XSS allows session hijacking",
        "remediation_hint": "Add input sanitization",
        "duplicate_group_id": "NONE",
        "ingestion_batch_id": "BATCH-2026-02-24",
        "data_source_trust": 0.9,
        "schema_version": "1.0.0",
    }
    record.update(overrides)
    return record


class TestSchemaValidator(unittest.TestCase):
    """Test canonical 23-field schema."""

    def test_valid_record_passes(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record())
        self.assertTrue(result.valid)
        self.assertEqual(len(result.violations), 0)
        self.assertEqual(result.checked_fields, 23)

    def test_missing_field_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        record = _make_valid_record()
        del record["record_id"]
        result = validate_record(record)
        self.assertFalse(result.valid)
        self.assertTrue(any(v.field_name == "record_id" for v in result.violations))

    def test_wrong_type_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(confidence_score="not a float"))
        self.assertFalse(result.valid)
        self.assertTrue(any(v.violation_type == "WRONG_TYPE" for v in result.violations))

    def test_invalid_http_method_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(http_method="HACK"))
        self.assertFalse(result.valid)

    def test_invalid_severity_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(severity="ULTRA"))
        self.assertFalse(result.valid)

    def test_confidence_out_of_range_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(confidence_score=1.5))
        self.assertFalse(result.valid)

    def test_short_feature_vector_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(feature_vector=[0.1] * 8))
        self.assertFalse(result.valid)

    def test_negative_label_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(label=-1))
        self.assertFalse(result.valid)

    def test_forbidden_field_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        record = _make_valid_record()
        record["bypass_governance"] = True
        result = validate_record(record)
        self.assertFalse(result.valid)
        self.assertTrue(any(v.violation_type == "FORBIDDEN" for v in result.violations))

    def test_empty_record_id_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(record_id="  "))
        self.assertFalse(result.valid)

    def test_int_coerced_to_float(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(confidence_score=1, data_source_trust=0))
        self.assertTrue(result.valid)

    def test_extra_unknown_field_warned(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(unknown_bonus_field="hello"))
        self.assertTrue(result.valid)  # Unknown fields are warnings, not violations
        self.assertTrue(len(result.warnings) > 0)

    def test_response_code_out_of_range_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(response_code=999))
        self.assertFalse(result.valid)

    def test_to_dict_serialization(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record())
        d = result.to_dict()
        self.assertTrue(d["valid"])
        self.assertEqual(d["schema_version"], "1.0.0")

    def test_batch_validation(self):
        from impl_v1.training.safety.schema_validator import validate_batch
        records = [
            _make_valid_record(record_id=f"REC-{i}") for i in range(5)
        ]
        records.append(_make_valid_record(record_id="BAD", severity="INVALID"))
        summary = validate_batch(records)
        self.assertEqual(summary["total"], 6)
        self.assertEqual(summary["valid_count"], 5)
        self.assertEqual(summary["rejected_count"], 1)

    def test_trust_score_out_of_range_rejected(self):
        from impl_v1.training.safety.schema_validator import validate_record
        result = validate_record(_make_valid_record(data_source_trust=2.0))
        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()
