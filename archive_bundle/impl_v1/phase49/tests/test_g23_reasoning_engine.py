# test_g23_reasoning_engine.py
"""Tests for G23 Governed Reasoning & Evidence Engine."""

import pytest

from impl_v1.phase49.governors.g23_reasoning_engine import (
    ReportSection,
    EvidenceType,
    ReasoningStatus,
    FORBIDDEN_WORDS,
    EvidenceItem,
    EvidencePack,
    ReportSectionContent,
    StructuredReport,
    VoiceScript,
    VideoNarrationMeta,
    ReasoningResult,
    create_evidence_item,
    create_evidence_pack,
    check_forbidden_words,
    generate_deterministic_hash,
    build_context_section,
    build_observations_section,
    build_reasoning_section,
    build_impact_section,
    build_reproduction_section,
    build_why_matters_section,
    generate_structured_report,
    generate_voice_script,
    generate_video_metadata,
    perform_reasoning,
    can_reasoning_execute,
    can_reasoning_decide,
    can_reasoning_modify_state,
)


class TestReportSection:
    """Tests for ReportSection enum."""
    
    def test_has_6_sections(self):
        assert len(ReportSection) == 6
    
    def test_has_context(self):
        assert ReportSection.CONTEXT.value == "CONTEXT"
    
    def test_has_observations(self):
        assert ReportSection.OBSERVATIONS.value == "OBSERVATIONS"
    
    def test_has_logical_reasoning(self):
        assert ReportSection.LOGICAL_REASONING.value == "LOGICAL_REASONING"
    
    def test_has_impact_analysis(self):
        assert ReportSection.IMPACT_ANALYSIS.value == "IMPACT_ANALYSIS"
    
    def test_has_reproduction_steps(self):
        assert ReportSection.REPRODUCTION_STEPS.value == "REPRODUCTION_STEPS"
    
    def test_has_why_this_matters(self):
        assert ReportSection.WHY_THIS_MATTERS.value == "WHY_THIS_MATTERS"


class TestEvidenceType:
    """Tests for EvidenceType enum."""
    
    def test_has_5_types(self):
        assert len(EvidenceType) == 5
    
    def test_has_browser_observation(self):
        assert EvidenceType.BROWSER_OBSERVATION.value == "BROWSER_OBSERVATION"
    
    def test_has_scope_extraction(self):
        assert EvidenceType.SCOPE_EXTRACTION.value == "SCOPE_EXTRACTION"


class TestForbiddenWords:
    """Tests for forbidden words list."""
    
    def test_maybe_forbidden(self):
        assert "maybe" in FORBIDDEN_WORDS
    
    def test_likely_forbidden(self):
        assert "likely" in FORBIDDEN_WORDS
    
    def test_could_be_forbidden(self):
        assert "could be" in FORBIDDEN_WORDS
    
    def test_possibly_forbidden(self):
        assert "possibly" in FORBIDDEN_WORDS
    
    def test_might_forbidden(self):
        assert "might" in FORBIDDEN_WORDS


class TestCheckForbiddenWords:
    """Tests for check_forbidden_words function."""
    
    def test_clean_text_passes(self):
        has_forbidden, word = check_forbidden_words("This is a clear statement.")
        assert has_forbidden == False
        assert word is None
    
    def test_maybe_detected(self):
        has_forbidden, word = check_forbidden_words("This maybe works")
        assert has_forbidden == True
        assert word == "maybe"
    
    def test_likely_detected(self):
        has_forbidden, word = check_forbidden_words("This is likely a bug")
        assert has_forbidden == True
        assert word == "likely"
    
    def test_could_be_detected(self):
        has_forbidden, word = check_forbidden_words("It could be vulnerable")
        assert has_forbidden == True
        assert word == "could be"
    
    def test_case_insensitive(self):
        has_forbidden, _ = check_forbidden_words("This MAYBE works")
        assert has_forbidden == True


class TestCreateEvidenceItem:
    """Tests for create_evidence_item function."""
    
    def test_creates_item(self):
        item = create_evidence_item(
            EvidenceType.BROWSER_OBSERVATION,
            "G19",
            "Page title: Test"
        )
        assert isinstance(item, EvidenceItem)
    
    def test_item_has_id(self):
        item = create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope")
        assert item.evidence_id.startswith("EVI-")
    
    def test_item_has_checksum(self):
        item = create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "CVE data")
        assert len(item.checksum) == 16
    
    def test_same_content_same_checksum(self):
        item1 = create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "test")
        item2 = create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "test")
        assert item1.checksum == item2.checksum


class TestCreateEvidencePack:
    """Tests for create_evidence_pack function."""
    
    def _create_full_pack(self):
        return create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
    
    def test_complete_pack(self):
        pack = self._create_full_pack()
        assert pack.is_complete == True
        assert len(pack.missing_types) == 0
    
    def test_incomplete_pack_missing_browser(self):
        pack = create_evidence_pack(
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
        assert pack.is_complete == False
        assert EvidenceType.BROWSER_OBSERVATION in pack.missing_types
    
    def test_empty_pack_all_missing(self):
        pack = create_evidence_pack()
        assert pack.is_complete == False
        assert len(pack.missing_types) == 5


class TestDeterministicHash:
    """Tests for deterministic hash generation."""
    
    def _create_full_pack(self):
        return create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
    
    def test_same_input_same_hash(self):
        pack1 = self._create_full_pack()
        pack2 = self._create_full_pack()
        
        # Same pack_id needed for same hash
        hash1 = generate_deterministic_hash(pack1, "XSS", "HIGH")
        hash2 = generate_deterministic_hash(pack1, "XSS", "HIGH")
        assert hash1 == hash2
    
    def test_different_bug_type_different_hash(self):
        pack = self._create_full_pack()
        hash1 = generate_deterministic_hash(pack, "XSS", "HIGH")
        hash2 = generate_deterministic_hash(pack, "SQLi", "HIGH")
        assert hash1 != hash2


class TestBuildSections:
    """Tests for section building functions."""
    
    def _create_full_pack(self):
        return create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "Browser obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "*.example.com"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "HackerOne"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "No CVE"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "Screenshot"),
        )
    
    def test_context_section(self):
        pack = self._create_full_pack()
        section = build_context_section(pack, "example.com", "XSS")
        assert section.section == ReportSection.CONTEXT
        assert "example.com" in section.content
    
    def test_observations_section(self):
        pack = self._create_full_pack()
        section = build_observations_section(pack)
        assert section.section == ReportSection.OBSERVATIONS
        assert "Browser" in section.content
    
    def test_reasoning_section_xss(self):
        pack = self._create_full_pack()
        section = build_reasoning_section("XSS", pack)
        assert "sanitization" in section.content or "injection" in section.content
    
    def test_reasoning_section_sqli(self):
        pack = self._create_full_pack()
        section = build_reasoning_section("SQLi", pack)
        assert "parameterization" in section.content or "query" in section.content
    
    def test_impact_section(self):
        section = build_impact_section("CRITICAL", "RCE")
        assert section.section == ReportSection.IMPACT_ANALYSIS
    
    def test_reproduction_section(self):
        steps = ["Open URL", "Enter payload", "Observe response"]
        section = build_reproduction_section(steps)
        assert section.section == ReportSection.REPRODUCTION_STEPS
        assert "1." in section.content
        assert "2." in section.content


class TestGenerateStructuredReport:
    """Tests for generate_structured_report function."""
    
    def _create_full_pack(self):
        return create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
    
    def test_generates_report(self):
        pack = self._create_full_pack()
        report = generate_structured_report(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert isinstance(report, StructuredReport)
    
    def test_report_has_6_sections(self):
        pack = self._create_full_pack()
        report = generate_structured_report(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert len(report.sections) == 6
    
    def test_report_has_determinism_hash(self):
        pack = self._create_full_pack()
        report = generate_structured_report(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert len(report.determinism_hash) == 32


class TestGenerateVoiceScript:
    """Tests for generate_voice_script function."""
    
    def _create_report(self):
        pack = create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
        return generate_structured_report(pack, "example.com", "XSS", "HIGH", ["Step 1"])
    
    def test_generates_english_script(self):
        report = self._create_report()
        script = generate_voice_script(report, "EN")
        assert script.language == "EN"
    
    def test_generates_hindi_script(self):
        report = self._create_report()
        script = generate_voice_script(report, "HI")
        assert script.language == "HI"
    
    def test_script_has_sections(self):
        report = self._create_report()
        script = generate_voice_script(report, "EN")
        assert len(script.sections) == 6


class TestPerformReasoning:
    """Tests for perform_reasoning function."""
    
    def _create_full_pack(self):
        return create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
    
    def test_success_with_complete_evidence(self):
        pack = self._create_full_pack()
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.status == ReasoningStatus.SUCCESS
    
    def test_has_report(self):
        pack = self._create_full_pack()
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.report is not None
    
    def test_has_voice_en(self):
        pack = self._create_full_pack()
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.voice_script_en is not None
    
    def test_has_voice_hi(self):
        pack = self._create_full_pack()
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.voice_script_hi is not None
    
    def test_has_video_meta(self):
        pack = self._create_full_pack()
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.video_meta is not None


class TestMissingEvidenceFails:
    """Tests that missing evidence causes HARD FAIL."""
    
    def test_empty_pack_fails(self):
        pack = create_evidence_pack()  # All missing
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.status == ReasoningStatus.MISSING_EVIDENCE
    
    def test_missing_browser_fails(self):
        pack = create_evidence_pack(
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.status == ReasoningStatus.MISSING_EVIDENCE
        assert "BROWSER_OBSERVATION" in result.error_message
    
    def test_report_is_none_on_fail(self):
        pack = create_evidence_pack()
        result = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        assert result.report is None


class TestDeterminism:
    """Tests that same input produces same output."""
    
    def test_same_input_same_hash(self):
        # Create identical packs with same content
        pack = create_evidence_pack(
            browser_observation=create_evidence_item(EvidenceType.BROWSER_OBSERVATION, "G19", "obs"),
            scope_extraction=create_evidence_item(EvidenceType.SCOPE_EXTRACTION, "G19", "scope"),
            platform_metadata=create_evidence_item(EvidenceType.PLATFORM_METADATA, "G19", "platform"),
            cve_context=create_evidence_item(EvidenceType.CVE_CONTEXT, "G15", "cve"),
            screen_evidence=create_evidence_item(EvidenceType.SCREEN_EVIDENCE, "G18", "screen"),
        )
        
        result1 = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        result2 = perform_reasoning(pack, "example.com", "XSS", "HIGH", ["Step 1"])
        
        # Same report content
        assert result1.report.determinism_hash == result2.report.determinism_hash


class TestCanReasoningExecute:
    """Tests for can_reasoning_execute guard."""
    
    def test_cannot_execute(self):
        can_exec, reason = can_reasoning_execute()
        assert can_exec == False
        assert "cannot execute" in reason.lower()


class TestCanReasoningDecide:
    """Tests for can_reasoning_decide guard."""
    
    def test_cannot_decide(self):
        can_decide, reason = can_reasoning_decide()
        assert can_decide == False
        assert "human" in reason.lower() or "cannot approve" in reason.lower()


class TestCanReasoningModifyState:
    """Tests for can_reasoning_modify_state guard."""
    
    def test_cannot_modify(self):
        can_modify, reason = can_reasoning_modify_state()
        assert can_modify == False
        assert "read-only" in reason.lower()
