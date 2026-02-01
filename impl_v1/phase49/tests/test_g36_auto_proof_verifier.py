# Test G36: Autonomous Proof Verifier
"""
Tests for G36 autonomous proof verifier.

100% coverage required.
"""

import pytest
import json

from impl_v1.phase49.governors.g36_auto_proof_verifier import (
    AutoVerifyStatus,
    AutoBugType,
    ProofSignals,
    AutoVerificationResult,
    is_scanner_noise,
    is_keyword_only,
    is_theoretical,
    check_proof_signals,
    check_evidence_exists,
    determine_bug_type,
    calculate_confidence,
    auto_verify_finding,
    build_auto_final_report,
    auto_verify_batch,
    filter_auto_real,
    filter_needs_human,
    can_auto_verify_without_proof,
    can_auto_submit_bug,
    can_auto_override_g33,
    can_auto_ignore_duplicate_score,
    can_auto_execute_payloads,
    can_auto_bypass_human,
)


class TestAutoVerifyStatus:
    """Test status enum."""
    
    def test_status_values(self):
        assert AutoVerifyStatus.AUTO_REAL.value == "AUTO_REAL"
        assert AutoVerifyStatus.NOT_REAL.value == "NOT_REAL"
        assert AutoVerifyStatus.DUPLICATE.value == "DUPLICATE"
        assert AutoVerifyStatus.NEEDS_HUMAN.value == "NEEDS_HUMAN"


class TestAutoBugType:
    """Test bug type enum."""
    
    def test_bug_type_values(self):
        assert AutoBugType.SQLI.value == "SQLi"
        assert AutoBugType.XSS.value == "XSS"
        assert AutoBugType.IDOR.value == "IDOR"
        assert AutoBugType.AUTH.value == "AUTH"


class TestScannerNoiseDetection:
    """Test scanner noise detection."""
    
    def test_detects_missing_header(self):
        is_noise, reason = is_scanner_noise("Missing X-Frame-Options header")
        assert is_noise is True
        assert "x-frame-options" in reason.lower()
    
    def test_detects_version_disclosure(self):
        is_noise, reason = is_scanner_noise("Server version disclosed in headers")
        assert is_noise is True
    
    def test_detects_cookie_flags(self):
        is_noise, reason = is_scanner_noise("Secure flag missing on cookie")
        assert is_noise is True
    
    def test_real_finding_not_noise(self):
        is_noise, reason = is_scanner_noise("SQL injection in login parameter allows data extraction")
        assert is_noise is False


class TestKeywordOnlyDetection:
    """Test keyword-only detection."""
    
    def test_detects_sqlite_keyword(self):
        is_kw, reason = is_keyword_only("Error: sqlite_ table not found")
        assert is_kw is True
    
    def test_keyword_with_proof_not_rejected(self):
        is_kw, reason = is_keyword_only("sqlite_ error. Response: extracted user data")
        assert is_kw is False  # Has "response:" indicator


class TestTheoreticalDetection:
    """Test theoretical risk detection."""
    
    def test_detects_could_lead_to(self):
        is_theo, reason = is_theoretical("This could lead to account takeover")
        assert is_theo is True
    
    def test_detects_might_allow(self):
        is_theo, reason = is_theoretical("This might allow privilege escalation")
        assert is_theo is True
    
    def test_proven_finding_not_theoretical(self):
        is_theo, reason = is_theoretical("Account takeover confirmed with admin access")
        assert is_theo is False


class TestProofSignals:
    """Test proof signal extraction."""
    
    def test_extracts_all_signals(self):
        data = {
            "input_vector": "id=123",
            "response_before": "Access denied",
            "response_after": "Welcome admin",
            "unauthorized_access": True,
            "extracted_data": "email@example.com",
            "reproduction_count": 3,
        }
        signals = check_proof_signals(data)
        
        assert signals.input_control is True
        assert signals.response_delta is True
        assert signals.auth_boundary is True
        assert signals.data_extracted is True
        assert signals.reproduction_count == 3
    
    def test_no_signals_for_empty_data(self):
        signals = check_proof_signals({})
        
        assert signals.input_control is False
        assert signals.response_delta is False
        assert signals.reproduction_count == 0


class TestAutoVerifyFinding:
    """Test main auto verification function."""
    
    def test_rejects_scanner_noise(self):
        result = auto_verify_finding(
            "Missing X-Content-Type-Options header",
            {},
        )
        assert result.status == AutoVerifyStatus.NOT_REAL
        assert "scanner noise" in result.why_verified_or_rejected.lower()
    
    def test_rejects_keyword_only(self):
        result = auto_verify_finding(
            "Error message contains mongo. string",
            {},
        )
        assert result.status == AutoVerifyStatus.NOT_REAL
        assert "keyword" in result.why_verified_or_rejected.lower()
    
    def test_rejects_theoretical(self):
        result = auto_verify_finding(
            "This could lead to remote code execution",
            {},
        )
        assert result.status == AutoVerifyStatus.NOT_REAL
        assert "theoretical" in result.why_verified_or_rejected.lower()
    
    def test_rejects_duplicate(self):
        result = auto_verify_finding(
            "SQL injection in login form",
            {"input_vector": "id=1"},
            duplicate_probability=85,
            duplicate_threshold=70,
        )
        assert result.status == AutoVerifyStatus.DUPLICATE
        assert result.duplicate_probability == 85
    
    def test_needs_human_for_missing_signals(self):
        result = auto_verify_finding(
            "SQL injection in login",
            {"input_vector": "id=1"},  # Missing other signals
        )
        assert result.status == AutoVerifyStatus.NEEDS_HUMAN
        assert "missing" in result.why_verified_or_rejected.lower()
    
    def test_auto_real_with_all_signals(self):
        result = auto_verify_finding(
            "SQL injection in login form allows data extraction",
            {
                "input_vector": "id=1' OR 1=1--",
                "response_before": "Invalid login",
                "response_after": "Welcome admin, email: admin@example.com",
                "unauthorized_access": True,
                "reproduction_count": 3,
                "video_path": "/evidence/poc.webm",
                "request_data": "POST /login",
                "response_data": "200 OK",
                "impact": "Full database access",
            },
        )
        assert result.status == AutoVerifyStatus.AUTO_REAL
        assert result.confidence >= 80
        assert result.proof_signals.input_control is True
        assert result.proof_signals.response_delta is True
        assert "video" in result.linked_evidence


class TestBuildAutoReport:
    """Test JSON report building."""
    
    def test_builds_valid_json(self):
        result = auto_verify_finding("Test", {})
        report_bytes = build_auto_final_report(result)
        
        assert isinstance(report_bytes, bytes)
        
        report = json.loads(report_bytes.decode("utf-8"))
        assert "mode" in report
        assert "status" in report
        assert "proof_signals" in report
        assert report["mode"] == "AUTO"


class TestBatchOperations:
    """Test batch verification."""
    
    def test_verify_batch(self):
        findings = (
            ("Missing header", {}, 0),
            ("SQL injection with proof", {
                "input_vector": "id=1",
                "response_before": "A",
                "response_after": "B",
                "unauthorized_access": True,
                "reproduction_count": 2,
                "video_path": "/poc.webm",
            }, 0),
        )
        
        results = auto_verify_batch(findings)
        assert len(results) == 2
        assert results[0].status == AutoVerifyStatus.NOT_REAL
    
    def test_filter_auto_real(self):
        results = (
            AutoVerificationResult(
                result_id="1", mode="AUTO", status=AutoVerifyStatus.AUTO_REAL,
                confidence=90, bug_type=AutoBugType.SQLI,
                proof_signals=ProofSignals(True, True, True, False, 2),
                impact="High", why_verified_or_rejected="Verified",
                linked_evidence=tuple(), duplicate_probability=0,
                determinism_hash="abc",
            ),
            AutoVerificationResult(
                result_id="2", mode="AUTO", status=AutoVerifyStatus.NOT_REAL,
                confidence=95, bug_type=AutoBugType.OTHER,
                proof_signals=ProofSignals(False, False, False, False, 0),
                impact="None", why_verified_or_rejected="Noise",
                linked_evidence=tuple(), duplicate_probability=0,
                determinism_hash="def",
            ),
        )
        
        real_only = filter_auto_real(results)
        assert len(real_only) == 1
        assert real_only[0].result_id == "1"


class TestGuards:
    """Test all guards return False."""
    
    def test_can_auto_verify_without_proof_returns_false(self):
        can_verify, reason = can_auto_verify_without_proof()
        assert can_verify is False
        assert "proof" in reason.lower()
    
    def test_can_auto_submit_bug_returns_false(self):
        can_submit, reason = can_auto_submit_bug()
        assert can_submit is False
        assert "human" in reason.lower()
    
    def test_can_auto_override_g33_returns_false(self):
        can_override, reason = can_auto_override_g33()
        assert can_override is False
        assert "g33" in reason.lower()
    
    def test_can_auto_ignore_duplicate_score_returns_false(self):
        can_ignore, reason = can_auto_ignore_duplicate_score()
        assert can_ignore is False
        assert "duplicate" in reason.lower()
    
    def test_can_auto_execute_payloads_returns_false(self):
        can_execute, reason = can_auto_execute_payloads()
        assert can_execute is False
        assert "read-only" in reason.lower()
    
    def test_can_auto_bypass_human_returns_false(self):
        can_bypass, reason = can_auto_bypass_human()
        assert can_bypass is False
        assert "human" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive guard test."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_auto_verify_without_proof,
            can_auto_submit_bug,
            can_auto_override_g33,
            can_auto_ignore_duplicate_score,
            can_auto_execute_payloads,
            can_auto_bypass_human,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result is False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0, f"Guard {guard.__name__} has empty reason!"


class TestDataclassesFrozen:
    """Test dataclasses are immutable."""
    
    def test_proof_signals_frozen(self):
        signals = ProofSignals(True, True, True, False, 2)
        with pytest.raises(AttributeError):
            signals.input_control = False
    
    def test_result_frozen(self):
        result = auto_verify_finding("test", {})
        with pytest.raises(AttributeError):
            result.status = AutoVerifyStatus.AUTO_REAL
