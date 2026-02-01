# Test G37: Autonomous Hunter
"""
Tests for G37 autonomous hunter and reporter.

100% coverage required.
"""

import pytest
import json

from impl_v1.phase49.governors.g37_autonomous_hunter import (
    # Enums
    AutoMode,
    ReportQuality,
    # Dataclasses
    VulnerabilityTitle,
    ProofEvidence,
    DuplicateAnalysis,
    NoiseAnalysis,
    ImpactAnalysis,
    AutonomousReport,
    HunterStats,
    # Functions
    create_vulnerability_title,
    create_proof_evidence,
    analyze_duplicates,
    analyze_noise,
    analyze_impact,
    calculate_report_quality,
    generate_autonomous_report,
    export_report_json,
    export_report_markdown,
    calculate_hunter_stats,
    verify_accuracy_targets,
    # Guards
    can_g37_execute_exploit,
    can_g37_submit_report,
    can_g37_expand_scope,
    can_g37_override_g36,
    can_g37_ignore_duplicates,
    can_g37_accept_without_proof,
    can_g37_bypass_governance,
)


class TestAutoModeEnum:
    """Tests for AutoMode enum."""
    
    def test_has_discovery(self):
        assert AutoMode.DISCOVERY.value == "DISCOVERY"
    
    def test_has_verification(self):
        assert AutoMode.VERIFICATION.value == "VERIFICATION"
    
    def test_has_idle(self):
        assert AutoMode.IDLE.value == "IDLE"


class TestReportQualityEnum:
    """Tests for ReportQuality enum."""
    
    def test_has_high(self):
        assert ReportQuality.HIGH.value == "HIGH"
    
    def test_has_needs_human(self):
        assert ReportQuality.NEEDS_HUMAN.value == "NEEDS_HUMAN"


class TestCreateVulnerabilityTitle:
    """Tests for create_vulnerability_title."""
    
    def test_creates_title(self):
        title = create_vulnerability_title(
            bug_type="SQLi",
            target="example.com",
            endpoint="/login",
            impact_summary="SQL injection allows data extraction",
        )
        
        assert title.bug_type == "SQLi"
        assert title.target == "example.com"
        assert title.endpoint == "/login"


class TestCreateProofEvidence:
    """Tests for create_proof_evidence."""
    
    def test_creates_proof(self):
        proof = create_proof_evidence(
            controlled_input="id=1' OR 1=1--",
            response_before="Invalid login",
            response_after="Welcome admin",
            reproduction_steps=("Navigate", "Enter payload", "Observe"),
            screenshots=("/path/s1.png",),
            video_path="/path/poc.webm",
            video_timestamps=(0, 3000, 5000),
            request_data="POST /login",
            response_data="200 OK",
        )
        
        assert "id=1' OR 1=1--" in proof.controlled_input
        assert "BEFORE:" in proof.response_delta
        assert "AFTER:" in proof.response_delta
        assert len(proof.reproduction_steps) == 3


class TestAnalyzeDuplicates:
    """Tests for analyze_duplicates."""
    
    def test_identifies_duplicate(self):
        finding_hash = "abc123"
        existing = ("abc123", "def456")
        
        analysis = analyze_duplicates(finding_hash, existing)
        
        assert analysis.is_duplicate is True
        assert analysis.similarity_score == 1.0
    
    def test_identifies_not_duplicate(self):
        finding_hash = "xyz789"
        existing = ("abc123", "def456")
        
        analysis = analyze_duplicates(finding_hash, existing)
        
        assert analysis.is_duplicate is False
        assert "below threshold" in analysis.why_not_duplicate.lower()
    
    def test_empty_existing_reports(self):
        analysis = analyze_duplicates("abc", tuple())
        
        assert analysis.is_duplicate is False
        assert analysis.checked_against_count == 0


class TestAnalyzeNoise:
    """Tests for analyze_noise."""
    
    def test_identifies_scanner_noise(self):
        analysis = analyze_noise("Missing X-Frame-Options header")
        
        assert analysis.is_noise is True
        assert "IS NOISE" in analysis.why_not_noise
    
    def test_identifies_cookie_noise(self):
        analysis = analyze_noise("Cookie flag missing on session cookie")
        
        assert analysis.is_noise is True
    
    def test_real_finding_not_noise(self):
        analysis = analyze_noise("SQL injection in login allows database dump")
        
        assert analysis.is_noise is False
        assert "does not match" in analysis.why_not_noise.lower()


class TestAnalyzeImpact:
    """Tests for analyze_impact."""
    
    def test_critical_for_rce_with_data(self):
        impact = analyze_impact("RCE", data_exposed=True, auth_bypass=False, affected_scope="server")
        
        assert impact.severity == "CRITICAL"
        assert "compromise" in impact.business_impact.lower()
    
    def test_high_for_auth_bypass(self):
        impact = analyze_impact("AUTH", data_exposed=False, auth_bypass=True, affected_scope="users")
        
        assert impact.severity == "HIGH"
        assert "unauthorized" in impact.business_impact.lower()


class TestCalculateReportQuality:
    """Tests for calculate_report_quality."""
    
    def test_needs_human_for_duplicate(self):
        proof = create_proof_evidence("x", "a", "b", tuple(), tuple(), "", tuple(), "", "")
        dup = DuplicateAnalysis(True, 1.0, "Is duplicate", 1)
        noise = NoiseAnalysis(False, tuple(), "Not noise")
        
        quality = calculate_report_quality(proof, dup, noise, 95)
        
        assert quality == ReportQuality.NEEDS_HUMAN
    
    def test_needs_human_for_noise(self):
        proof = create_proof_evidence("x", "a", "b", tuple(), tuple(), "", tuple(), "", "")
        dup = DuplicateAnalysis(False, 0.1, "Not dup", 0)
        noise = NoiseAnalysis(True, tuple(), "Is noise")
        
        quality = calculate_report_quality(proof, dup, noise, 95)
        
        assert quality == ReportQuality.NEEDS_HUMAN
    
    def test_high_quality_with_all_proof(self):
        proof = create_proof_evidence(
            "x", "a", "b",
            ("Step 1", "Step 2", "Step 3"),
            ("/s1.png",),
            "/video.webm",
            (0,),
            "req", "resp",
        )
        dup = DuplicateAnalysis(False, 0.1, "Not dup", 0)
        noise = NoiseAnalysis(False, tuple(), "Not noise")
        
        quality = calculate_report_quality(proof, dup, noise, 95)
        
        assert quality == ReportQuality.HIGH


class TestGenerateAutonomousReport:
    """Tests for generate_autonomous_report."""
    
    def test_generates_report(self):
        report = generate_autonomous_report(
            bug_type="SQLi",
            target="example.com",
            endpoint="/login",
            controlled_input="id=1' OR 1=1--",
            response_before="Invalid",
            response_after="Welcome admin",
            reproduction_steps=("Step 1", "Step 2"),
            screenshots=("/s.png",),
            video_path="/poc.webm",
            video_timestamps=(0, 3000),
            request_data="POST /login",
            response_data="200 OK",
            existing_reports=tuple(),
            data_exposed=True,
            auth_bypass=True,
            confidence=90,
        )
        
        assert report.report_id.startswith("G37-RPT-")
        assert report.title.bug_type == "SQLi"
        assert report.auto_mode is True
        assert report.confidence == 90
    
    def test_report_is_frozen(self):
        report = generate_autonomous_report(
            "XSS", "example.com", "/page", "<script>",
            "clean", "alert(1)",
            ("nav", "inject"),
            tuple(), "/v.webm", tuple(),
            "req", "resp", tuple(),
        )
        
        with pytest.raises(AttributeError):
            report.confidence = 100


class TestExportReportJson:
    """Tests for export_report_json."""
    
    def test_exports_valid_json(self):
        report = generate_autonomous_report(
            "IDOR", "api.com", "/user/123", "id=456",
            "user123", "user456",
            ("GET", "Change ID"),
            tuple(), "/v.webm", (0,),
            "req", "resp", tuple(),
        )
        
        json_bytes = export_report_json(report)
        
        assert isinstance(json_bytes, bytes)
        data = json.loads(json_bytes.decode("utf-8"))
        assert "report_id" in data
        assert "title" in data
        assert "proof" in data


class TestExportReportMarkdown:
    """Tests for export_report_markdown."""
    
    def test_exports_markdown(self):
        report = generate_autonomous_report(
            "AUTH", "login.com", "/bypass", "token=invalid",
            "denied", "granted",
            ("Login", "Bypass"),
            tuple(), "/v.webm", (0,),
            "req", "resp", tuple(),
            auth_bypass=True,
        )
        
        md = export_report_markdown(report)
        
        assert "# AUTH Vulnerability" in md
        assert "## Summary" in md
        assert "## Proof of Concept" in md
        assert "## Why This Is NOT a Duplicate" in md


class TestHunterStats:
    """Tests for hunter statistics."""
    
    def test_calculates_stats(self):
        stats = calculate_hunter_stats(
            candidates=1000,
            false_positives=0,
            duplicates=1,
            noise=50,
            verified=100,
            needs_human=849,
        )
        
        assert stats.total_candidates == 1000
        assert stats.false_positive_rate == 0.0
        assert stats.duplicate_rate == 0.001
    
    def test_verify_accuracy_targets_pass(self):
        stats = HunterStats(
            total_candidates=1000,
            false_positives_rejected=0,
            duplicates_rejected=0,
            noise_rejected=50,
            verified_real=100,
            needs_human=850,
            false_positive_rate=0.0,
            duplicate_rate=0.0,
        )
        
        passes, reason = verify_accuracy_targets(stats)
        
        assert passes is True
        assert "met" in reason.lower()
    
    def test_verify_accuracy_targets_fail_fp(self):
        stats = HunterStats(
            total_candidates=100,
            false_positives_rejected=0,
            duplicates_rejected=0,
            noise_rejected=0,
            verified_real=100,
            needs_human=0,
            false_positive_rate=0.1,  # 10% - way over
            duplicate_rate=0.0,
        )
        
        passes, reason = verify_accuracy_targets(stats)
        
        assert passes is False
        assert "false positive" in reason.lower()


class TestGuards:
    """Tests for all guards."""
    
    def test_can_g37_execute_exploit_returns_false(self):
        can_execute, reason = can_g37_execute_exploit()
        assert can_execute is False
        assert "read-only" in reason.lower()
    
    def test_can_g37_submit_report_returns_false(self):
        can_submit, reason = can_g37_submit_report()
        assert can_submit is False
        assert "human" in reason.lower()
    
    def test_can_g37_expand_scope_returns_false(self):
        can_expand, reason = can_g37_expand_scope()
        assert can_expand is False
        assert "fixed" in reason.lower()
    
    def test_can_g37_override_g36_returns_false(self):
        can_override, reason = can_g37_override_g36()
        assert can_override is False
        assert "g36" in reason.lower()
    
    def test_can_g37_ignore_duplicates_returns_false(self):
        can_ignore, reason = can_g37_ignore_duplicates()
        assert can_ignore is False
        assert "duplicate" in reason.lower()
    
    def test_can_g37_accept_without_proof_returns_false(self):
        can_accept, reason = can_g37_accept_without_proof()
        assert can_accept is False
        assert "proof" in reason.lower()
    
    def test_can_g37_bypass_governance_returns_false(self):
        can_bypass, reason = can_g37_bypass_governance()
        assert can_bypass is False
        assert "absolute" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive guard test."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_g37_execute_exploit,
            can_g37_submit_report,
            can_g37_expand_scope,
            can_g37_override_g36,
            can_g37_ignore_duplicates,
            can_g37_accept_without_proof,
            can_g37_bypass_governance,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result is False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0, f"Guard {guard.__name__} has empty reason!"


class TestFrozenDataclasses:
    """Test all dataclasses are frozen."""
    
    def test_vulnerability_title_frozen(self):
        title = create_vulnerability_title("XSS", "t", "/e", "s")
        with pytest.raises(AttributeError):
            title.bug_type = "SQLi"
    
    def test_proof_evidence_frozen(self):
        proof = create_proof_evidence("x", "a", "b", tuple(), tuple(), "", tuple(), "", "")
        with pytest.raises(AttributeError):
            proof.controlled_input = "y"


class TestNoForbiddenImports:
    """Test no forbidden imports."""
    
    def test_no_forbidden_imports(self):
        import impl_v1.phase49.governors.g37_autonomous_hunter as g37
        import inspect
        
        source = inspect.getsource(g37)
        
        forbidden = ["subprocess", "socket", "selenium", "playwright"]
        for name in forbidden:
            assert f"import {name}" not in source


class TestNoExploitExecution:
    """Critical: G37 cannot execute exploits."""
    
    def test_report_generation_does_not_execute(self):
        # Calling generate_autonomous_report should NOT execute anything
        report = generate_autonomous_report(
            bug_type="RCE",
            target="critical.com",
            endpoint="/admin/exec",
            controlled_input="cmd=rm -rf /",
            response_before="denied",
            response_after="executed",
            reproduction_steps=("send payload",),
            screenshots=tuple(),
            video_path="/v.webm",
            video_timestamps=tuple(),
            request_data="req",
            response_data="resp",
            existing_reports=tuple(),
        )
        
        # Report was generated but nothing was executed
        assert report.auto_mode is True
        assert can_g37_execute_exploit()[0] is False
