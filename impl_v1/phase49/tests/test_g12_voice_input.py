# test_g12_voice_input.py
"""Tests for G12: Voice Command Input"""

import pytest
from impl_v1.phase49.governors.g12_voice_input import (
    VoiceIntentType,
    VoiceInputStatus,
    VoiceIntent,
    extract_intent,
    validate_voice_input,
    is_forbidden_command,
    can_voice_trigger_execution,
)


class TestEnumClosure:
    def test_voice_intent_type_8_members(self):
        assert len(VoiceIntentType) == 8
    
    def test_voice_input_status_4_members(self):
        assert len(VoiceInputStatus) == 4


class TestForbiddenCommands:
    def test_execute_forbidden(self):
        forbidden, reason = is_forbidden_command("execute the attack")
        assert forbidden
    
    def test_run_forbidden(self):
        forbidden, reason = is_forbidden_command("run the exploit")
        assert forbidden
    
    def test_approve_forbidden(self):
        forbidden, reason = is_forbidden_command("approve this")
        assert forbidden
    
    def test_normal_allowed(self):
        forbidden, reason = is_forbidden_command("set target to example.com")
        assert not forbidden


class TestExtractIntent:
    def test_set_target(self):
        intent = extract_intent("target is example.com")
        assert intent.intent_type == VoiceIntentType.SET_TARGET
        assert intent.status == VoiceInputStatus.PARSED
        assert "example.com" in intent.extracted_value
    
    def test_set_scope(self):
        intent = extract_intent("scope to api endpoints only")
        assert intent.intent_type == VoiceIntentType.SET_SCOPE
        assert intent.status == VoiceInputStatus.PARSED
    
    def test_query_status(self):
        intent = extract_intent("what is the status")
        assert intent.intent_type == VoiceIntentType.QUERY_STATUS
    
    def test_query_progress(self):
        intent = extract_intent("what is the progress")
        assert intent.intent_type == VoiceIntentType.QUERY_PROGRESS
    
    def test_find_targets(self):
        intent = extract_intent("find targets for me")
        assert intent.intent_type == VoiceIntentType.FIND_TARGETS
    
    def test_unknown_intent(self):
        intent = extract_intent("random gibberish xyz")
        assert intent.intent_type == VoiceIntentType.UNKNOWN
        assert intent.status == VoiceInputStatus.INVALID


class TestBlockedCommands:
    def test_blocked_has_reason(self):
        intent = extract_intent("execute the attack now")
        assert intent.status == VoiceInputStatus.BLOCKED
        assert intent.block_reason is not None
    
    def test_blocked_confidence_zero(self):
        intent = extract_intent("run exploit")
        assert intent.confidence == 0.0


class TestValidateVoiceInput:
    def test_empty_input(self):
        intent = validate_voice_input("")
        assert intent.status == VoiceInputStatus.INVALID
        assert "Empty" in intent.block_reason
    
    def test_whitespace_only(self):
        intent = validate_voice_input("   ")
        assert intent.status == VoiceInputStatus.INVALID
    
    def test_valid_input(self):
        intent = validate_voice_input("target is test.com")
        assert intent.status == VoiceInputStatus.PARSED


class TestVoiceCannotExecute:
    def test_voice_cannot_trigger_execution(self):
        intent = extract_intent("target is example.com")
        can, reason = can_voice_trigger_execution(intent)
        assert not can
        assert "cannot trigger execution" in reason


class TestDataclassFrozen:
    def test_intent_frozen(self):
        intent = extract_intent("target is test.com")
        with pytest.raises(AttributeError):
            intent.intent_type = VoiceIntentType.UNKNOWN
