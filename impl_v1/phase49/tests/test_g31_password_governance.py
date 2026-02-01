# Test G31: Cryptographic Multilingual Password Governance
"""
Tests for password governance governor.

100% coverage required.
"""

import pytest
import time
from datetime import datetime, UTC, timedelta
from unittest.mock import patch
from impl_v1.phase49.governors.g31_password_governance import (
    PasswordStrength,
    TriggerType,
    ScriptType,
    PasswordPolicy,
    GeneratedPassword,
    VerificationResult,
    can_password_log,
    can_password_store_plaintext,
    can_password_bypass_expiry,
    can_password_reuse,
    can_password_execute,
    can_password_mutate_state,
    SCRIPT_CHARSETS,
    calculate_password_length,
    get_length_for_strength,
    normalize_unicode,
    get_script_category,
    validate_script_mixing,
    detect_homoglyph_attack,
    generate_salt,
    compute_password_hash,
    generate_password_id,
    PasswordGenerator,
    PasswordVerifier,
    should_challenge,
    create_password_generator,
    create_password_verifier,
    get_default_policy,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_password_log_always_false(self):
        """Guard: Passwords cannot be logged."""
        assert can_password_log() is False
    
    def test_can_password_store_plaintext_always_false(self):
        """Guard: Passwords cannot be stored in plaintext."""
        assert can_password_store_plaintext() is False
    
    def test_can_password_bypass_expiry_always_false(self):
        """Guard: Password expiry cannot be bypassed."""
        assert can_password_bypass_expiry() is False
    
    def test_can_password_reuse_always_false(self):
        """Guard: Passwords cannot be reused."""
        assert can_password_reuse() is False
    
    def test_can_password_execute_always_false(self):
        """Guard: Passwords cannot approve execution."""
        assert can_password_execute() is False
    
    def test_can_password_mutate_state_always_false(self):
        """Guard: Password system cannot mutate state."""
        assert can_password_mutate_state() is False


class TestCharacterSets:
    """Test character set definitions."""
    
    def test_all_script_types_have_charset(self):
        """All script types have a charset defined."""
        for script_type in ScriptType:
            assert script_type in SCRIPT_CHARSETS
            assert len(SCRIPT_CHARSETS[script_type]) > 0
    
    def test_english_upper_is_uppercase(self):
        """English upper charset is all uppercase."""
        charset = SCRIPT_CHARSETS[ScriptType.ENGLISH_UPPER]
        assert charset.isupper()
    
    def test_english_lower_is_lowercase(self):
        """English lower charset is all lowercase."""
        charset = SCRIPT_CHARSETS[ScriptType.ENGLISH_LOWER]
        assert charset.islower()
    
    def test_numbers_are_digits(self):
        """Numbers charset is all digits."""
        charset = SCRIPT_CHARSETS[ScriptType.NUMBERS]
        assert charset.isdigit()
    
    def test_hindi_chars_are_devanagari(self):
        """Hindi chars are Devanagari script."""
        charset = SCRIPT_CHARSETS[ScriptType.HINDI]
        for char in charset[:5]:
            assert get_script_category(char) == "DEVANAGARI"
    
    def test_telugu_chars_are_telugu(self):
        """Telugu chars are Telugu script."""
        charset = SCRIPT_CHARSETS[ScriptType.TELUGU]
        for char in charset[:5]:
            assert get_script_category(char) == "TELUGU"


class TestLengthDistribution:
    """Test length calculation with non-uniform distribution."""
    
    def test_calculate_length_base(self):
        """Calculate length with default args."""
        length = calculate_password_length(0.0, 1)
        assert 1 <= length <= 100
    
    def test_calculate_length_high_risk(self):
        """High risk increases length."""
        lengths = [calculate_password_length(0.9, 1) for _ in range(10)]
        avg = sum(lengths) / len(lengths)
        assert avg > 40  # Higher than base
    
    def test_calculate_length_many_users(self):
        """Many users increases length."""
        lengths = [calculate_password_length(0.0, 1000) for _ in range(10)]
        avg = sum(lengths) / len(lengths)
        assert avg > 35  # Higher than single user
    
    def test_calculate_length_clamped(self):
        """Length is clamped to 1-100."""
        # Even with extreme values, should be in range
        length = calculate_password_length(1.0, 10000, base_length=80)
        assert 1 <= length <= 100
    
    def test_get_length_minimal(self):
        """Minimal strength gives short password."""
        lengths = [get_length_for_strength(PasswordStrength.MINIMAL) for _ in range(20)]
        assert all(1 <= l <= 15 for l in lengths)
    
    def test_get_length_standard(self):
        """Standard strength gives medium password."""
        lengths = [get_length_for_strength(PasswordStrength.STANDARD) for _ in range(20)]
        assert all(24 <= l <= 39 for l in lengths)
    
    def test_get_length_high_entropy(self):
        """High entropy gives long password."""
        lengths = [get_length_for_strength(PasswordStrength.HIGH_ENTROPY) for _ in range(20)]
        assert all(50 <= l <= 65 for l in lengths)
    
    def test_get_length_maximum(self):
        """Maximum strength gives longest password."""
        lengths = [get_length_for_strength(PasswordStrength.MAXIMUM) for _ in range(20)]
        assert all(80 <= l <= 100 for l in lengths)
    
    def test_length_randomness(self):
        """Lengths should have variance (not deterministic)."""
        lengths = [get_length_for_strength(PasswordStrength.STANDARD) for _ in range(50)]
        unique_lengths = set(lengths)
        assert len(unique_lengths) > 1  # Not all same


class TestUnicodeNormalization:
    """Test Unicode normalization and homoglyph prevention."""
    
    def test_normalize_unicode_nfkc(self):
        """NFKC normalization is applied."""
        # Compatibility char should be normalized
        result = normalize_unicode("ﬁ")  # fi ligature
        assert result == "fi"
    
    def test_get_script_category_latin(self):
        """Latin chars detected correctly."""
        assert get_script_category("A") == "LATIN"
        assert get_script_category("z") == "LATIN"
    
    def test_get_script_category_devanagari(self):
        """Devanagari chars detected correctly."""
        assert get_script_category("अ") == "DEVANAGARI"
    
    def test_get_script_category_arabic(self):
        """Arabic chars detected correctly."""
        assert get_script_category("ا") == "ARABIC"
    
    def test_get_script_category_telugu(self):
        """Telugu chars detected correctly."""
        assert get_script_category("అ") == "TELUGU"
    
    def test_get_script_category_cjk(self):
        """CJK chars detected correctly."""
        assert get_script_category("中") == "CJK"
    
    def test_get_script_category_hiragana(self):
        """Hiragana chars detected correctly."""
        assert get_script_category("あ") == "HIRAGANA"
    
    def test_get_script_category_katakana(self):
        """Katakana chars detected correctly."""
        assert get_script_category("ア") == "KATAKANA"
    
    def test_get_script_category_digit(self):
        """Digits detected correctly."""
        assert get_script_category("5") == "DIGIT"
    
    def test_get_script_category_symbol(self):
        """Symbols detected correctly."""
        assert get_script_category("@") == "SYMBOL"
    
    def test_get_script_category_unknown(self):
        """Unknown chars may return SYMBOL or None."""
        # Control character - isalnum() returns False so it's classified as SYMBOL
        result = get_script_category("\x00")
        # NULL char is not alphanumeric, so classified as SYMBOL
        assert result == "SYMBOL" or result is None
    
    def test_validate_script_mixing_pass(self):
        """Valid script mixing passes."""
        # English + Hindi + Number
        password = "ABCअआइ123"
        assert validate_script_mixing(password, min_scripts=3) is True
    
    def test_validate_script_mixing_fail(self):
        """Insufficient scripts fails."""
        password = "ABC123"  # Only LATIN + DIGIT
        assert validate_script_mixing(password, min_scripts=3) is False
    
    def test_detect_homoglyph_attack_clean(self):
        """Clean password has no homoglyph attack."""
        password = "ABCअआइ123"
        assert detect_homoglyph_attack(password) is False
    
    def test_get_script_category_gurmukhi(self):
        """Gurmukhi chars detected correctly."""
        assert get_script_category("ਅ") == "GURMUKHI"
    
    def test_get_script_category_gujarati(self):
        """Gujarati chars detected correctly."""
        assert get_script_category("અ") == "GUJARATI"


class TestPasswordGeneration:
    """Test password generation."""
    
    def test_generate_salt_length(self):
        """Salt has correct length."""
        salt = generate_salt()
        assert len(salt) > 30  # Base64 of 32 bytes
    
    def test_generate_salt_unique(self):
        """Each salt is unique."""
        salts = [generate_salt() for _ in range(10)]
        assert len(set(salts)) == 10
    
    def test_compute_password_hash(self):
        """Hash is computed correctly."""
        password = "test123"
        salt = generate_salt()
        hash1 = compute_password_hash(password, salt)
        hash2 = compute_password_hash(password, salt)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex
    
    def test_compute_hash_different_salt(self):
        """Different salt = different hash."""
        password = "test123"
        salt1 = generate_salt()
        salt2 = generate_salt()
        hash1 = compute_password_hash(password, salt1)
        hash2 = compute_password_hash(password, salt2)
        assert hash1 != hash2
    
    def test_generate_password_id(self):
        """Password ID has correct format."""
        pid = generate_password_id()
        assert pid.startswith("PWD-")
        assert len(pid) == 4 + 32  # PWD- + 32 hex chars
    
    def test_generator_create(self):
        """Create generator with defaults."""
        gen = create_password_generator()
        assert gen.min_scripts == 3
        assert gen.max_scripts == 5
        assert gen.expiry_seconds == 300
    
    def test_generator_generate_password(self):
        """Generate a password."""
        gen = PasswordGenerator()
        plaintext, record = gen.generate()
        
        assert len(plaintext) > 0
        assert record.password_id.startswith("PWD-")
        assert record.length == len(plaintext)
        assert record.is_used is False
        assert len(record.scripts_used) >= 3
    
    def test_generator_password_not_stored_plaintext(self):
        """Plaintext is NOT stored in record."""
        gen = PasswordGenerator()
        plaintext, record = gen.generate()
        
        # Record should only have hash, not plaintext
        assert not hasattr(record, "plaintext")
        assert record.password_hash != plaintext
    
    def test_generator_scripts_minimum(self):
        """At least min_scripts are used."""
        gen = PasswordGenerator(min_scripts=4)
        _, record = gen.generate()
        assert len(record.scripts_used) >= 4
    
    def test_generator_with_risk_score(self):
        """Risk score affects length."""
        gen = PasswordGenerator()
        _, record = gen.generate(risk_score=0.9, user_count=100)
        assert record.length > 30  # Higher than standard base
    
    def test_generator_with_trigger(self):
        """Trigger is recorded."""
        gen = PasswordGenerator()
        _, record = gen.generate(trigger=TriggerType.NEW_DEVICE)
        assert record.trigger == TriggerType.NEW_DEVICE
    
    def test_generator_get_record(self):
        """Get record by ID."""
        gen = PasswordGenerator()
        _, record = gen.generate()
        
        retrieved = gen.get_record(record.password_id)
        assert retrieved == record
    
    def test_generator_get_record_not_found(self):
        """Get non-existent record returns None."""
        gen = PasswordGenerator()
        assert gen.get_record("INVALID-ID") is None
    
    def test_generator_each_password_unique(self):
        """Each generated password is unique."""
        gen = PasswordGenerator()
        passwords = [gen.generate()[0] for _ in range(10)]
        assert len(set(passwords)) == 10


class TestPasswordVerification:
    """Test password verification."""
    
    def test_create_verifier(self):
        """Create verifier."""
        gen = PasswordGenerator()
        verifier = create_password_verifier(gen)
        assert verifier.generator == gen
    
    def test_verify_correct_password(self):
        """Correct password verifies."""
        gen = PasswordGenerator()
        plaintext, record = gen.generate()
        
        verifier = PasswordVerifier(gen)
        result = verifier.verify(record.password_id, plaintext)
        
        assert result.verified is True
        assert result.reason == "VERIFIED"
    
    def test_verify_wrong_password(self):
        """Wrong password fails."""
        gen = PasswordGenerator()
        _, record = gen.generate()
        
        verifier = PasswordVerifier(gen)
        result = verifier.verify(record.password_id, "WRONG_PASSWORD")
        
        assert result.verified is False
        assert result.reason == "HASH_MISMATCH"
    
    def test_verify_one_time_use(self):
        """Password can only be used once."""
        gen = PasswordGenerator()
        plaintext, record = gen.generate()
        
        verifier = PasswordVerifier(gen)
        
        # First attempt
        result1 = verifier.verify(record.password_id, plaintext)
        assert result1.verified is True
        
        # Second attempt fails
        result2 = verifier.verify(record.password_id, plaintext)
        assert result2.verified is False
        assert result2.reason == "PASSWORD_ALREADY_USED"
    
    def test_verify_expired_password(self):
        """Expired password fails."""
        gen = PasswordGenerator(expiry_seconds=1)  # 1 second expiry
        plaintext, record = gen.generate()
        
        # Wait for expiry
        time.sleep(1.1)
        
        verifier = PasswordVerifier(gen)
        result = verifier.verify(record.password_id, plaintext)
        
        assert result.verified is False
        assert result.reason == "PASSWORD_EXPIRED"
    
    def test_verify_not_found(self):
        """Non-existent password fails."""
        gen = PasswordGenerator()
        verifier = PasswordVerifier(gen)
        
        result = verifier.verify("INVALID-ID", "test")
        
        assert result.verified is False
        assert result.reason == "PASSWORD_NOT_FOUND"
    
    def test_is_used(self):
        """Check if password has been used."""
        gen = PasswordGenerator()
        plaintext, record = gen.generate()
        
        verifier = PasswordVerifier(gen)
        
        assert verifier.is_used(record.password_id) is False
        verifier.verify(record.password_id, plaintext)
        assert verifier.is_used(record.password_id) is True


class TestTriggerEvaluation:
    """Test challenge trigger evaluation."""
    
    def test_trigger_concurrent_logins(self):
        """Concurrent logins trigger challenge."""
        should, trigger = should_challenge(
            concurrent_logins=3,
            is_new_device=False,
            is_new_ip=False,
            is_new_geo=False,
            is_admin_access=False,
            risk_score=0.0,
        )
        assert should is True
        assert trigger == TriggerType.CONCURRENT_LOGINS
    
    def test_trigger_new_device(self):
        """New device triggers challenge."""
        should, trigger = should_challenge(
            concurrent_logins=1,
            is_new_device=True,
            is_new_ip=False,
            is_new_geo=False,
            is_admin_access=False,
            risk_score=0.0,
        )
        assert should is True
        assert trigger == TriggerType.NEW_DEVICE
    
    def test_trigger_new_ip(self):
        """New IP triggers challenge."""
        should, trigger = should_challenge(
            concurrent_logins=1,
            is_new_device=False,
            is_new_ip=True,
            is_new_geo=False,
            is_admin_access=False,
            risk_score=0.0,
        )
        assert should is True
        assert trigger == TriggerType.NEW_IP
    
    def test_trigger_new_geo(self):
        """New GEO triggers challenge."""
        should, trigger = should_challenge(
            concurrent_logins=1,
            is_new_device=False,
            is_new_ip=False,
            is_new_geo=True,
            is_admin_access=False,
            risk_score=0.0,
        )
        assert should is True
        assert trigger == TriggerType.NEW_GEO
    
    def test_trigger_admin_access(self):
        """Admin access triggers challenge."""
        should, trigger = should_challenge(
            concurrent_logins=1,
            is_new_device=False,
            is_new_ip=False,
            is_new_geo=False,
            is_admin_access=True,
            risk_score=0.0,
        )
        assert should is True
        assert trigger == TriggerType.ADMIN_ACCESS
    
    def test_trigger_risk_escalation(self):
        """High risk triggers challenge."""
        should, trigger = should_challenge(
            concurrent_logins=1,
            is_new_device=False,
            is_new_ip=False,
            is_new_geo=False,
            is_admin_access=False,
            risk_score=0.8,
        )
        assert should is True
        assert trigger == TriggerType.RISK_ESCALATION
    
    def test_no_trigger(self):
        """Normal access does not trigger."""
        should, trigger = should_challenge(
            concurrent_logins=1,
            is_new_device=False,
            is_new_ip=False,
            is_new_geo=False,
            is_admin_access=False,
            risk_score=0.3,
        )
        assert should is False
        assert trigger is None


class TestPolicy:
    """Test password policy."""
    
    def test_get_default_policy(self):
        """Get default policy."""
        policy = get_default_policy()
        
        assert policy.min_length == 1
        assert policy.max_length == 100
        assert policy.min_scripts == 3
        assert policy.max_scripts == 5
        assert policy.expiry_seconds == 300
        assert policy.strength == PasswordStrength.STANDARD


class TestDataclasses:
    """Test dataclass immutability."""
    
    def test_password_policy_frozen(self):
        """PasswordPolicy is immutable."""
        policy = get_default_policy()
        with pytest.raises(Exception):
            policy.min_length = 10
    
    def test_generated_password_frozen(self):
        """GeneratedPassword is immutable."""
        gen = PasswordGenerator()
        _, record = gen.generate()
        with pytest.raises(Exception):
            record.is_used = True
    
    def test_verification_result_frozen(self):
        """VerificationResult is immutable."""
        result = VerificationResult(
            password_id="PWD-123",
            verified=True,
            reason="VERIFIED",
            timestamp="2026-01-29T00:00:00Z",
        )
        with pytest.raises(Exception):
            result.verified = False


class TestScriptDiversity:
    """Test that passwords have proper script diversity."""
    
    def test_generated_password_has_multiple_scripts(self):
        """Generated password uses multiple scripts."""
        gen = PasswordGenerator(min_scripts=4)
        
        for _ in range(10):
            plaintext, record = gen.generate()
            
            # Count unique scripts in password
            scripts_found = set()
            for char in plaintext:
                script = get_script_category(char)
                if script:
                    scripts_found.add(script)
            
            assert len(scripts_found) >= 3
    
    def test_password_contains_chars_from_selected_scripts(self):
        """Password contains chars from multiple scripts."""
        gen = PasswordGenerator(min_scripts=3, max_scripts=5)
        
        for _ in range(10):
            plaintext, record = gen.generate()
            
            # Count unique scripts in password
            # Note: Some scripts may share Unicode categories
            # (e.g., Hindi/Marathi both map to DEVANAGARI)
            scripts_found = set()
            for char in plaintext:
                script = get_script_category(char)
                if script:
                    scripts_found.add(script)
            
            # Should have at least 2 distinct Unicode categories
            # (some ScriptTypes share categories)
            assert len(scripts_found) >= 2
