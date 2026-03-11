"""
API v2 Contract Tests — Schema validation, null-safe builder, field stability.

Validates:
1. Schema validation passes with valid response
2. Schema validation fails on missing required fields
3. Schema validation allows null for nullable fields
4. NullSafeResponseBuilder never drops fields
5. get_measurement_completeness calculation accuracy
6. ContractViolationError contains useful info
7. Field diff detection (missing/extra fields)
"""

import unittest


class TestContractValidation(unittest.TestCase):
    """Test JSON schema validation for API responses."""

    def _get_schema(self):
        from backend.api.api_v2_contract import RUNTIME_STATUS_SCHEMA
        return RUNTIME_STATUS_SCHEMA

    def test_valid_response_passes(self):
        from backend.api.api_v2_contract import validate_response
        schema = self._get_schema()
        data = {
            "status": "active",
            "storage_engine_status": "ACTIVE",
            "dataset_readiness": {"status": "BLOCKED"},
            "training_ready": False,
            "timestamp": 1234567890,
        }
        violations = validate_response(data, schema)
        self.assertEqual(len(violations), 0)

    def test_missing_required_field(self):
        from backend.api.api_v2_contract import validate_response
        schema = self._get_schema()
        data = {
            "status": "active",
            # missing storage_engine_status, dataset_readiness, training_ready, timestamp
        }
        violations = validate_response(data, schema)
        self.assertGreater(len(violations), 0)
        self.assertTrue(any("storage_engine_status" in v for v in violations))

    def test_null_required_field_is_violation(self):
        from backend.api.api_v2_contract import validate_response
        schema = self._get_schema()
        data = {
            "status": None,  # null in required field
            "storage_engine_status": "ACTIVE",
            "dataset_readiness": {},
            "training_ready": False,
            "timestamp": 123,
        }
        violations = validate_response(data, schema)
        self.assertTrue(any("null" in v.lower() for v in violations))

    def test_nullable_fields_allowed_null(self):
        from backend.api.api_v2_contract import validate_response
        schema = self._get_schema()
        data = {
            "status": "active",
            "storage_engine_status": "ACTIVE",
            "dataset_readiness": {},
            "training_ready": False,
            "timestamp": 123,
            "runtime": None,  # nullable field
            "signature": None,  # nullable field
        }
        violations = validate_response(data, schema)
        # Nullable fields with null should NOT cause violations
        self.assertEqual(len(violations), 0)


class TestContractViolationError(unittest.TestCase):
    """Test the ContractViolationError exception."""

    def test_error_message(self):
        from backend.api.api_v2_contract import ContractViolationError
        err = ContractViolationError(
            ["missing field 'x'", "missing field 'y'"],
            "test_schema",
        )
        self.assertIn("test_schema", str(err))
        self.assertIn("missing field", str(err))
        self.assertEqual(len(err.violations), 2)

    def test_truncation(self):
        from backend.api.api_v2_contract import ContractViolationError
        violations = [f"violation_{i}" for i in range(10)]
        err = ContractViolationError(violations, "test")
        self.assertIn("+5 more", str(err))


class TestNullSafeResponseBuilder(unittest.TestCase):
    """Test the null-safe response builder."""

    def test_adds_missing_nullable_fields(self):
        from backend.api.api_v2_contract import (
            NullSafeResponseBuilder, RUNTIME_STATUS_SCHEMA
        )
        builder = NullSafeResponseBuilder(RUNTIME_STATUS_SCHEMA)
        data = {
            "status": "active",
            "storage_engine_status": "ACTIVE",
            "dataset_readiness": {},
            "training_ready": False,
            "timestamp": 123,
        }
        result = builder.build(data)
        # Nullable fields should be present as None
        self.assertIn("runtime", result)
        self.assertIsNone(result["runtime"])
        self.assertIn("signature", result)
        self.assertIsNone(result["signature"])

    def test_raises_on_missing_required(self):
        from backend.api.api_v2_contract import (
            NullSafeResponseBuilder, RUNTIME_STATUS_SCHEMA,
            ContractViolationError,
        )
        builder = NullSafeResponseBuilder(RUNTIME_STATUS_SCHEMA)
        data = {"status": "active"}  # missing other required fields
        with self.assertRaises(ContractViolationError):
            builder.build(data)

    def test_preserves_extra_fields(self):
        from backend.api.api_v2_contract import (
            NullSafeResponseBuilder, RUNTIME_STATUS_SCHEMA,
        )
        builder = NullSafeResponseBuilder(RUNTIME_STATUS_SCHEMA)
        data = {
            "status": "active",
            "storage_engine_status": "ACTIVE",
            "dataset_readiness": {},
            "training_ready": False,
            "timestamp": 123,
            "custom_field": "preserved",
        }
        result = builder.build(data)
        self.assertEqual(result["custom_field"], "preserved")

    def test_field_diff_detection(self):
        from backend.api.api_v2_contract import (
            NullSafeResponseBuilder, RUNTIME_STATUS_SCHEMA,
        )
        builder = NullSafeResponseBuilder(RUNTIME_STATUS_SCHEMA)
        actual = {"status", "timestamp", "unknown_field"}
        diff = builder.get_field_diff(actual)
        self.assertIn("unknown_field", diff["extra"])
        self.assertGreater(len(diff["missing"]), 0)


class TestMeasurementCompleteness(unittest.TestCase):
    """Test measurement completeness calculation."""

    def test_full_completeness(self):
        from backend.api.api_v2_contract import get_measurement_completeness
        data = {"total_epochs": 10, "completed_epochs": 5, "current_loss": 0.1}
        ratio = get_measurement_completeness(data, ["total_epochs", "completed_epochs", "current_loss"])
        self.assertAlmostEqual(ratio, 1.0, places=4)

    def test_partial_completeness(self):
        from backend.api.api_v2_contract import get_measurement_completeness
        data = {"total_epochs": 10, "completed_epochs": None, "current_loss": None}
        ratio = get_measurement_completeness(data, ["total_epochs", "completed_epochs", "current_loss"])
        self.assertAlmostEqual(ratio, 1 / 3, places=4)

    def test_zero_completeness(self):
        from backend.api.api_v2_contract import get_measurement_completeness
        data = {}
        ratio = get_measurement_completeness(data, ["a", "b", "c"])
        self.assertAlmostEqual(ratio, 0.0, places=4)

    def test_uses_schema_defaults(self):
        from backend.api.api_v2_contract import (
            get_measurement_completeness, RUNTIME_STATUS_SCHEMA,
        )
        data = {}
        ratio = get_measurement_completeness(data)  # uses default metric_fields
        metric_count = len(RUNTIME_STATUS_SCHEMA["metric_fields"])
        self.assertAlmostEqual(ratio, 0.0, places=4)
        self.assertGreater(metric_count, 0)


if __name__ == "__main__":
    unittest.main()
