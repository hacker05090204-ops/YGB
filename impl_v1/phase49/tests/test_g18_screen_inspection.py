"""Tests for G18 screen inspection infrastructure gating."""

import pytest

from impl_v1.phase49.governors.g02_browser_types import BrowserProfile
from impl_v1.phase49.governors.g18_screen_inspection import (
    InspectionMode,
    InspectionResult,
    InspectionStatus,
    RealBackendNotConfiguredError,
    SCREEN_INSPECTION_PROVISIONING_MESSAGE,
    ScreenInspectionRequest,
    ScreenInspector,
    authorize_inspection,
    can_execute_inspection,
    can_inspection_interact,
    clear_inspection_store,
    create_inspection_request,
    get_inspection_mode_info,
    get_inspection_result,
    perform_inspection,
)


def _safe_profile() -> BrowserProfile:
    return BrowserProfile(
        profile_id="PROFILE-SAFE",
        browser_type="CHROMIUM",
        headless=True,
        sandboxed=True,
        allowed_domains=["example.com"],
    )


def _unsafe_profile() -> BrowserProfile:
    return BrowserProfile(
        profile_id="PROFILE-UNSAFE",
        browser_type="CHROMIUM",
        headless=False,
        sandboxed=True,
        allowed_domains=["example.com"],
    )


class TestInspectionMode:
    def test_only_passive_only_mode(self):
        assert InspectionMode.PASSIVE_ONLY.value == "PASSIVE_ONLY"

    def test_read_only_is_legacy_alias(self):
        assert InspectionMode.READ_ONLY is InspectionMode.PASSIVE_ONLY


class TestModeInfo:
    def test_mode_info_is_truthful(self):
        info = get_inspection_mode_info()
        assert info["is_stub"] is False
        assert info["native_capture_available"] is False
        assert info["mode"] == "INFRASTRUCTURE_GATED_PASSIVE_ONLY"
        assert "fail closed" in info["description"].lower()


class TestInspectionRequestFlow:
    def setup_method(self):
        clear_inspection_store()

    def test_creates_request(self):
        request = create_inspection_request(
            "DEV-123",
            "USR-456",
            True,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        assert isinstance(request, ScreenInspectionRequest)
        assert request.request_id.startswith("INS-")
        assert request.mode is InspectionMode.PASSIVE_ONLY
        assert request.status is InspectionStatus.PENDING

    def test_trusted_verified_allowed(self):
        request = create_inspection_request(
            "dev",
            "user",
            True,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        allowed, reason = can_execute_inspection(request)
        assert allowed is True
        assert "passive observation" in reason.lower()

    def test_untrusted_device_denied(self):
        request = create_inspection_request(
            "dev",
            "user",
            False,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        allowed, reason = can_execute_inspection(request)
        assert allowed is False
        assert "not trusted" in reason

    def test_authorizes_valid_request(self):
        request = create_inspection_request(
            "dev",
            "user",
            True,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        result = authorize_inspection(request.request_id)
        assert result is not None
        assert result.status is InspectionStatus.AUTHORIZED

    def test_invalid_id_returns_none(self):
        assert authorize_inspection("INS-INVALID") is None


class TestScreenInspector:
    def test_inspection_result_contract_shape(self):
        result = InspectionResult(
            inspection_id="INSPECT-1",
            target_url="https://example.com",
            inspected_at="2026-04-06T00:00:00+00:00",
            elements_found=0,
            issues_detected=[],
            status="BACKEND_NOT_CONFIGURED",
        )
        assert result.inspection_id == "INSPECT-1"
        assert result.target_url == "https://example.com"
        assert result.elements_found == 0
        assert result.issues_detected == []

    def test_unsafe_profile_blocked_before_infrastructure_error(self):
        inspector = ScreenInspector()
        with pytest.raises(PermissionError, match="Unsafe browser profile blocked"):
            inspector.inspect(_unsafe_profile(), "https://example.com")

    def test_safe_profile_raises_real_backend_not_configured(self):
        inspector = ScreenInspector()
        with pytest.raises(RealBackendNotConfiguredError, match=SCREEN_INSPECTION_PROVISIONING_MESSAGE):
            inspector.inspect(_safe_profile(), "https://example.com")

    def test_passive_only_contract_is_explicit(self):
        contract = ScreenInspector.passive_observation_contract()
        assert contract["mutation_allowed"] is False
        assert contract["regex_xss_scanning_allowed"] is False
        assert contract["nmap_allowed"] is False
        assert contract["automated_exploit_detection_allowed"] is False


class TestPerformInspection:
    def setup_method(self):
        clear_inspection_store()

    def test_requires_authorization(self):
        request = create_inspection_request(
            "dev",
            "user",
            True,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        assert perform_inspection(request.request_id) is None

    def test_authorized_inspection_raises_real_backend_not_configured(self):
        request = create_inspection_request(
            "dev",
            "user",
            True,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        authorize_inspection(request.request_id)
        with pytest.raises(RealBackendNotConfiguredError, match=SCREEN_INSPECTION_PROVISIONING_MESSAGE):
            perform_inspection(request.request_id)

    def test_no_result_stored_when_backend_unconfigured(self):
        request = create_inspection_request(
            "dev",
            "user",
            True,
            True,
            profile=_safe_profile(),
            target_url="https://example.com",
        )
        authorize_inspection(request.request_id)
        with pytest.raises(RealBackendNotConfiguredError):
            perform_inspection(request.request_id)
        assert get_inspection_result(request.request_id) is None


class TestCanInspectionInteract:
    def test_returns_tuple(self):
        assert isinstance(can_inspection_interact(), tuple)

    def test_cannot_interact(self):
        can_interact, _ = can_inspection_interact()
        assert can_interact is False

    def test_reason_mentions_passive_only_controls(self):
        _, reason = can_inspection_interact()
        assert "passive only" in reason.lower()
        assert "nmap" in reason.lower()
        assert "regex xss" in reason.lower()
