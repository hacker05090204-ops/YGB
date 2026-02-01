"""
Tests for Phase-14 Input Contracts.

Tests:
- ConnectorRequestType enum members
- ConnectorInput validation
- Required fields enforcement
"""
import pytest


class TestConnectorRequestTypeEnum:
    """Test ConnectorRequestType enum."""

    def test_has_status_check(self):
        """Has STATUS_CHECK member."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        assert hasattr(ConnectorRequestType, 'STATUS_CHECK')

    def test_has_readiness_check(self):
        """Has READINESS_CHECK member."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        assert hasattr(ConnectorRequestType, 'READINESS_CHECK')

    def test_has_full_evaluation(self):
        """Has FULL_EVALUATION member."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        assert hasattr(ConnectorRequestType, 'FULL_EVALUATION')

    def test_exactly_three_members(self):
        """ConnectorRequestType has exactly 3 members."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        assert len(ConnectorRequestType) == 3


class TestConnectorInputValidation:
    """Test ConnectorInput validation."""

    def test_valid_input(self):
        """Valid input passes validation."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import validate_input

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None
        )

        assert validate_input(input) is True

    def test_empty_bug_id_invalid(self):
        """Empty bug_id fails validation."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import validate_input

        input = ConnectorInput(
            bug_id="",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None
        )

        assert validate_input(input) is False

    def test_empty_target_id_invalid(self):
        """Empty target_id fails validation."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import validate_input

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None
        )

        assert validate_input(input) is False

    def test_empty_timestamp_invalid(self):
        """Empty timestamp fails validation."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import validate_input

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="",  # Empty timestamp
            handoff_decision=None
        )

        assert validate_input(input) is False


class TestConnectorInputFrozen:
    """Test ConnectorInput immutability."""

    def test_connector_input_is_frozen(self):
        """ConnectorInput is frozen."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None
        )

        with pytest.raises(Exception):
            input.bug_id = "MODIFIED"
