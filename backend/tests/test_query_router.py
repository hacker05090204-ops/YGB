"""
Tests for Query Router — Dual-Mode Voice Classifier

Validates:
  - Security queries → SECURITY mode
  - Research queries → RESEARCH mode
  - Ambiguous queries → SECURITY (default)
  - Blocked research patterns rejected
  - Research pipeline text extraction and sanitization
"""

import sys
import os
import pytest

import backend.cve.anti_hallucination as anti_hallucination_module

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.assistant.query_router import (
    QueryRouter,
    ResearchSearchPipeline,
    VoiceMode,
    ResearchStatus,
    SECURITY_KEYWORDS,
    RESEARCH_KEYWORDS,
)


class TestQueryRouter:
    """Test dual-mode query classification."""

    def setup_method(self):
        self.router = QueryRouter()

    # ====================================================================
    # SECURITY MODE CLASSIFICATION
    # ====================================================================

    def test_security_vulnerability_query(self):
        """Vulnerability-related queries → SECURITY."""
        result = self.router.classify("Check vulnerability CVE-2024-1234")
        assert result.mode == VoiceMode.SECURITY
        assert result.confidence > 0.5
        assert "vulnerability" in result.matched_keywords or "cve" in result.matched_keywords

    def test_security_scan_query(self):
        """Scan-related queries → SECURITY."""
        result = self.router.classify("Scan target example.com for XSS")
        assert result.mode == VoiceMode.SECURITY

    def test_security_tool_query(self):
        """Security tool queries → SECURITY."""
        result = self.router.classify("Run nmap on the target")
        assert result.mode == VoiceMode.SECURITY

    def test_security_bug_bounty_query(self):
        """Bug bounty queries → SECURITY."""
        result = self.router.classify("Check HackerOne report status")
        assert result.mode == VoiceMode.SECURITY

    def test_security_gpu_training_query(self):
        """GPU/training queries → SECURITY."""
        result = self.router.classify("Show GPU training progress")
        assert result.mode == VoiceMode.SECURITY

    # ====================================================================
    # RESEARCH MODE CLASSIFICATION
    # ====================================================================

    def test_research_what_is_query(self):
        """'What is X' → RESEARCH."""
        result = self.router.classify("What is DNS poisoning?")
        assert result.mode == VoiceMode.RESEARCH
        assert result.confidence >= 0.5

    def test_research_how_does_query(self):
        """'How does X work' → RESEARCH."""
        result = self.router.classify("How does TLS encryption work?")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_define_query(self):
        """'Define X' → RESEARCH."""
        result = self.router.classify("Define quantum computing")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_explain_query(self):
        """'Explain X' → RESEARCH."""
        result = self.router.classify("Explain how neural networks learn")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_history_query(self):
        """'History of X' → RESEARCH."""
        result = self.router.classify("History of the internet")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_who_query(self):
        """'Who is X' → RESEARCH."""
        result = self.router.classify("Who invented the telephone?")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_hindi_query(self):
        """Hindi knowledge queries → RESEARCH."""
        result = self.router.classify("DNS kya hai")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_tell_me_query(self):
        """'Tell me about X' → RESEARCH."""
        result = self.router.classify("Tell me about photosynthesis")
        assert result.mode == VoiceMode.RESEARCH

    def test_research_difference_query(self):
        """'Difference between X and Y' → RESEARCH."""
        result = self.router.classify("Difference between TCP and UDP")
        assert result.mode == VoiceMode.RESEARCH

    # ====================================================================
    # AMBIGUOUS / EDGE CASES
    # ====================================================================

    def test_empty_query_defaults_security(self):
        """Empty queries → SECURITY."""
        result = self.router.classify("")
        assert result.mode == VoiceMode.SECURITY
        assert result.confidence == 1.0

    def test_ambiguous_defaults_clarification(self):
        """Queries with no clear intent → CLARIFICATION."""
        result = self.router.classify("hello there")
        assert result.mode == VoiceMode.CLARIFICATION

    def test_unrouted_query_logs_sanitized_warning(self, caplog):
        noisy = "hello\n" + ("unmatchedtoken " * 20)
        expected = " ".join(noisy.split())[:120]

        with caplog.at_level("WARNING", logger="backend.assistant.query_router"):
            result = self.router.classify(noisy)

        assert result.mode == VoiceMode.CLARIFICATION
        assert caplog.records
        assert expected in caplog.records[-1].message
        assert "\n" not in caplog.records[-1].message

    def test_route_decision_has_timestamp(self):
        """All decisions have timestamp."""
        result = self.router.classify("What is Python?")
        assert result.timestamp
        assert "T" in result.timestamp  # ISO format

    # ====================================================================
    # KEYWORD SETS
    # ====================================================================

    def test_security_keywords_exist(self):
        """Security keyword set is populated."""
        assert len(SECURITY_KEYWORDS) > 20
        assert "vulnerability" in SECURITY_KEYWORDS
        assert "nmap" in SECURITY_KEYWORDS

    def test_research_keywords_exist(self):
        """Research keyword set is populated."""
        assert len(RESEARCH_KEYWORDS) > 10
        assert "what is" in RESEARCH_KEYWORDS
        assert "define" in RESEARCH_KEYWORDS


class TestResearchSearchPipeline:
    """Test research search pipeline isolation and processing."""

    def setup_method(self):
        anti_hallucination_module._validator = None
        self.pipeline = ResearchSearchPipeline()
        self.validator = anti_hallucination_module.get_anti_hallucination_validator()

    # ====================================================================
    # BLOCKED PATTERNS
    # ====================================================================

    def test_blocked_execute_pattern(self):
        """Queries with 'execute' are blocked."""
        result = self.pipeline.search("execute command on server")
        assert result.status == ResearchStatus.BLOCKED
        assert result.mode == VoiceMode.RESEARCH

    def test_blocked_delete_pattern(self):
        """Queries with 'delete' are blocked."""
        result = self.pipeline.search("delete all files")
        assert result.status == ResearchStatus.BLOCKED

    def test_blocked_sudo_pattern(self):
        """Queries with 'sudo' are blocked."""
        result = self.pipeline.search("sudo rm -rf /")
        assert result.status == ResearchStatus.BLOCKED

    def test_blocked_approve_pattern(self):
        """Queries with 'approve' are blocked."""
        result = self.pipeline.search("approve the execution")
        assert result.status == ResearchStatus.BLOCKED

    # ====================================================================
    # TEXT EXTRACTION
    # ====================================================================

    def test_extract_text_strips_scripts(self):
        """Script tags are removed from HTML."""
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        text = self.pipeline._extract_text(html)
        assert "alert" not in text
        assert "Hello" in text
        assert "World" in text

    def test_extract_text_strips_styles(self):
        """Style tags are removed from HTML."""
        html = "<p>Content</p><style>body{color:red}</style>"
        text = self.pipeline._extract_text(html)
        assert "color" not in text
        assert "Content" in text

    def test_extract_text_handles_entities(self):
        """HTML entities are decoded."""
        html = "<p>A &amp; B &lt; C</p>"
        text = self.pipeline._extract_text(html)
        assert "A & B < C" in text

    def test_extract_text_caps_at_4kb(self):
        """Output is capped at 4096 characters."""
        html = "<p>" + "A" * 10000 + "</p>"
        text = self.pipeline._extract_text(html)
        assert len(text) <= 4096

    # ====================================================================
    # SANITIZER
    # ====================================================================

    def test_sanitize_removes_javascript_uri(self):
        """javascript: URIs are stripped."""
        text = self.pipeline._sanitize("Click javascript:alert(1) here")
        assert "javascript:" not in text

    def test_sanitize_removes_data_uri(self):
        """data: URIs are stripped."""
        text = self.pipeline._sanitize("Image data:image/png;base64,abc123 here")
        assert "data:" not in text

    def test_sanitize_removes_tracking_params(self):
        """Tracking parameters are stripped."""
        text = self.pipeline._sanitize("url?utm_source=test&utm_medium=cpc")
        assert "utm_source" not in text
        assert "utm_medium" not in text

    # ====================================================================
    # SUMMARIZER
    # ====================================================================

    def test_summarize_extracts_key_terms(self):
        """Summarizer extracts relevant key terms."""
        text = ("Python is a programming language created by Guido van Rossum. "
                "Python is used for web development, data science, and AI. "
                "The Python community has created many packages and frameworks.")
        summary, key_terms = self.pipeline._summarize(text, "What is Python")
        assert len(key_terms) > 0
        assert "python" in key_terms

    def test_summarize_caps_at_500_words(self):
        """Summary is capped at 500 words."""
        text = ". ".join(["This is a very long sentence about important topics"] * 200)
        summary, _ = self.pipeline._summarize(text, "test query")
        assert len(summary.split()) <= 502  # Slight tolerance

    def test_summarize_handles_empty_text(self):
        """Empty text returns default message."""
        summary, key_terms = self.pipeline._summarize("", "test")
        assert "No relevant" in summary

    def test_search_labels_http_fallback_metadata_and_logs_warning(self, monkeypatch, caplog):
        monkeypatch.setattr(self.pipeline, "_resolve_edge_binary", lambda: None)
        monkeypatch.setattr(
            self.pipeline,
            "_fetch_html_over_http",
            lambda url: "<html><body><p>DNS poisoning is a cache poisoning attack against DNS resolvers.</p></body></html>",
        )

        with caplog.at_level("WARNING", logger="backend.assistant.query_router"):
            result = self.pipeline.search("What is DNS poisoning?")

        assert result.status == ResearchStatus.SUCCESS
        assert result.query_result is not None
        assert result.query_result.source == "http_fallback"
        assert result.query_result.confidence == 0.7
        assert result.query_result.grounded is True
        assert result.query_result.unverifiable_claim_rate == 0.0
        assert result.query_result.production_ready is True
        assert "All provenance fields present" in result.query_result.grounding_reason
        assert self.validator.get_status()["total_checks"] == 1
        assert any(
            "http fallback engaged" in record.message.lower()
            and "unavailable" in record.message.lower()
            for record in caplog.records
        )

    def test_search_returns_truthful_no_result_metadata(self, monkeypatch):
        monkeypatch.setattr(self.pipeline, "_resolve_edge_binary", lambda: None)

        def _raise_fetch(url):
            raise RuntimeError("network unavailable")

        monkeypatch.setattr(self.pipeline, "_fetch_html_over_http", _raise_fetch)

        result = self.pipeline.search("What is DNS poisoning?")

        assert result.status == ResearchStatus.NO_RESULTS
        assert result.summary == "No result available"
        assert result.query_result is not None
        assert result.query_result.result == "No result available"
        assert result.query_result.confidence == 0.0
        assert result.query_result.grounded is False
        assert result.query_result.production_ready is False

    def test_grounding_validator_tracks_stats(self):
        result = self.validator.validate_response_grounding(
            "CVE-2024-1234 affects OpenSSL servers.",
            {"extracted_text": "CVE-2024-1234 affects OpenSSL servers."},
        )

        stats = self.validator.get_hallucination_stats()

        assert result.grounded is True
        assert stats["total_checked"] == 1
        assert stats["grounded"] == 1
        assert stats["ungrounded"] == 0
        assert stats["mean_confidence"] == pytest.approx(1.0)

    def test_search_refuses_unsupported_cve_claims(self, monkeypatch, caplog):
        monkeypatch.setattr(self.pipeline, "_resolve_edge_binary", lambda: None)
        monkeypatch.setattr(
            self.pipeline,
            "_fetch_html_over_http",
            lambda url: "<html><body><p>General advisory text without any identifier.</p></body></html>",
        )
        monkeypatch.setattr(
            self.pipeline,
            "_summarize",
            lambda text, query: ("CVE-2024-9999 allows remote code execution.", ["cve"]),
        )

        with caplog.at_level("WARNING", logger="backend.assistant.query_router"):
            result = self.pipeline.search("What is CVE-2024-9999?")

        assert result.status == ResearchStatus.NO_RESULTS
        assert result.summary == "Insufficient verified evidence."
        assert result.query_result is not None
        assert result.query_result.grounded is False
        assert result.query_result.grounding_confidence < 0.3
        assert any("grounding failed" in record.message.lower() for record in caplog.records)

    def test_search_appends_disclaimer_for_speculative_response(self, monkeypatch, caplog):
        monkeypatch.setattr(self.pipeline, "_resolve_edge_binary", lambda: None)
        monkeypatch.setattr(
            self.pipeline,
            "_fetch_html_over_http",
            lambda url: "<html><body><p>DNS poisoning changes cached responses on recursive resolvers.</p></body></html>",
        )
        monkeypatch.setattr(
            self.pipeline,
            "_summarize",
            lambda text, query: (
                "DNS poisoning may change cached responses on recursive resolvers.",
                ["dns", "poisoning"],
            ),
        )

        with caplog.at_level("WARNING", logger="backend.assistant.query_router"):
            result = self.pipeline.search("What is DNS poisoning?")

        assert result.status == ResearchStatus.SUCCESS
        assert "could not be fully verified" in result.summary
        assert result.query_result is not None
        assert result.query_result.result == result.summary
        assert result.query_result.grounded is False
        assert result.query_result.grounding_confidence >= 0.3
        assert result.query_result.production_ready is False
        assert any("grounding failed" in record.message.lower() for record in caplog.records)

    # ====================================================================
    # GUARDS
    # ====================================================================

    def test_cannot_access_training(self):
        assert ResearchSearchPipeline.can_access_training() is False

    def test_cannot_modify_governance(self):
        assert ResearchSearchPipeline.can_modify_governance() is False

    def test_cannot_execute_commands(self):
        assert ResearchSearchPipeline.can_execute_commands() is False

    def test_cannot_persist_data(self):
        assert ResearchSearchPipeline.can_persist_data() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
