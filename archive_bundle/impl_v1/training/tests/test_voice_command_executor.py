"""
Tests for voice command executor — end-to-end lifecycle.

Covers:
  - Low-risk command direct execution
  - High-risk command blocks without confirmation
  - High-risk command executes after confirmation
  - Critical risk auto-rejection
  - Command retry on transient failure
  - Queue management
  - Audit trail
  - Governance guards
"""

import pytest

from impl_v1.training.voice_command_executor import (
    CommandQueue,
    CommandRisk,
    CommandStatus,
    ActionType,
    VoiceCommand,
    ExecutionResult,
    parse_voice_text,
    classify_risk,
    can_voice_execute_directly,
    can_voice_bypass_confirmation,
)


class TestParseVoiceText:
    """Test voice text parsing."""

    def test_parse_status_query(self):
        assert parse_voice_text("show me the status") == ActionType.STATUS_QUERY

    def test_parse_training_status(self):
        assert parse_voice_text("what is the training status") == ActionType.TRAINING_STATUS

    def test_parse_list_devices(self):
        assert parse_voice_text("list devices") == ActionType.LIST_DEVICES

    def test_parse_start_training(self):
        assert parse_voice_text("start training now") == ActionType.START_TRAINING

    def test_parse_export_report(self):
        assert parse_voice_text("export report") == ActionType.EXPORT_REPORT

    def test_parse_unknown(self):
        assert parse_voice_text("do something random") == ActionType.UNKNOWN


class TestRiskClassification:
    """Test risk classification."""

    def test_status_query_is_low(self):
        assert classify_risk(ActionType.STATUS_QUERY) == CommandRisk.LOW

    def test_start_training_is_high(self):
        assert classify_risk(ActionType.START_TRAINING) == CommandRisk.HIGH

    def test_security_change_is_critical(self):
        assert classify_risk(ActionType.SECURITY_CHANGE) == CommandRisk.CRITICAL

    def test_unknown_is_critical(self):
        assert classify_risk(ActionType.UNKNOWN) == CommandRisk.CRITICAL


class TestLowRiskExecution:
    """Test low-risk commands execute directly."""

    def test_low_risk_queued(self):
        q = CommandQueue()
        cmd = q.submit("show me the status")
        assert cmd.status == CommandStatus.QUEUED
        assert cmd.risk_level == CommandRisk.LOW

    def test_low_risk_executes(self):
        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, lambda cmd: "All systems operational")
        q.submit("show me the status")
        result = q.execute_next()
        assert result is not None
        assert result.success is True
        assert result.status == CommandStatus.COMPLETED

    def test_low_risk_result_captured(self):
        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, lambda cmd: "Running OK")
        cmd = q.submit("status")
        q.execute_next()
        completed = q.get_status(cmd.command_id)
        assert completed.result == "Running OK"
        assert completed.status == CommandStatus.COMPLETED


class TestHighRiskConfirmation:
    """Test high-risk commands require confirmation."""

    def test_high_risk_awaits_confirmation(self):
        q = CommandQueue()
        cmd = q.submit("start training now")
        assert cmd.status == CommandStatus.AWAITING_CONFIRMATION

    def test_high_risk_does_not_execute_without_confirmation(self):
        q = CommandQueue()
        q.register_handler(ActionType.START_TRAINING, lambda cmd: "Training started")
        q.submit("start training now")
        result = q.execute_next()
        assert result is None  # Nothing to execute

    def test_high_risk_executes_after_confirmation(self):
        q = CommandQueue()
        q.register_handler(ActionType.START_TRAINING, lambda cmd: "Training started")
        cmd = q.submit("start training now")
        q.confirm(cmd.command_id, "HUMAN-001")
        result = q.execute_next()
        assert result is not None
        assert result.success is True

    def test_high_risk_rejection(self):
        q = CommandQueue()
        cmd = q.submit("start training now")
        rejected = q.reject(cmd.command_id, "HUMAN-001", "Not safe right now")
        assert rejected.status == CommandStatus.REJECTED
        assert rejected.error == "Not safe right now"


class TestCriticalRiskRejection:
    """Test critical risk commands are auto-rejected."""

    def test_critical_auto_rejected(self):
        q = CommandQueue()
        cmd = q.submit("something completely unknown")
        assert cmd.status == CommandStatus.REJECTED
        assert "governance token" in cmd.error.lower()

    def test_critical_not_in_queue(self):
        q = CommandQueue()
        q.submit("do something dangerous unknown")
        assert q.pending_count() == 0


class TestRetryLogic:
    """Test command retry on transient failure."""

    def test_retry_on_failure(self):
        call_count = {"n": 0}

        def flaky_handler(cmd):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("Transient error")
            return "Success on retry"

        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, flaky_handler)
        q.submit("status")

        # First attempt fails, retries
        r1 = q.execute_next()
        assert r1.success is False
        assert r1.status == CommandStatus.QUEUED

        # Second attempt fails, retries
        r2 = q.execute_next()
        assert r2.success is False

        # Third attempt succeeds
        r3 = q.execute_next()
        assert r3.success is True
        assert r3.result == "Success on retry"

    def test_max_retries_exhausted(self):
        def always_fail(cmd):
            raise RuntimeError("Permanent error")

        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, always_fail)
        q.submit("status")

        for _ in range(3):
            r = q.execute_next()

        assert r.success is False
        assert r.status == CommandStatus.FAILED


class TestQueueManagement:
    """Test queue operations."""

    def test_multiple_commands(self):
        q = CommandQueue()
        q.submit("status")
        q.submit("list devices")
        assert q.pending_count() == 2

    def test_fifo_order(self):
        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, lambda cmd: "status ok")
        q.register_handler(ActionType.LIST_DEVICES, lambda cmd: "2 devices")
        q.submit("status")
        q.submit("list devices")

        r1 = q.execute_next()
        assert r1.result == "status ok"

        r2 = q.execute_next()
        assert r2.result == "2 devices"

    def test_history_after_completion(self):
        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, lambda cmd: "ok")
        q.submit("status")
        q.execute_next()
        assert len(q.get_history()) == 1
        assert q.pending_count() == 0


class TestAuditTrail:
    """Test audit trail generation."""

    def test_audit_entries_created(self):
        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, lambda cmd: "ok")
        q.submit("status")
        q.execute_next()
        trail = q.get_audit_trail()
        assert len(trail) >= 2  # SUBMITTED + COMPLETED
        actions = [e.action for e in trail]
        assert "SUBMITTED" in actions
        assert "COMPLETED" in actions

    def test_audit_hash_generated(self):
        q = CommandQueue()
        q.register_handler(ActionType.STATUS_QUERY, lambda cmd: "ok")
        cmd = q.submit("status")
        q.execute_next()
        completed = q.get_status(cmd.command_id)
        assert completed.audit_hash is not None
        assert len(completed.audit_hash) == 32


class TestGovernanceGuards:
    """Test governance guard functions."""

    def test_cannot_execute_directly(self):
        can_exec, reason = can_voice_execute_directly()
        assert can_exec is False
        assert "commandqueue" in reason.lower()

    def test_cannot_bypass_confirmation(self):
        can_bypass, reason = can_voice_bypass_confirmation()
        assert can_bypass is False
        assert "confirmation" in reason.lower()
