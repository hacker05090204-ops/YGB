# test_g18_screen_inspection.py
"""Tests for G18 Screen Inspection governor."""

import pytest

import impl_v1.phase49.governors.g18_screen_inspection as g18

from impl_v1.phase49.governors.g18_screen_inspection import (
    FindingType,
    InspectionMode,
    InspectionResult,
    InspectionStatus,
    ScreenFinding,
    ScreenInspectionRequest,
    authorize_inspection,
    can_execute_inspection,
    can_inspection_interact,
    clear_inspection_store,
    create_inspection_request,
    get_inspection_mode_info,
    get_inspection_result,
    perform_inspection,
)


def _finding(kind: FindingType, description: str) -> ScreenFinding:
    return ScreenFinding(
        finding_id="FND-TEST",
        finding_type=kind,
        description=description,
        location=None,
        confidence=0.95,
        timestamp="2026-03-08T00:00:00+00:00",
    )


class TestInspectionMode:
    def test_only_read_only_mode(self):
        assert InspectionMode.READ_ONLY.value == "READ_ONLY"

    def test_enum_has_single_member(self):
        assert len(list(InspectionMode)) == 1


class TestInspectionStatus:
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
    def test_has_window_detected(self):
        assert FindingType.WINDOW_DETECTED.value == "WINDOW_DETECTED"

    def test_has_browser_detected(self):
        assert FindingType.BROWSER_DETECTED.value == "BROWSER_DETECTED"

    def test_has_form_detected(self):
        assert FindingType.FORM_DETECTED.value == "FORM_DETECTED"


class TestModeInfo:
    def test_mode_info_is_truthful(self):
        info = get_inspection_mode_info()
        assert info["is_stub"] is False
        assert info["mode"] in {"LOCAL_READ_ONLY", "UNAVAILABLE_READ_ONLY"}
        assert isinstance(info["native_capture_available"], bool)
        assert len(info["description"]) > 0


class TestCreateInspectionRequest:
    def setup_method(self):
        clear_inspection_store()

    def test_creates_request(self):
        request = create_inspection_request("DEV-123", "USR-456", True, True)
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
    def setup_method(self):
        clear_inspection_store()

    def test_trusted_verified_allowed(self):
        request = create_inspection_request("dev", "user", True, True)
        allowed, _ = can_execute_inspection(request)
        assert allowed is True

    def test_untrusted_device_denied(self):
        request = create_inspection_request("dev", "user", False, True)
        allowed, reason = can_execute_inspection(request)
        assert allowed is False
        assert "not trusted" in reason

    def test_unverified_user_denied(self):
        request = create_inspection_request("dev", "user", True, False)
        allowed, reason = can_execute_inspection(request)
        assert allowed is False
        assert "not verified" in reason


class TestAuthorizeInspection:
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
        assert authorize_inspection("INS-INVALID") is None


class TestPerformInspection:
    def setup_method(self):
        clear_inspection_store()

    def test_requires_authorization(self):
        request = create_inspection_request("dev", "user", True, True)
        assert perform_inspection(request.request_id) is None

    def test_performs_with_authorization(self, monkeypatch):
        monkeypatch.setattr(
            g18,
            "_collect_live_findings",
            lambda: [_finding(FindingType.WINDOW_DETECTED, "Foreground window: Browser")],
        )
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert isinstance(result, InspectionResult)
        assert result.status == InspectionStatus.COMPLETED

    def test_result_has_voice_explanation_en(self, monkeypatch):
        monkeypatch.setattr(
            g18,
            "_collect_live_findings",
            lambda: [_finding(FindingType.TEXT_DETECTED, "Visible title text: Portal")],
        )
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert len(result.voice_explanation_en) > 0

    def test_result_has_voice_explanation_hi(self, monkeypatch):
        monkeypatch.setattr(
            g18,
            "_collect_live_findings",
            lambda: [_finding(FindingType.ELEMENT_DETECTED, "Screen frame captured at 1920x1080")],
        )
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert len(result.voice_explanation_hi) > 0

    def test_live_findings_processed(self, monkeypatch):
        monkeypatch.setattr(
            g18,
            "_collect_live_findings",
            lambda: [
                _finding(FindingType.BROWSER_DETECTED, "Browser-like foreground window detected"),
                _finding(FindingType.FORM_DETECTED, "Foreground window title suggests a form"),
            ],
        )
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert len(result.findings) == 2

    def test_result_is_stored(self, monkeypatch):
        monkeypatch.setattr(
            g18,
            "_collect_live_findings",
            lambda: [_finding(FindingType.WINDOW_DETECTED, "Foreground window: Browser")],
        )
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        perform_inspection(request.request_id)
        result = get_inspection_result(request.request_id)
        assert result is not None

    def test_unavailable_runtime_marks_request_denied(self, monkeypatch):
        def _raise():
            raise RuntimeError("capture unavailable")

        monkeypatch.setattr(g18, "_collect_live_findings", _raise)
        request = create_inspection_request("dev", "user", True, True)
        authorize_inspection(request.request_id)
        result = perform_inspection(request.request_id)
        assert result.status == InspectionStatus.DENIED
        assert "capture unavailable" in result.voice_explanation_en


class TestCanInspectionInteract:
    def test_returns_tuple(self):
        assert isinstance(can_inspection_interact(), tuple)

    def test_cannot_interact(self):
        can_interact, _ = can_inspection_interact()
        assert can_interact is False

    def test_has_reason(self):
        _, reason = can_inspection_interact()
        assert "READ-ONLY" in reason or "no" in reason.lower()

    def test_no_clicks_mentioned(self):
        _, reason = can_inspection_interact()
        assert "click" in reason.lower() or "interaction" in reason.lower()
