# Test G29: Real Voice Input (STT)
"""
Tests for voice STT governor.

100% coverage required.
"""

import pytest
from impl_v1.phase49.governors.g29_voice_stt import (
    VoiceIntent,
    VoiceState,
    AudioQuality,
    VoiceCommand,
    VoiceSession,
    IntentResult,
    can_voice_execute,
    can_voice_approve,
    can_voice_click,
    can_voice_submit,
    can_voice_bypass_dashboard,
    DEFAULT_WAKE_WORD,
    STOP_HOTWORDS,
    SUPPORTED_WAKE_WORDS,
    assess_audio_quality,
    apply_noise_filter,
    parse_intent,
    VoiceInputEngine,
    create_voice_engine,
    is_voice_supported,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_voice_execute_always_false(self):
        """Guard: Voice cannot execute."""
        assert can_voice_execute() is False
    
    def test_can_voice_approve_always_false(self):
        """Guard: Voice cannot approve."""
        assert can_voice_approve() is False
    
    def test_can_voice_click_always_false(self):
        """Guard: Voice cannot click."""
        assert can_voice_click() is False
    
    def test_can_voice_submit_always_false(self):
        """Guard: Voice cannot submit."""
        assert can_voice_submit() is False
    
    def test_can_voice_bypass_dashboard_always_false(self):
        """Guard: Voice cannot bypass dashboard."""
        assert can_voice_bypass_dashboard() is False


class TestAudioQuality:
    """Test audio quality assessment."""
    
    def test_good_quality(self):
        """Assess good quality audio."""
        quality = assess_audio_quality(0.8, 0.1)
        assert quality == AudioQuality.GOOD
    
    def test_fair_quality(self):
        """Assess fair quality audio."""
        quality = assess_audio_quality(0.4, 0.25)
        assert quality == AudioQuality.FAIR
    
    def test_poor_quality(self):
        """Assess poor quality audio."""
        quality = assess_audio_quality(0.2, 0.5)
        assert quality == AudioQuality.POOR
    
    def test_unusable_quality(self):
        """Assess unusable quality audio."""
        quality = assess_audio_quality(0.05, 0.8)
        assert quality == AudioQuality.UNUSABLE
    
    def test_apply_noise_filter(self):
        """Apply noise filter."""
        raw = b"audio data"
        filtered = apply_noise_filter(raw)
        assert filtered == raw  # Mock returns as-is


class TestIntentParsing:
    """Test intent parsing."""
    
    def test_parse_stop_intent(self):
        """Parse stop intent."""
        intent, confidence, params = parse_intent("stop")
        assert intent == VoiceIntent.STOP
        assert confidence == 1.0
    
    def test_parse_stop_hotwords(self):
        """Parse all stop hotwords."""
        for word in STOP_HOTWORDS:
            intent, _, _ = parse_intent(word)
            assert intent == VoiceIntent.STOP
    
    def test_parse_set_target(self):
        """Parse set target intent."""
        intent, confidence, params = parse_intent("set target example.com")
        assert intent == VoiceIntent.SET_TARGET
        assert "value" in params
    
    def test_parse_status(self):
        """Parse status intent."""
        intent, _, _ = parse_intent("what's the status")
        assert intent == VoiceIntent.ASK_STATUS
    
    def test_parse_discovery(self):
        """Parse discovery intent."""
        intent, _, _ = parse_intent("discover HackerOne")
        assert intent == VoiceIntent.REQUEST_DISCOVERY
    
    def test_parse_report(self):
        """Parse report intent."""
        intent, _, _ = parse_intent("generate report")
        assert intent == VoiceIntent.REQUEST_REPORT
    
    def test_parse_toggle_voice(self):
        """Parse toggle voice intent."""
        intent, _, _ = parse_intent("toggle voice")
        assert intent == VoiceIntent.TOGGLE_VOICE
    
    def test_parse_unknown(self):
        """Parse unknown intent."""
        intent, confidence, _ = parse_intent("random gibberish xyz")
        assert intent == VoiceIntent.UNKNOWN
        assert confidence < 0.5


class TestVoiceEngine:
    """Test voice input engine."""
    
    def test_create_engine(self):
        """Create voice engine."""
        engine = create_voice_engine()
        assert engine.wake_word == DEFAULT_WAKE_WORD
    
    def test_create_engine_custom_wake(self):
        """Create engine with custom wake word."""
        engine = create_voice_engine("ok hunter")
        assert engine.wake_word == "ok hunter"
    
    def test_start_listening(self):
        """Start listening session."""
        engine = VoiceInputEngine()
        session = engine.start_listening()
        
        assert session.session_id.startswith("VOI-")
        assert session.state == VoiceState.LISTENING
        assert engine.state == VoiceState.LISTENING
    
    def test_stop_listening(self):
        """Stop listening session."""
        engine = VoiceInputEngine()
        engine.start_listening()
        ended = engine.stop_listening()
        
        assert ended.state == VoiceState.STOPPED
        assert ended.ended_at is not None
    
    def test_stop_listening_no_session(self):
        """Stop without active session."""
        engine = VoiceInputEngine()
        result = engine.stop_listening()
        assert result is None
    
    def test_detect_wake_word(self):
        """Detect wake word."""
        engine = VoiceInputEngine()
        assert engine.detect_wake_word("hey hunter start") is True
        assert engine.detect_wake_word("hello world") is False
    
    def test_detect_stop_hotword(self):
        """Detect stop hotword."""
        engine = VoiceInputEngine()
        assert engine.detect_stop_hotword("please stop") is True
        assert engine.detect_stop_hotword("continue") is False
    
    def test_process_speech(self):
        """Process speech input."""
        engine = VoiceInputEngine()
        engine.start_listening()
        
        command = engine.process_speech("set target example.com")
        
        assert command.intent == VoiceIntent.SET_TARGET
        assert command.command_id.startswith("CMD-")
        assert engine.state == VoiceState.LISTENING
    
    def test_process_speech_with_callback(self):
        """Process speech with intent callback."""
        received = []
        def on_intent(intent, params):
            received.append((intent, params))
        
        engine = VoiceInputEngine(on_intent=on_intent)
        engine.start_listening()
        engine.process_speech("status")
        
        assert len(received) == 1
        assert received[0][0] == VoiceIntent.ASK_STATUS
    
    def test_get_commands(self):
        """Get all commands."""
        engine = VoiceInputEngine()
        engine.start_listening()
        engine.process_speech("status")
        engine.process_speech("report")
        
        commands = engine.get_commands()
        assert len(commands) == 2
    
    def test_route_to_dashboard(self):
        """Route command to dashboard."""
        engine = VoiceInputEngine()
        engine.start_listening()
        command = engine.process_speech("status")
        
        def handler(intent, params):
            return "Status: 50% complete"
        
        result = engine.route_to_dashboard(command, handler)
        
        assert result.routed_to == "DASHBOARD"
        assert result.success is True
        assert result.response_text == "Status: 50% complete"
    
    def test_route_to_dashboard_error(self):
        """Route handles errors."""
        engine = VoiceInputEngine()
        engine.start_listening()
        command = engine.process_speech("status")
        
        def handler(intent, params):
            raise ValueError("Test error")
        
        result = engine.route_to_dashboard(command, handler)
        
        assert result.success is False
        assert "Test error" in result.response_text


class TestConstants:
    """Test constant definitions."""
    
    def test_default_wake_word(self):
        """Default wake word defined."""
        assert DEFAULT_WAKE_WORD == "hey hunter"
    
    def test_stop_hotwords(self):
        """Stop hotwords defined."""
        assert len(STOP_HOTWORDS) > 0
        assert "stop" in STOP_HOTWORDS
    
    def test_supported_wake_words(self):
        """Supported wake words defined."""
        assert len(SUPPORTED_WAKE_WORDS) > 0
    
    def test_is_voice_supported(self):
        """Voice support check."""
        assert is_voice_supported() is True


class TestDataclasses:
    """Test dataclass immutability."""
    
    def test_voice_command_frozen(self):
        """VoiceCommand is immutable."""
        cmd = VoiceCommand(
            "CMD-1", "test", VoiceIntent.UNKNOWN, 0.5,
            (), "2026-01-28T00:00:00Z", AudioQuality.GOOD
        )
        with pytest.raises(Exception):
            cmd.raw_text = "changed"
    
    def test_voice_session_frozen(self):
        """VoiceSession is immutable."""
        session = VoiceSession(
            "VOI-1", "2026-01-28T00:00:00Z", None,
            VoiceState.IDLE, 0, "hey hunter"
        )
        with pytest.raises(Exception):
            session.state = VoiceState.LISTENING
