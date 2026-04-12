"""Canonical Phase 11 anti-hallucination gate tests.

Covers:
  - CVE in store is verified
  - CVE not in store is unverified
  - speculation reduces confidence
  - low confidence returns refusal
  - all verified is grounded
"""

import pytest

import backend.cve.anti_hallucination as anti_hallucination_module
from backend.cve.anti_hallucination import GROUNDING_DISCLAIMER, REFUSAL_TEXT


@pytest.fixture()
def validator():
    anti_hallucination_module._validator = None
    current = anti_hallucination_module.get_anti_hallucination_validator()
    yield current
    anti_hallucination_module._validator = None


def test_cve_in_store_is_verified(validator):
    response = "CVE-2024-1234 affects OpenSSL servers."

    result = validator.validate_response_grounding(
        response,
        {"extracted_text": response},
    )

    assert result.grounded is True
    assert result.confidence == pytest.approx(1.0)
    assert result.reason == "grounded_against_evidence_store"
    assert result.cve_mentions == ("CVE-2024-1234",)
    assert result.unsupported_cves == ()
    assert result.refusal_required is False
    assert result.final_text == response


def test_cve_not_in_store_is_unverified(validator):
    response = "CVE-2024-9999 affects OpenSSL servers."

    result = validator.validate_response_grounding(
        response,
        {"extracted_text": "CVE-2024-1234 affects OpenSSL servers."},
    )

    assert result.grounded is False
    assert result.confidence < 0.3
    assert result.unsupported_cves == ("CVE-2024-9999",)
    assert "unsupported_cves=CVE-2024-9999" in result.reason
    assert result.refusal_required is True
    assert result.final_text == REFUSAL_TEXT


def test_speculation_reduces_confidence(validator):
    evidence_store = {
        "extracted_text": "DNS poisoning changes cached responses on recursive resolvers.",
    }
    verified = validator.validate_response_grounding(
        "DNS poisoning changes cached responses on recursive resolvers.",
        evidence_store,
    )
    speculative = validator.validate_response_grounding(
        "DNS poisoning may change cached responses on recursive resolvers.",
        evidence_store,
    )

    assert verified.grounded is True
    assert speculative.grounded is False
    assert speculative.confidence < verified.confidence
    assert speculative.speculation_flags == ("may",)
    assert speculative.refusal_required is False
    assert GROUNDING_DISCLAIMER in speculative.final_text


def test_low_confidence_returns_refusal(validator):
    result = validator.validate_response_grounding(
        "CVE-2024-1234 could allow remote code execution on OpenSSL servers.",
        {"extracted_text": "CVE-2024-1234 affects OpenSSL servers."},
    )

    assert result.grounded is False
    assert result.unsupported_cves == ()
    assert result.confidence < 0.3
    assert "sentence_support=0.00" in result.reason
    assert "speculation_markers=could" in result.reason
    assert result.refusal_required is True
    assert result.final_text == REFUSAL_TEXT


def test_all_verified_is_grounded(validator):
    response = (
        "CVE-2024-1234 affects OpenSSL servers. "
        "Vendor patches are available for affected deployments."
    )

    result = validator.validate_response_grounding(
        response,
        {"extracted_text": response},
    )

    assert result.grounded is True
    assert result.confidence == pytest.approx(1.0)
    assert result.unsupported_cves == ()
    assert result.speculation_flags == ()
    assert result.refusal_required is False
    assert result.final_text == response
