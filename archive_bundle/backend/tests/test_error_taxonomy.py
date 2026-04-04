"""
Error Taxonomy Tests

Tests for backend/errors.py standardized error handling.
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestErrorCodes(unittest.TestCase):
    """Test ErrorCode enum values and mapping."""

    def test_all_codes_have_status_mapping(self):
        """Every ErrorCode must have a corresponding HTTP status code."""
        from backend.errors import ErrorCode, _STATUS_MAP
        for code in ErrorCode:
            self.assertIn(code, _STATUS_MAP, f"Missing status mapping for {code}")

    def test_status_codes_are_valid_http(self):
        """All mapped status codes should be valid HTTP error codes."""
        from backend.errors import _STATUS_MAP
        for code, status in _STATUS_MAP.items():
            self.assertGreaterEqual(status, 400)
            self.assertLessEqual(status, 599)


class TestApiError(unittest.TestCase):
    """Test api_error helper function."""

    def test_returns_http_exception(self):
        from backend.errors import api_error, ErrorCode
        from fastapi import HTTPException
        exc = api_error(ErrorCode.VALIDATION, "Title is required")
        self.assertIsInstance(exc, HTTPException)
        self.assertEqual(exc.status_code, 400)

    def test_includes_correlation_id(self):
        from backend.errors import api_error, ErrorCode
        exc = api_error(ErrorCode.INTERNAL, "Something broke")
        detail = exc.detail
        self.assertIn("correlation_id", detail)
        self.assertTrue(len(detail["correlation_id"]) > 0)

    def test_custom_status_code(self):
        from backend.errors import api_error, ErrorCode
        exc = api_error(ErrorCode.VALIDATION, "bad", status_code=422)
        self.assertEqual(exc.status_code, 422)

    def test_error_format(self):
        from backend.errors import api_error, ErrorCode
        exc = api_error(ErrorCode.NOT_FOUND, "User not found")
        self.assertEqual(exc.detail["error"], "NOT_FOUND")
        self.assertEqual(exc.detail["detail"], "User not found")

    def test_extra_fields(self):
        from backend.errors import api_error, ErrorCode
        exc = api_error(ErrorCode.VALIDATION, "Bad field", extra={"field": "email"})
        self.assertEqual(exc.detail["field"], "email")

    def test_no_internal_details_exposed(self):
        """Error messages should not contain stack traces or file paths."""
        from backend.errors import api_error, ErrorCode
        exc = api_error(ErrorCode.INTERNAL, "Server error")
        detail_str = str(exc.detail)
        self.assertNotIn("Traceback", detail_str)
        self.assertNotIn(".py", detail_str)


class TestInternalError(unittest.TestCase):
    """Test internal_error helper for exception wrapping."""

    def test_wraps_exception(self):
        from backend.errors import internal_error
        try:
            raise ValueError("test error")
        except ValueError as e:
            exc = internal_error(e, context="test context")
            self.assertEqual(exc.status_code, 500)
            self.assertIn("correlation_id", exc.detail)

    def test_does_not_leak_exception_details(self):
        from backend.errors import internal_error
        try:
            raise RuntimeError("/etc/passwd hack attempt")
        except RuntimeError as e:
            exc = internal_error(e)
            self.assertNotIn("/etc/passwd", exc.detail.get("detail", ""))
            self.assertNotIn("hack", exc.detail.get("detail", ""))


class TestLogInternalError(unittest.TestCase):
    """Test log_internal_error function."""

    def test_returns_correlation_id(self):
        from backend.errors import log_internal_error
        try:
            raise TypeError("type mismatch")
        except TypeError as e:
            cid = log_internal_error(e, context="test")
            self.assertIsInstance(cid, str)
            self.assertEqual(len(cid), 16)  # hex(8) = 16 chars


class TestNoMockPatterns(unittest.TestCase):
    """Ensure errors module doesn't contain mock/fake patterns."""

    def test_no_forbidden_patterns(self):
        import inspect
        from backend import errors
        source = inspect.getsource(errors)
        for pattern in ["MOCK_", "FAKE_", "DEMO_", "simulated ="]:
            self.assertNotIn(pattern, source)


if __name__ == "__main__":
    unittest.main()
