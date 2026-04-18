from __future__ import annotations

import numpy as np
import pytest

import backend.governance.kill_switch as kill_switch
import backend.governance.training_gate as training_gate
from backend.training.runtime_status_validator import TrainingGovernanceError
from impl_v1.training.data.governance_pipeline import pre_training_gate


def _fixed_check(passed: bool, message: str):
    def _check(**kwargs):
        return passed, message

    return _check


def test_kill_switch_persists_and_raises(tmp_path):
    state_path = tmp_path / "training_kill_switch.json"

    engaged = kill_switch.engage(
        "incident_response",
        actor="unit-test",
        path=state_path,
    )

    assert engaged["killed"] is True
    assert kill_switch.is_killed(path=state_path) is True

    with pytest.raises(TrainingGovernanceError) as excinfo:
        kill_switch.check_or_raise(path=state_path)

    assert excinfo.value.status == "KILLED"
    assert "incident_response" in str(excinfo.value)

    disengaged = kill_switch.disengage(
        "incident_cleared",
        actor="unit-test",
        path=state_path,
    )

    assert disengaged["killed"] is False
    assert kill_switch.is_killed(path=state_path) is False
    kill_switch.check_or_raise(path=state_path)


def test_training_gate_check_or_raise_raises_on_failed_check(monkeypatch):
    monkeypatch.setattr(training_gate, "check_kill_switch", lambda: None)
    monkeypatch.setattr(
        training_gate,
        "get_key_manager_status",
        lambda **kwargs: {"status": "HEALTHY", "available": True},
    )

    class _AuthorityLock:
        @staticmethod
        def verify_all_locked():
            return {"all_locked": True, "violations": []}

    monkeypatch.setattr(training_gate, "AuthorityLock", _AuthorityLock)
    monkeypatch.setattr(
        training_gate,
        "_PRETRAINING_CHECKS",
        tuple(
            (f"check_{index}", _fixed_check(index != 4, "blocked" if index == 4 else "ok"))
            for index in range(9)
        ),
    )

    features = np.ones((6, 4), dtype=np.float32)
    labels = np.asarray([0, 1, 0, 1, 0, 1], dtype=np.int64)
    result = training_gate.run_training_gate(features, labels, 2)

    assert result.passed is False
    assert result.checks_run == 9
    assert result.checks_failed == 1
    assert result.failures == ["check_4: blocked"]

    with pytest.raises(TrainingGovernanceError) as excinfo:
        training_gate.check_or_raise(features, labels, 2)

    assert excinfo.value.status == "TRAINING_GATE_BLOCKED"
    assert "check_4: blocked" in str(excinfo.value)


def test_training_gate_blocks_authority_lock_violation(monkeypatch):
    monkeypatch.setattr(training_gate, "check_kill_switch", lambda: None)

    class _AuthorityLock:
        @staticmethod
        def verify_all_locked():
            return {"all_locked": False, "violations": ["AUTO_SUBMIT"]}

    monkeypatch.setattr(training_gate, "AuthorityLock", _AuthorityLock)

    with pytest.raises(TrainingGovernanceError) as excinfo:
        training_gate.run_training_gate(
            np.ones((4, 4), dtype=np.float32),
            np.asarray([0, 1, 0, 1], dtype=np.int64),
            2,
        )

    assert excinfo.value.status == "AUTHORITY_VIOLATION"
    assert "AUTO_SUBMIT" in str(excinfo.value)


def test_governance_pipeline_maps_hard_training_gate_result(monkeypatch):
    fake_result = training_gate.TrainingGateResult(
        passed=False,
        checks_run=9,
        checks_passed=8,
        checks_failed=1,
        failures=["Dataset Quality Gate: blocked"],
        warnings=["warning"],
        duration_ms=12.5,
        authority_lock={"all_locked": True},
        approval_ledger={"status": "HEALTHY"},
    )

    monkeypatch.setattr(
        "backend.governance.training_gate.run_training_gate",
        lambda **kwargs: fake_result,
    )

    result = pre_training_gate(
        np.ones((4, 4), dtype=np.float32),
        np.asarray([0, 1, 0, 1], dtype=np.int64),
        2,
    )

    assert result.passed is False
    assert result.checks_run == 9
    assert result.checks_passed == 8
    assert result.checks_failed == 1
    assert result.failures == ["Dataset Quality Gate: blocked"]
    assert result.warnings == ["warning"]
    assert result.duration_ms == pytest.approx(12.5)
