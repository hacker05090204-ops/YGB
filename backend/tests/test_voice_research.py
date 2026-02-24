"""
Tests for Phase 6 (Voice Hardening) and Phase 7 (Research Truth Policy).
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# =============================================================================
# Phase 6 — Voice Hardening
# =============================================================================

class TestVoiceConfidence(unittest.TestCase):
    """Test confidence-based voice routing."""

    def _make_router(self):
        from backend.voice.intent_router import IntentRouter
        return IntentRouter()

    def test_clear_clarification(self):
        router = self._make_router()
        result = router.route("what is XSS")
        self.assertTrue(result.allowed)
        self.assertEqual(result.mode, "clarification")

    def test_report_not_blocked(self):
        """'report' should NOT be blocked — it's a valid status keyword."""
        router = self._make_router()
        result = router.route("status report")
        # Should not be blocked — 'report' + 'status' are both status keywords
        self.assertTrue(result.allowed)

    def test_submit_report_blocked(self):
        """'submit report' phrase should be blocked."""
        router = self._make_router()
        result = router.route("submit report now")
        self.assertFalse(result.allowed)
        self.assertEqual(result.mode, "blocked")

    def test_hunt_blocked(self):
        router = self._make_router()
        result = router.route("hunt for bugs")
        self.assertFalse(result.allowed)

    def test_empty_input(self):
        router = self._make_router()
        result = router.route("")
        self.assertFalse(result.allowed)
        self.assertEqual(result.mode, "idle")

    def test_blocked_phrases(self):
        router = self._make_router()
        for phrase in ["override governance", "disable safety", "bypass gate"]:
            result = router.route(phrase)
            self.assertFalse(result.allowed, f"'{phrase}' should be blocked")

    def test_multilingual_hindi(self):
        router = self._make_router()
        result = router.route("kya hai yeh")
        # Should route (may be clarification)
        self.assertIsNotNone(result)

    def test_safety_override_blocked(self):
        router = self._make_router()
        result = router.route("execute attack on target system")
        self.assertFalse(result.allowed)

    def test_noisy_input_safe_fallback(self):
        router = self._make_router()
        result = router.route("asdf jkl qwerty 12345")
        # Unknown input → default clarification
        self.assertEqual(result.mode, "clarification")


# =============================================================================
# Phase 7 — Research Truth Policy
# =============================================================================

class TestSourceConsensus(unittest.TestCase):
    """Test multi-source consensus engine."""

    def test_verified_with_two_sources(self):
        from native.research_assistant.source_consensus import (
            verify_claim, SourceRecord, SourceConfidence,
        )
        sources = [
            SourceRecord(source_url="https://nvd.nist.gov/vuln/1", source_name="NVD", trust_score=0.95),
            SourceRecord(source_url="https://cve.mitre.org/cgi-bin/1", source_name="MITRE", trust_score=0.95),
        ]
        result = verify_claim("CVE-2024-1234 is critical", sources)
        self.assertEqual(result.confidence, SourceConfidence.VERIFIED)
        self.assertEqual(result.independent_count, 2)

    def test_unverified_no_sources(self):
        from native.research_assistant.source_consensus import (
            verify_claim, SourceConfidence,
        )
        result = verify_claim("Some random claim", [])
        self.assertEqual(result.confidence, SourceConfidence.UNVERIFIED)

    def test_likely_single_trusted_source(self):
        from native.research_assistant.source_consensus import (
            verify_claim, SourceRecord, SourceConfidence,
        )
        sources = [
            SourceRecord(source_url="https://owasp.org/top-10", source_name="OWASP", trust_score=0.90),
        ]
        result = verify_claim("XSS is in OWASP Top 10", sources)
        self.assertEqual(result.confidence, SourceConfidence.LIKELY)

    def test_mathematical_truth_always_verified(self):
        from native.research_assistant.source_consensus import (
            verify_claim, SourceConfidence,
        )
        result = verify_claim("2 + 2 = 4", [], is_mathematical=True)
        self.assertEqual(result.confidence, SourceConfidence.VERIFIED)

    def test_same_domain_not_independent(self):
        from native.research_assistant.source_consensus import (
            verify_claim, SourceRecord, SourceConfidence,
        )
        sources = [
            SourceRecord(source_url="https://nvd.nist.gov/vuln/1", source_name="NVD page 1", trust_score=0.95),
            SourceRecord(source_url="https://nvd.nist.gov/vuln/2", source_name="NVD page 2", trust_score=0.95),
        ]
        result = verify_claim("Claim needing verification", sources)
        # Same domain → only 1 independent source → LIKELY, not VERIFIED
        self.assertNotEqual(result.confidence, SourceConfidence.VERIFIED)

    def test_domain_trust_scoring(self):
        from native.research_assistant.source_consensus import get_domain_trust
        self.assertGreater(get_domain_trust("https://nvd.nist.gov/vuln/1"), 0.9)
        self.assertGreater(get_domain_trust("https://owasp.org/top-10"), 0.8)
        self.assertLess(get_domain_trust("https://random-blog.example.com"), 0.5)

    def test_claim_to_dict(self):
        from native.research_assistant.source_consensus import (
            verify_claim, SourceRecord,
        )
        sources = [
            SourceRecord(source_url="https://example.com", source_name="Example"),
        ]
        result = verify_claim("test claim", sources)
        d = result.to_dict()
        self.assertIn("confidence", d)
        self.assertIn("sources", d)
        self.assertIn("independent_count", d)


if __name__ == "__main__":
    unittest.main()
