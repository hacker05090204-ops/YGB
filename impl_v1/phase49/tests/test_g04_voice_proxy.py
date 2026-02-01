# test_g04_voice_proxy.py
"""Tests for G04: Voice Proxy"""

import pytest
from impl_v1.phase49.governors.g04_voice_proxy import (
    VoiceOutputType,
    VoiceOutputStatus,
    VoiceOutputRequest,
    VoiceOutputResult,
    TTS_PROXY_URL,
    create_voice_request,
    build_tts_url,
    process_voice_request,
    reset_rate_limit,
    check_rate_limit,
    MAX_REQUESTS_PER_MINUTE,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_voice_output_type_5_members(self):
        assert len(VoiceOutputType) == 5
    
    def test_voice_output_status_4_members(self):
        assert len(VoiceOutputStatus) == 4


class TestProxyURL:
    """Test TTS proxy URL."""
    
    def test_proxy_url_set(self):
        assert TTS_PROXY_URL == "https://tts-five-iota.vercel.app/api/audio"


class TestCreateVoiceRequest:
    """Test voice request creation."""
    
    def test_request_has_id(self):
        request = create_voice_request("Hello world")
        assert request.request_id.startswith("VOI-")
    
    def test_default_type_is_explanation(self):
        request = create_voice_request("Test")
        assert request.output_type == VoiceOutputType.EXPLANATION
    
    def test_default_language_is_en(self):
        request = create_voice_request("Test")
        assert request.language == "en"
    
    def test_custom_output_type(self):
        request = create_voice_request("Alert!", VoiceOutputType.ALERT)
        assert request.output_type == VoiceOutputType.ALERT
    
    def test_custom_priority(self):
        request = create_voice_request("Urgent", priority=10)
        assert request.priority == 10


class TestBuildTTSUrl:
    """Test URL building."""
    
    def test_basic_url(self):
        request = create_voice_request("Hello", language="en")
        url = build_tts_url(request)
        assert TTS_PROXY_URL in url
        assert "text=Hello" in url
        assert "lang=en" in url
    
    def test_url_encoding(self):
        request = create_voice_request("Hello world!", language="en")
        url = build_tts_url(request)
        assert "%20" in url or "+" in url  # Space encoding


class TestProcessVoiceRequest:
    """Test voice request processing."""
    
    def setup_method(self):
        reset_rate_limit()
    
    def test_successful_request(self):
        request = create_voice_request("Test message")
        result = process_voice_request(request)
        assert result.status == VoiceOutputStatus.DELIVERED
        assert result.audio_url is not None
    
    def test_empty_text_fails(self):
        request = VoiceOutputRequest(
            request_id="VOI-TEST",
            output_type=VoiceOutputType.EXPLANATION,
            text="   ",  # Whitespace only
            language="en",
            priority=5,
        )
        result = process_voice_request(request)
        assert result.status == VoiceOutputStatus.FAILED
        assert "Empty text" in result.error_message
    
    def test_result_has_timestamp(self):
        request = create_voice_request("Test")
        result = process_voice_request(request)
        assert result.timestamp is not None


class TestRateLimiting:
    """Test rate limiting."""
    
    def setup_method(self):
        reset_rate_limit()
    
    def test_rate_limit_check_initially_true(self):
        assert check_rate_limit() is True
    
    def test_rate_limit_after_max_requests(self):
        # Process max requests
        for i in range(MAX_REQUESTS_PER_MINUTE):
            request = create_voice_request(f"Message {i}")
            process_voice_request(request)
        
        # Next request should be rate limited
        request = create_voice_request("One more")
        result = process_voice_request(request)
        assert result.status == VoiceOutputStatus.RATE_LIMITED


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def test_request_frozen(self):
        request = create_voice_request("Test")
        with pytest.raises(AttributeError):
            request.text = "Modified"
    
    def test_result_frozen(self):
        request = create_voice_request("Test")
        result = process_voice_request(request)
        with pytest.raises(AttributeError):
            result.status = VoiceOutputStatus.FAILED
