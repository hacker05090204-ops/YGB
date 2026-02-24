# test_g15_cve_api.py
"""Tests for G15 CVE API governor."""

import pytest
from datetime import datetime, UTC

from impl_v1.phase49.governors.g15_cve_api import (
    CVEAPIConfig,
    CVEAPIResult,
    APIStatus,
    fetch_cves_passive,
    can_cve_trigger_execution,
    get_config,
    clear_api_cache,
    get_risk_context,
    DEFAULT_API_KEY,
)
from impl_v1.phase49.governors.g07_cve_intelligence import (
    clear_cache as clear_cve_cache,
)


class TestCVEAPIConfig:
    """Tests for CVEAPIConfig dataclass."""
    
    def test_config_exists(self):
        config = CVEAPIConfig(api_key="test-key")
        assert config is not None
    
    def test_config_has_api_key(self):
        config = CVEAPIConfig(api_key="test-key")
        assert config.api_key == "test-key"
    
    def test_config_has_default_base_url(self):
        config = CVEAPIConfig(api_key="test")
        assert "nvd.nist.gov" in config.base_url
    
    def test_config_has_default_timeout(self):
        config = CVEAPIConfig(api_key="test")
        assert config.timeout == 30
    
    def test_config_has_cache_ttl(self):
        config = CVEAPIConfig(api_key="test")
        assert config.cache_ttl_hours == 24


class TestAPIStatus:
    """Tests for APIStatus enum."""
    
    def test_has_connected(self):
        assert APIStatus.CONNECTED.value == "CONNECTED"
    
    def test_has_degraded(self):
        assert APIStatus.DEGRADED.value == "DEGRADED"
    
    def test_has_offline(self):
        assert APIStatus.OFFLINE.value == "OFFLINE"
    
    def test_has_invalid_key(self):
        assert APIStatus.INVALID_KEY.value == "INVALID_KEY"


class TestFetchCVEsPassive:
    """Tests for fetch_cves_passive function."""
    
    def setup_method(self):
        clear_api_cache()
        clear_cve_cache()
    
    def test_returns_cve_api_result(self):
        result = fetch_cves_passive("apache")
        assert isinstance(result, CVEAPIResult)

    def test_result_has_result_id(self):
        result = fetch_cves_passive("nginx")
        assert result.result_id.startswith("API-") or result.result_id.startswith("CACHE-") or result.result_id.startswith("ERR-")

    def test_result_without_key_returns_invalid_key(self):
        """Without CVE_API_KEY, fetch_cves_passive returns INVALID_KEY status."""
        import os
        original = os.environ.pop("CVE_API_KEY", None)
        try:
            clear_api_cache()
            result = fetch_cves_passive("test")
            assert result.status == APIStatus.INVALID_KEY
        finally:
            if original:
                os.environ["CVE_API_KEY"] = original
    
    def test_result_has_status(self):
        result = fetch_cves_passive("test")
        assert isinstance(result.status, APIStatus)
    
    def test_result_has_timestamp(self):
        result = fetch_cves_passive("test")
        assert result.timestamp is not None
    
    def test_mock_response_connected(self):
        config = CVEAPIConfig(api_key="test-key-for-mock")
        mock = {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": "CVE-2024-1234",
                        "descriptions": [{"value": "Test vuln"}],
                        "metrics": {
                            "cvssMetricV31": [{"cvssData": {"baseScore": 9.8}}]
                        },
                    }
                }
            ]
        }
        result = fetch_cves_passive("test", config=config, _mock_response=mock)
        assert result.status == APIStatus.CONNECTED
    
    def test_mock_response_has_records(self):
        config = CVEAPIConfig(api_key="test-key-for-mock")
        mock = {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": "CVE-2024-5678",
                        "descriptions": [{"value": "Another vuln"}],
                        "metrics": {
                            "cvssMetricV31": [{"cvssData": {"baseScore": 7.5}}]
                        },
                    }
                }
            ]
        }
        result = fetch_cves_passive("test", config=config, _mock_response=mock)
        assert len(result.records) == 1
    
    def test_mock_error_returns_offline(self):
        config = CVEAPIConfig(api_key="test-key-for-mock")
        mock = {"error": "Connection refused"}
        result = fetch_cves_passive("test", config=config, _mock_response=mock)
        assert result.status == APIStatus.OFFLINE
    
    def test_mock_invalid_key_returns_invalid_key(self):
        config = CVEAPIConfig(api_key="test-key-for-mock")
        mock = {"error": "Invalid API key"}
        result = fetch_cves_passive("test", config=config, _mock_response=mock)
        assert result.status == APIStatus.INVALID_KEY
    
    def test_caching_works(self):
        config = CVEAPIConfig(api_key="test-key-for-mock")
        mock = {"vulnerabilities": []}
        result1 = fetch_cves_passive("cached-test", config=config, _mock_response=mock)
        result2 = fetch_cves_passive("cached-test", config=config)
        assert result2.from_cache == True


class TestCanCVETriggerExecution:
    """Tests for can_cve_trigger_execution function."""
    
    def test_returns_tuple(self):
        result = can_cve_trigger_execution()
        assert isinstance(result, tuple)
    
    def test_cannot_trigger_execution(self):
        can_trigger, reason = can_cve_trigger_execution()
        assert can_trigger == False
    
    def test_has_reason(self):
        can_trigger, reason = can_cve_trigger_execution()
        assert "PASSIVE" in reason or "passive" in reason.lower()


class TestGetRiskContext:
    """Tests for get_risk_context function."""
    
    def setup_method(self):
        clear_api_cache()
        clear_cve_cache()
    
    def test_empty_result_returns_unknown(self):
        result = CVEAPIResult(
            result_id="test",
            status=APIStatus.DEGRADED,
            records=tuple(),
            from_cache=False,
            error_message=None,
            timestamp=datetime.now(UTC).isoformat(),
        )
        context = get_risk_context(result)
        assert context["risk_level"] == "UNKNOWN"
    
    def test_returns_cve_count(self):
        result = CVEAPIResult(
            result_id="test",
            status=APIStatus.DEGRADED,
            records=tuple(),
            from_cache=False,
            error_message=None,
            timestamp=datetime.now(UTC).isoformat(),
        )
        context = get_risk_context(result)
        assert "cve_count" in context


class TestDefaultAPIKey:
    """Tests for default API key removal — no hardcoded keys."""
    
    def test_default_key_is_empty(self):
        """DEFAULT_API_KEY must be empty — no hardcoded secrets."""
        assert DEFAULT_API_KEY == ""
    
    def test_default_key_is_string(self):
        assert isinstance(DEFAULT_API_KEY, str)
    
    def test_get_config_fails_without_env(self):
        """get_config must fail-closed when CVE_API_KEY not set."""
        import os
        original = os.environ.pop("CVE_API_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="CVE_API_KEY"):
                get_config()
        finally:
            if original:
                os.environ["CVE_API_KEY"] = original
