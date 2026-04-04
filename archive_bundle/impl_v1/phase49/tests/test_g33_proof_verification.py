# test_g33_proof_verification.py
"""Tests for G33 Proof-Based Bug Verification."""

import pytest

from impl_v1.phase49.governors.g33_proof_verification import (
    # Enums
    ProofStatus,
    ImpactCategory,
    RejectionReason,
    # Data structures
    ProofEvidence,
    ProofVerificationResult,
    # Functions
    verify_bug_proof,
    verify_findings_batch,
    filter_real_bugs,
    filter_needs_human,
    # Guards
    can_verify_without_proof,
    can_auto_submit,
    can_override_human,
    can_mark_real_without_evidence,
)


class TestProofStatusEnum:
    """Tests for ProofStatus enum."""
    
    def test_has_4_statuses(self):
        assert len(ProofStatus) == 4
    
    def test_has_real(self):
        assert ProofStatus.REAL.value == "REAL"
    
    def test_has_not_real(self):
        assert ProofStatus.NOT_REAL.value == "NOT_REAL"
    
    def test_has_duplicate(self):
        assert ProofStatus.DUPLICATE.value == "DUPLICATE"
    
    def test_has_needs_human(self):
        assert ProofStatus.NEEDS_HUMAN.value == "NEEDS_HUMAN"


class TestImpactCategoryEnum:
    """Tests for ImpactCategory enum."""
    
    def test_has_7_categories(self):
        assert len(ImpactCategory) == 7
    
    def test_has_account_takeover(self):
        assert ImpactCategory.ACCOUNT_TAKEOVER.value == "ACCOUNT_TAKEOVER"
    
    def test_has_data_leak(self):
        assert ImpactCategory.DATA_LEAK.value == "DATA_LEAK"


class TestRejectionReasonEnum:
    """Tests for RejectionReason enum."""
    
    def test_has_9_reasons(self):
        assert len(RejectionReason) == 9
    
    def test_has_scanner_output_only(self):
        assert RejectionReason.SCANNER_OUTPUT_ONLY.value == "SCANNER_OUTPUT_ONLY"


class TestVerifyBugProof:
    """Tests for verify_bug_proof function."""
    
    def test_rejects_scanner_noise_missing_headers(self):
        result = verify_bug_proof(
            finding_text="Missing X-Frame-Options header",
            finding_data={},
        )
        assert result.status == ProofStatus.NOT_REAL
        assert result.rejection_reason == RejectionReason.SCANNER_OUTPUT_ONLY
    
    def test_rejects_scanner_noise_sqlite(self):
        result = verify_bug_proof(
            finding_text="Found sqlite_ function in response",
            finding_data={},
        )
        assert result.status == ProofStatus.NOT_REAL
    
    def test_rejects_theoretical_risk(self):
        result = verify_bug_proof(
            finding_text="This could potentially lead to XSS",
            finding_data={},
        )
        assert result.status == ProofStatus.NOT_REAL
        assert result.rejection_reason == RejectionReason.THEORETICAL_RISK
    
    def test_rejects_no_controllable_input(self):
        result = verify_bug_proof(
            finding_text="Found XSS vulnerability",
            finding_data={},  # No input_vector, parameter, or payload
        )
        assert result.status == ProofStatus.NOT_REAL
        assert result.rejection_reason == RejectionReason.NO_CONTROLLABLE_INPUT
    
    def test_needs_human_no_response_delta(self):
        result = verify_bug_proof(
            finding_text="SQL injection found",
            finding_data={"input_vector": "id=1'"},
        )
        assert result.status == ProofStatus.NEEDS_HUMAN
        assert result.rejection_reason == RejectionReason.NO_RESPONSE_DELTA
    
    def test_verifies_real_bug_with_full_proof(self):
        result = verify_bug_proof(
            finding_text="Account takeover via IDOR",
            finding_data={
                "input_vector": "user_id=123",
                "response_before": "Access denied",
                "response_after": "User profile: admin@...",
                "unauthorized_access": True,
                "account_takeover": True,
            },
        )
        assert result.status == ProofStatus.REAL
        assert result.impact == ImpactCategory.ACCOUNT_TAKEOVER
        assert result.confidence >= 75
    
    def test_has_result_id(self):
        result = verify_bug_proof("test", {})
        assert result.result_id.startswith("PRF-")
    
    def test_has_determinism_hash(self):
        result = verify_bug_proof("test", {})
        assert len(result.determinism_hash) == 32


class TestDeterministicVerification:
    """Tests for determinism in verification."""
    
    def test_same_input_same_result(self):
        finding_text = "XSS found"
        finding_data = {"input_vector": "<script>"}
        
        result1 = verify_bug_proof(finding_text, finding_data)
        result2 = verify_bug_proof(finding_text, finding_data)
        
        assert result1.status == result2.status
        assert result1.determinism_hash == result2.determinism_hash


class TestBatchVerification:
    """Tests for batch verification."""
    
    def test_verify_batch(self):
        findings = (
            ("Missing headers", {}),
            ("XSS with proof", {"input_vector": "<script>", "response_before": "a", "response_after": "b"}),
        )
        results = verify_findings_batch(findings)
        assert len(results) == 2
    
    def test_filter_real_bugs(self):
        results = (
            ProofVerificationResult("1", ProofStatus.REAL, 90, ImpactCategory.DATA_LEAK, "", "", RejectionReason.NONE, None, ""),
            ProofVerificationResult("2", ProofStatus.NOT_REAL, 80, ImpactCategory.NONE, "", "", RejectionReason.SCANNER_OUTPUT_ONLY, None, ""),
        )
        real = filter_real_bugs(results)
        assert len(real) == 1
        assert real[0].status == ProofStatus.REAL
    
    def test_filter_needs_human(self):
        results = (
            ProofVerificationResult("1", ProofStatus.NEEDS_HUMAN, 60, ImpactCategory.NONE, "", "", RejectionReason.NONE, None, ""),
            ProofVerificationResult("2", ProofStatus.NOT_REAL, 80, ImpactCategory.NONE, "", "", RejectionReason.SCANNER_OUTPUT_ONLY, None, ""),
        )
        human = filter_needs_human(results)
        assert len(human) == 1
        assert human[0].status == ProofStatus.NEEDS_HUMAN


class TestCanVerifyWithoutProof:
    """Tests for can_verify_without_proof guard."""
    
    def test_returns_false(self):
        can_verify, reason = can_verify_without_proof()
        assert can_verify == False
    
    def test_has_reason(self):
        can_verify, reason = can_verify_without_proof()
        assert "proof" in reason.lower()


class TestCanAutoSubmit:
    """Tests for can_auto_submit guard."""
    
    def test_returns_false(self):
        can_submit, reason = can_auto_submit()
        assert can_submit == False
    
    def test_has_reason(self):
        can_submit, reason = can_auto_submit()
        assert "human" in reason.lower()


class TestCanOverrideHuman:
    """Tests for can_override_human guard."""
    
    def test_returns_false(self):
        can_override, reason = can_override_human()
        assert can_override == False
    
    def test_reason_mentions_absolute(self):
        can_override, reason = can_override_human()
        assert "absolute" in reason.lower()


class TestCanMarkRealWithoutEvidence:
    """Tests for can_mark_real_without_evidence guard."""
    
    def test_returns_false(self):
        can_mark, reason = can_mark_real_without_evidence()
        assert can_mark == False
    
    def test_has_reason(self):
        can_mark, reason = can_mark_real_without_evidence()
        assert "evidence" in reason.lower() or "proof" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive test that ALL guards return False."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_verify_without_proof,
            can_auto_submit,
            can_override_human,
            can_mark_real_without_evidence,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result == False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0, f"Guard {guard.__name__} has empty reason!"


class TestFrozenDatastructures:
    """Tests that all datastructures are frozen."""
    
    def test_proof_verification_result_is_frozen(self):
        result = verify_bug_proof("test", {})
        with pytest.raises(AttributeError):
            result.status = ProofStatus.REAL


class TestNoForbiddenImports:
    """Tests that G33 has no forbidden imports."""
    
    def test_no_forbidden_imports(self):
        import impl_v1.phase49.governors.g33_proof_verification as g33
        import inspect
        
        source = inspect.getsource(g33)
        
        forbidden = ["subprocess", "socket", "selenium", "playwright"]
        for name in forbidden:
            assert f"import {name}" not in source
