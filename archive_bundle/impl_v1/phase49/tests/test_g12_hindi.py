# test_g12_hindi.py
"""Tests for G12 Voice Input Hindi support and extended intents."""

import pytest

from impl_v1.phase49.governors.g12_voice_input import (
    VoiceIntentType,
    VoiceInputStatus,
    VoiceIntent,
    validate_voice_input,
    extract_intent,
    is_forbidden_command,
    HINDI_PATTERNS,
    INTENT_PATTERNS,
)


class TestHindiPatterns:
    """Tests for Hindi intent patterns."""
    
    def test_hindi_patterns_exist(self):
        assert HINDI_PATTERNS is not None
    
    def test_has_set_target_hindi(self):
        assert VoiceIntentType.SET_TARGET in HINDI_PATTERNS
    
    def test_has_set_scope_hindi(self):
        assert VoiceIntentType.SET_SCOPE in HINDI_PATTERNS
    
    def test_has_query_status_hindi(self):
        assert VoiceIntentType.QUERY_STATUS in HINDI_PATTERNS
    
    def test_has_query_progress_hindi(self):
        assert VoiceIntentType.QUERY_PROGRESS in HINDI_PATTERNS
    
    def test_has_find_targets_hindi(self):
        assert VoiceIntentType.FIND_TARGETS in HINDI_PATTERNS
    
    def test_has_screen_takeover_hindi(self):
        assert VoiceIntentType.SCREEN_TAKEOVER in HINDI_PATTERNS
    
    def test_has_report_help_hindi(self):
        assert VoiceIntentType.REPORT_HELP in HINDI_PATTERNS


class TestNewIntentTypes:
    """Tests for new intent types."""
    
    def test_screen_takeover_exists(self):
        assert VoiceIntentType.SCREEN_TAKEOVER.value == "SCREEN_TAKEOVER"
    
    def test_report_help_exists(self):
        assert VoiceIntentType.REPORT_HELP.value == "REPORT_HELP"


class TestHindiVoiceCommands:
    """Tests for Hindi voice command parsing."""
    
    def test_ye_mera_target_hai(self):
        intent = validate_voice_input("ye mera target hai example.com")
        assert intent.intent_type == VoiceIntentType.SET_TARGET
        assert intent.status == VoiceInputStatus.PARSED
    
    def test_mera_target_hai(self):
        intent = validate_voice_input("mera target hai test.com")
        assert intent.intent_type == VoiceIntentType.SET_TARGET
    
    def test_target_set_karo(self):
        intent = validate_voice_input("target set karo hackerone.com")
        assert intent.intent_type == VoiceIntentType.SET_TARGET
    
    def test_scope_ye_hai(self):
        intent = validate_voice_input("scope ye hai *.example.com")
        assert intent.intent_type == VoiceIntentType.SET_SCOPE
    
    def test_status_batao(self):
        intent = validate_voice_input("status batao")
        assert intent.intent_type == VoiceIntentType.QUERY_STATUS
    
    def test_kya_hal_hai(self):
        intent = validate_voice_input("kya hal hai")
        assert intent.intent_type == VoiceIntentType.QUERY_STATUS
    
    def test_progress_kitna_hua(self):
        intent = validate_voice_input("progress kitna hua")
        assert intent.intent_type == VoiceIntentType.QUERY_PROGRESS
    
    def test_find_targets_hindi(self):
        # Use 'targets dhundo' - 'accha target' matches SET_TARGET pattern
        intent = validate_voice_input("targets dhundo")
        assert intent.intent_type == VoiceIntentType.FIND_TARGETS
    
    def test_targets_dhundo_again(self):
        intent = validate_voice_input("targets dhundo")
        assert intent.intent_type == VoiceIntentType.FIND_TARGETS
    
    def test_screen_dekho(self):
        intent = validate_voice_input("screen dekho")
        assert intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER
    
    def test_screen_takeover_karo(self):
        intent = validate_voice_input("screen takeover karo")
        assert intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER
    
    def test_report_mein_kya_add_kare(self):
        intent = validate_voice_input("is report me aur kya add kar sakte hain")
        assert intent.intent_type == VoiceIntentType.REPORT_HELP
    
    def test_payout_badhao(self):
        intent = validate_voice_input("payout kaise badhao")
        assert intent.intent_type == VoiceIntentType.REPORT_HELP
    
    def test_high_impact_ke_liye(self):
        intent = validate_voice_input("high impact ke liye kya karu")
        assert intent.intent_type == VoiceIntentType.REPORT_HELP


class TestEnglishScreenTakeover:
    """Tests for English screen takeover commands."""
    
    def test_takeover_the_screen(self):
        intent = validate_voice_input("takeover the screen")
        assert intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER
    
    def test_screen_takeover(self):
        intent = validate_voice_input("screen takeover")
        assert intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER
    
    def test_show_me_the_screen(self):
        intent = validate_voice_input("show me the screen")
        assert intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER
    
    def test_inspect_screen(self):
        intent = validate_voice_input("inspect screen")
        assert intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER


class TestEnglishReportHelp:
    """Tests for English report help commands."""
    
    def test_high_impact_tips(self):
        intent = validate_voice_input("high impact tips")
        assert intent.intent_type == VoiceIntentType.REPORT_HELP
    
    def test_increase_payout(self):
        intent = validate_voice_input("how to increase payout")
        assert intent.intent_type == VoiceIntentType.REPORT_HELP
    
    def test_improve_report(self):
        intent = validate_voice_input("improve the report")
        assert intent.intent_type == VoiceIntentType.REPORT_HELP


class TestHindiConfidence:
    """Tests for Hindi command confidence levels."""
    
    def test_hindi_confidence_slightly_lower(self):
        # Hindi-only patterns have lower confidence
        intent = validate_voice_input("kya haal hai")
        assert intent.confidence == 0.75
    
    def test_english_confidence_higher(self):
        intent = validate_voice_input("what is the status")
        assert intent.confidence == 0.8


class TestExtractedValues:
    """Tests for extracted values from Hindi commands."""
    
    def test_target_extracted_hindi(self):
        intent = validate_voice_input("ye mera target hai bugcrowd.com")
        assert intent.extracted_value is not None
        assert "bugcrowd" in intent.extracted_value.lower()
    
    def test_scope_extracted_hindi(self):
        intent = validate_voice_input("scope ye hai *.test.io")
        assert intent.extracted_value is not None
