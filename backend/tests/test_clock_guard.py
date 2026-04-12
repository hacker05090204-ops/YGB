from __future__ import annotations

import pytest


def test_clock_skew_simulation_raises_without_env(monkeypatch):
    from backend.governance.clock_guard import ClockGuard

    monkeypatch.delenv("YGB_CLOCK_SIMULATION", raising=False)
    monkeypatch.delenv("YGB_ENV", raising=False)

    guard = ClockGuard()

    with pytest.raises(RuntimeError, match="clock skew simulation is disabled"):
        guard.check_skew_simulated(1000.0, 1000.0)
