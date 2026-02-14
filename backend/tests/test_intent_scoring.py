"""
test_intent_scoring.py — Tests for Weighted Intent Classifier

Validates:
  - Weighted scoring replaces simple counting
  - Confidence threshold (0.75) enforcement
  - Below-threshold → Security (safer)
  - High-confidence research queries classified correctly
  - High-confidence security queries classified correctly
  - Ambiguous queries default to Security
  - Confidence exposed in RouteDecision
"""

import sys
import os
import unittest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.assistant.query_router import (
    QueryRouter,
    VoiceMode,
    CONFIDENCE_THRESHOLD,
    SECURITY_KEYWORD_WEIGHTS,
    RESEARCH_KEYWORD_WEIGHTS,
    SECURITY_KEYWORDS,
    RESEARCH_KEYWORDS,
)


class TestConfidenceThreshold(unittest.TestCase):
    """Verify confidence threshold constant."""

    def test_threshold_is_075(self):
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.75)

    def test_threshold_immutable(self):
        """CONFIDENCE_THRESHOLD should be a numeric constant."""
        self.assertIsInstance(CONFIDENCE_THRESHOLD, float)


class TestWeightedKeywords(unittest.TestCase):
    """Verify keyword weights exist and have positive values."""

    def test_security_weights_exist(self):
        self.assertGreater(len(SECURITY_KEYWORD_WEIGHTS), 0)

    def test_research_weights_exist(self):
        self.assertGreater(len(RESEARCH_KEYWORD_WEIGHTS), 0)

    def test_all_security_weights_positive(self):
        for kw, w in SECURITY_KEYWORD_WEIGHTS.items():
            self.assertGreater(w, 0, f"Weight for '{kw}' must be positive")

    def test_all_research_weights_positive(self):
        for kw, w in RESEARCH_KEYWORD_WEIGHTS.items():
            self.assertGreater(w, 0, f"Weight for '{kw}' must be positive")

    def test_backward_compat_frozensets(self):
        """SECURITY_KEYWORDS and RESEARCH_KEYWORDS still exist as frozensets."""
        self.assertIsInstance(SECURITY_KEYWORDS, frozenset)
        self.assertIsInstance(RESEARCH_KEYWORDS, frozenset)

    def test_frozenset_matches_weights_keys(self):
        self.assertEqual(SECURITY_KEYWORDS, frozenset(SECURITY_KEYWORD_WEIGHTS.keys()))
        self.assertEqual(RESEARCH_KEYWORDS, frozenset(RESEARCH_KEYWORD_WEIGHTS.keys()))

    def test_vuln_types_high_weight(self):
        """CVE/XSS/RCE etc. should have weight >= 2.0."""
        for kw in ["cve", "xss", "sqli", "rce", "ssrf", "csrf"]:
            self.assertGreaterEqual(
                SECURITY_KEYWORD_WEIGHTS[kw], 2.0,
                f"Vuln type '{kw}' should be high-weight"
            )

    def test_research_triggers_high_weight(self):
        """'what is', 'define', 'who is' should have weight >= 2.0."""
        for kw in ["what is", "define", "who is", "tell me about"]:
            self.assertGreaterEqual(
                RESEARCH_KEYWORD_WEIGHTS[kw], 2.0,
                f"Research trigger '{kw}' should be high-weight"
            )


class TestWeightedClassification(unittest.TestCase):
    """Test the weighted scoring classification logic."""

    def setUp(self):
        self.router = QueryRouter()

    # === SECURITY queries ===

    def test_pure_security_query(self):
        """Pure security query gets high confidence."""
        result = self.router.classify("Check CVE-2024-1234 vulnerability")
        self.assertEqual(result.mode, VoiceMode.SECURITY)
        self.assertGreaterEqual(result.confidence, CONFIDENCE_THRESHOLD)

    def test_tool_security_query(self):
        """Tool-based security query."""
        result = self.router.classify("Run nmap scan on target")
        self.assertEqual(result.mode, VoiceMode.SECURITY)

    def test_xss_vuln_query(self):
        result = self.router.classify("Test for XSS injection vulnerability")
        self.assertEqual(result.mode, VoiceMode.SECURITY)

    def test_bounty_query(self):
        result = self.router.classify("Submit report to HackerOne for triage")
        self.assertEqual(result.mode, VoiceMode.SECURITY)

    # === RESEARCH queries ===

    def test_pure_research_query(self):
        """Pure research query gets high confidence."""
        result = self.router.classify("What is quantum computing?")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)
        self.assertGreaterEqual(result.confidence, CONFIDENCE_THRESHOLD)

    def test_define_research_query(self):
        result = self.router.classify("Define photosynthesis")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    def test_who_research_query(self):
        result = self.router.classify("Who invented the telephone?")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    def test_hindi_research_query(self):
        result = self.router.classify("DNS kya hai?")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    def test_tell_me_research(self):
        result = self.router.classify("Tell me about the solar system")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    def test_difference_research(self):
        result = self.router.classify("Difference between TCP and UDP")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    # === AMBIGUOUS / BELOW THRESHOLD ===

    def test_empty_defaults_security(self):
        result = self.router.classify("")
        self.assertEqual(result.mode, VoiceMode.SECURITY)
        self.assertEqual(result.confidence, 1.0)

    def test_gibberish_defaults_security(self):
        result = self.router.classify("asdf jkl zxcv qwer")
        self.assertEqual(result.mode, VoiceMode.SECURITY)

    def test_ambiguous_defaults_security(self):
        """Ambiguous queries with no keywords → Security."""
        result = self.router.classify("hello there")
        self.assertEqual(result.mode, VoiceMode.SECURITY)
        self.assertLessEqual(result.confidence, 0.5)

    # === CONFIDENCE PROPERTIES ===

    def test_confidence_in_range(self):
        """Confidence should always be 0-1."""
        queries = [
            "What is DNS?",
            "Scan target 192.168.1.1",
            "Define encryption",
            "Check CVE-2024-999",
            "Random gibberish text here",
        ]
        for q in queries:
            result = self.router.classify(q)
            self.assertGreaterEqual(result.confidence, 0.0, f"Query: {q}")
            self.assertLessEqual(result.confidence, 1.0, f"Query: {q}")

    def test_confidence_capped_at_099(self):
        """Confidence must not exceed 0.99."""
        result = self.router.classify("What is the meaning of biology?")
        self.assertLessEqual(result.confidence, 0.99)

    def test_confidence_exposed_in_decision(self):
        """RouteDecision includes confidence field."""
        result = self.router.classify("What is Python?")
        self.assertTrue(hasattr(result, 'confidence'))
        self.assertIsInstance(result.confidence, float)

    def test_below_threshold_falls_to_security(self):
        """If neither mode reaches 0.75, fall to Security."""
        # A query with balanced security + research keywords (neither dominates)
        result = self.router.classify("science of exploit payload math")
        self.assertEqual(result.mode, VoiceMode.SECURITY)

    # === WEIGHT IMPACT ===

    def test_high_weight_security_dominates(self):
        """High-weight security keywords should dominate low-weight research."""
        result = self.router.classify("XSS CSRF RCE attack vector")
        self.assertEqual(result.mode, VoiceMode.SECURITY)
        self.assertGreaterEqual(result.confidence, CONFIDENCE_THRESHOLD)

    def test_high_weight_research_dominates(self):
        """High-weight research triggers should dominate low-weight security."""
        result = self.router.classify("What is the history of biology and chemistry?")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    def test_pattern_boost_helps_research(self):
        """Regex pattern match adds +3.0 to research score."""
        result = self.router.classify("Explain how encryption works")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)


class TestBackwardCompatibility(unittest.TestCase):
    """Ensure existing test patterns still work."""

    def setUp(self):
        self.router = QueryRouter()

    def test_security_vuln_query(self):
        result = self.router.classify("Check vulnerability CVE-2024-1234")
        self.assertEqual(result.mode, VoiceMode.SECURITY)

    def test_research_what_is(self):
        result = self.router.classify("What is DNS poisoning?")
        self.assertEqual(result.mode, VoiceMode.RESEARCH)

    def test_blocked_patterns_exist(self):
        from backend.assistant.query_router import BLOCKED_RESEARCH_PATTERNS
        self.assertGreater(len(BLOCKED_RESEARCH_PATTERNS), 0)


if __name__ == "__main__":
    unittest.main()
