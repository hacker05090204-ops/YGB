"""Focused tests for G40 training quorum node checks."""

from impl_v1.phase49.governors.g40_training_quorum import (
    QuorumAuditLog,
    QuorumChecker,
    QuorumState,
)


def test_exact_quorum_met():
    checker = QuorumChecker()

    record = checker.evaluate(3, ["node-a", "node-b", "node-c"])

    assert record.required_nodes == 3
    assert record.active_nodes == 3
    assert record.state == QuorumState.QUORUM_MET


def test_one_below_quorum_not_met():
    checker = QuorumChecker()

    record = checker.evaluate(3, ["node-a", "node-b"])

    assert record.active_nodes == 2
    assert record.state == QuorumState.QUORUM_NOT_MET
    assert checker.can_start_training(3, ["node-a", "node-b"]) is False


def test_empty_active_nodes_are_unknown_not_not_met():
    checker = QuorumChecker()

    record = checker.evaluate(3, [])

    assert record.active_nodes == 0
    assert record.state == QuorumState.QUORUM_UNKNOWN
    assert record.state != QuorumState.QUORUM_NOT_MET
    assert checker.can_start_training(3, []) is False


def test_every_evaluation_is_logged():
    audit_log = QuorumAuditLog()
    checker = QuorumChecker(audit_log=audit_log)

    checker.evaluate(2, ["node-a", "node-b"])
    checker.evaluate(2, ["node-a"])
    checker.evaluate(2, [])

    assert len(audit_log) == 3
