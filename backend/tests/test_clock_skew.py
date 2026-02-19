"""
test_clock_skew.py — Clock Skew Guard Tests
============================================
Tests for clock_guard.py:
  - Simulated skew within tolerance
  - Simulated skew exceeding tolerance
  - Fail-safe when NTP unreachable
  - Certification blocking on skew
  - History tracking
  - Custom thresholds
============================================
"""

import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from governance.clock_guard import ClockGuard, ClockSkewResult


class TestClockSkewSimulated(unittest.TestCase):
    """Test clock skew detection with simulated times (no NTP)."""

    def setUp(self):
        self.guard = ClockGuard(max_skew=5.0)

    def test_zero_skew_passes(self):
        """Zero skew → CLOCK_OK."""
        result = self.guard.check_skew_simulated(1000.0, 1000.0)
        self.assertTrue(result.passed)
        self.assertEqual(result.skew_seconds, 0.0)
        self.assertIn("CLOCK_OK", result.reason)

    def test_skew_within_tolerance_passes(self):
        """Skew of 3s ≤ 5s → CLOCK_OK."""
        result = self.guard.check_skew_simulated(1000.0, 1003.0)
        self.assertTrue(result.passed)
        self.assertEqual(result.skew_seconds, 3.0)

    def test_skew_exactly_5s_passes(self):
        """Skew of exactly 5s → passes (≤ threshold)."""
        result = self.guard.check_skew_simulated(1000.0, 1005.0)
        self.assertTrue(result.passed)

    def test_skew_exceeds_tolerance_blocks(self):
        """Skew of 10s > 5s → GOVERNANCE_CLOCK_SKEW."""
        result = self.guard.check_skew_simulated(1000.0, 1010.0)
        self.assertFalse(result.passed)
        self.assertIn("GOVERNANCE_CLOCK_SKEW", result.reason)
        self.assertIn("CERTIFICATION BLOCKED", result.reason)

    def test_large_skew_blocks(self):
        """Skew of 60s → definitely blocked."""
        result = self.guard.check_skew_simulated(1000.0, 1060.0)
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.skew_seconds, 60.0)

    def test_negative_skew_handled(self):
        """Local clock ahead of NTP → abs(skew) used."""
        result = self.guard.check_skew_simulated(1010.0, 1000.0)
        self.assertFalse(result.passed)
        self.assertEqual(result.skew_seconds, 10.0)


class TestCertificationBlocking(unittest.TestCase):
    """Test that certification is blocked when clock is skewed."""

    def test_certification_blocked_on_skew(self):
        """Simulated skew blocks certification."""
        guard = ClockGuard(max_skew=5.0)
        result = guard.check_skew_simulated(1000.0, 1020.0)
        self.assertFalse(result.passed, "Certification must be blocked")

    def test_no_certification_without_ntp(self):
        """If all NTP unreachable → fail-safe blocks certification."""
        guard = ClockGuard(
            max_skew=5.0,
            ntp_servers=["invalid.ntp.server.zzz"],
            timeout=0.5,
        )
        allowed, reason = guard.certification_allowed()
        self.assertFalse(allowed)
        self.assertIn("BLOCKED", reason)


class TestClockGuardHistory(unittest.TestCase):
    """Test that clock check history is maintained."""

    def test_history_accumulates(self):
        """Each check adds an entry to history."""
        guard = ClockGuard()
        guard.check_skew_simulated(1000.0, 1000.0)
        guard.check_skew_simulated(1000.0, 1010.0)
        guard.check_skew_simulated(1000.0, 1003.0)
        self.assertEqual(len(guard.history), 3)

    def test_last_result_available(self):
        """last_result returns most recent check."""
        guard = ClockGuard()
        guard.check_skew_simulated(1000.0, 1000.0)
        guard.check_skew_simulated(1000.0, 1020.0)
        last = guard.last_result
        self.assertIsNotNone(last)
        self.assertFalse(last.passed)  # last one was skewed

    def test_empty_history_returns_none(self):
        """No checks → last_result is None."""
        guard = ClockGuard()
        self.assertIsNone(guard.last_result)

    def test_result_to_dict(self):
        """ClockSkewResult serializes to dict."""
        guard = ClockGuard()
        result = guard.check_skew_simulated(1000.0, 1002.0)
        d = result.to_dict()
        self.assertIn("skew_seconds", d)
        self.assertIn("passed", d)
        self.assertIn("reason", d)
        self.assertIn("ntp_server", d)
        self.assertEqual(d["ntp_server"], "SIMULATED")


class TestCustomThresholds(unittest.TestCase):
    """Test custom skew thresholds."""

    def test_tight_threshold_1s(self):
        """1s threshold blocks 2s skew."""
        guard = ClockGuard(max_skew=1.0)
        result = guard.check_skew_simulated(1000.0, 1002.0)
        self.assertFalse(result.passed)

    def test_loose_threshold_30s(self):
        """30s threshold allows 10s skew."""
        guard = ClockGuard(max_skew=30.0)
        result = guard.check_skew_simulated(1000.0, 1010.0)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
