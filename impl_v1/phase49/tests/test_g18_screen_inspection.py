# test_g18_screen_inspection.py
"""Tests for G18 Screen Inspection governor."""

import pytest

from impl_v1.phase49.governors.g18_screen_inspection import (
    InspectionMode,
    InspectionStatus,
    FindingType,
    ScreenInspectionRequest,
    ScreenFinding,
    InspectionResult,
    create_inspection_request,
    can_execute_inspection,
    authorize_inspection,
    perform_inspection,
    can_inspection_interact,
    get_inspection_result,
    clear_inspection_store,
)


class TestInspectionMode:
    """Tests for InspectionMode enum."""
    
    def test_only_read_only_mode(self):
        assert InspectionMode.READ_ONLY.value == "READ_ONLY"
    
    def test_enum_has_single_member(self):
        # Should only have READ_ONLY
        members = list(InspectionMode)
        assert len(members) == 1


class TestInspectionStatus:
    """Tests for InspectionStatus enum."""
    
    def test_has_pending(self):
        assert InspectionStatus.PENDING.value == "PENDING"
    
    def test_has_authorized(self):
        assert InspectionStatus.AUTHORIZED.value == "AUTHORIZED"
    
    def test_has_in_progress(self):
        assert InspectionStatus.IN_PROGRESS.value == "IN_PROGRESS"
    
    def test_has_completed(self):
        assert InspectionStatus.COMPLETED.value == "COMPLETED"
    
    def test_has_denied(self):
        assert InspectionStatus.DENIED.value == "DENIED"


class TestFindingType:
    """Tests for FindingType enum."""
    
    def test_has_window_detected(self):
        assert FindingType.WINDOW_DETECTED.value == "WINDOW_DETECTED"
    
    def test_has_browser_detected(self):
        assert FindingType.BROWSER_DETECTED.value == "BROWSER_DETECTED"
    
    def test_has_form_detected(self):
        assert FindingType.FORM_DETECTED.value == "FORM_DETECTED"


class TestCreateInspectionRequest:
    """Tests for create_inspection_request function."""
    
    def setup_method(self):
        clear_inspection_store()
    
    def test_creates_request(self):
        request = create_inspection_request(
            device_id="DEV-123",
            user_id="USR-456",
            device_trusted=True,
            user_verified=True,
        )
        assert isinstance(request, ScreenInspectionRequest)
    
    def test_request_has_id(self):
        request = create_inspection_request("dev", "user", True, True)
        assert request.request_id.startswith("INS-")
    
    def test_mode_is_always_read_only(self):
        request = create_inspection_request("dev", "user", True, True)
        assert request.mode == InspectionMode.READ_ONLY
    
    def test_initial_status_is_pending(self):
        request = create_inspection_request("dev", "user", True, True)
        assert request.status == InspectionStatus.PENDING


class TestCanExecuteInspection:
    """Tests for can_execute_inspection function."""
    
    def setup_method(self):
        clear_inspection_store()
    
    def test_trusted_verified_allowed(self):
        request = create_inspection_request("dev", "user", True, True)
        allowed, reason = can_execute_inspection(request)
        assert allowed == True
    
    def test_untrusted_device_denied(self):
        request = create_inspection_request("dev", "user", False, True)
        allowed, reason = can_execute_inspection(request)
        assert allowed == False
        assert "not trusted" in reason
    
    def test_unverified_user_denied(self):
        request = create_inspection_request("dev", "user", True, False)
        allowed, reason = can_execute_inspection(request)
        assert allowed == False
        assert "not verified" in reason


class TestAuthorizeInspection:
    """Tests for authorize_inspection function."""
    
    def setup_method(self):
        clear_inspection_store()
    
    def test_authorizes_valid_request(self):
        request = create_inspection_request("dev", "user", True, True)
        result = authorize_inspection(request.request_id)
        assert result.status == InspectionStatus.AUTHORIZED
    
    def test_denies_untrusted_request(self):
        request = create_inspection_request("dev", "user", False, True)
        result = authorize_inspection(request.request_id)
        assert result.status == InspectionStatus.DENIED
    
    def test_invalid_id_returns_none(self):
        result = authorize_inspection("INS-INVALID")
        assert result is None


class TestPerformInspection:
    """Tests for perform_inspection function."""
    
    def setup_method(self):
        clear_inspection_store()
    
    def test_requires_authorization(self):
        request = create_inspection_request("dev", "user", True, True)
        # Not authorized yet
        result = perform_inspection(request.request_id)
        assert result is None
    
    def test_performs_with_authorization(self):
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert isinstance(result, InspectionResult)
    
    def test_result_has_voice_explanation_en(self):
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert len(result.voice_explanation_en) > 0
    
    def test_result_has_voice_explanation_hi(self):
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert len(result.voice_explanation_hi) > 0
    
    def test_mock_findings_processed(self):
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        mock_findings = [
            {"type": "BROWSER_DETECTED", "description": "Chrome browser", "confidence": 0.9},
            {"type": "FORM_DETECTED", "description": "Login form", "confidence": 0.85},
        ]
        result = perform_inspection(request.request_id, _mock_findings=mock_findings)
        assert len(result.findings) == 2
    
    def test_result_is_stored(self):
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        perform_inspection(request.request_id)
        result = get_inspection_result(request.request_id)
        assert result is not None


class TestCanInspectionInteract:
    """Tests for can_inspection_interact function."""
    
    def test_returns_tuple(self):
        result = can_inspection_interact()
        assert isinstance(result, tuple)
    
    def test_cannot_interact(self):
        can_interact, reason = can_inspection_interact()
        assert can_interact == False
    
    def test_has_reason(self):
        _, reason = can_inspection_interact()
        assert "READ-ONLY" in reason or "no" in reason.lower()
    
    def test_no_clicks_mentioned(self):
        _, reason = can_inspection_interact()
        assert "click" in reason.lower() or "interaction" in reason.lower()
