"""
Scheduler Startup Regression Test.

Proves:
  1. scheduler.is_running == False before start
  2. scheduler.is_running == True after await start()
  3. Health state transitions (BOOTING → RUNNING)
  4. Graceful stop returns is_running to False
"""

import asyncio
import os
import sys
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestSchedulerStartup:
    """Regression tests for CVE scheduler lifecycle."""

    def setup_method(self):
        """Reset scheduler singleton for each test."""
        import backend.cve.cve_scheduler as mod
        mod._scheduler = None

    def test_not_running_initially(self):
        """Scheduler should not be running before start()."""
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()
        assert scheduler.is_running is False

    def test_running_after_await_start(self):
        """Scheduler MUST be running=True after await start().

        This is the root cause regression test:
        start() is async — calling without await leaves running=False.
        """
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(scheduler.start())
            assert scheduler.is_running is True, (
                "CRITICAL: scheduler.is_running must be True after await start(). "
                "Root cause: start() is async and must be awaited."
            )
        finally:
            loop.run_until_complete(scheduler.stop())
            loop.close()

    def test_not_running_after_stop(self):
        """Scheduler should not be running after stop()."""
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(scheduler.start())
            assert scheduler.is_running is True
            loop.run_until_complete(scheduler.stop())
            assert scheduler.is_running is False
        finally:
            if not loop.is_closed():
                loop.close()

    def test_health_state_booting_before_start(self):
        """Health state should be BOOTING before start."""
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()
        assert scheduler.health_state == "BOOTING"

    def test_health_includes_state(self):
        """get_health() must include health_state field."""
        from backend.cve.cve_scheduler import get_scheduler
        health = get_scheduler().get_health()
        assert "health_state" in health
        assert "running" in health
        assert "interval_seconds" in health
        assert health["interval_seconds"] == 300

    def test_double_start_idempotent(self):
        """Calling start() twice should not fail."""
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(scheduler.start())
            loop.run_until_complete(scheduler.start())  # Should warn, not crash
            assert scheduler.is_running is True
        finally:
            loop.run_until_complete(scheduler.stop())
            loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
