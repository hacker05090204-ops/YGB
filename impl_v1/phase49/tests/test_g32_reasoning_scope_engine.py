# test_g32_reasoning_scope_engine.py
"""Tests for G32 Deterministic Reasoning & Scope Intelligence Engine."""

import pytest

from impl_v1.phase49.governors.g32_reasoning_scope_engine import (
    # Enums
    ScopeClassification,
    TestCategory,
    ContextIndicator,
    SuppressionReason,
    # Data structures
    ScopeAsset,
    ScopeIntelligenceResult,
    TestSelectionReasoning,
    TestSelectionResult,
    DuplicateCheckResult,
    ReasoningExplanation,
    # Functions
    parse_scope_text,
    detect_context_indicators,
    select_tests_for_context,
    check_duplicates,
    generate_reasoning_explanation,
    # Security guards
    can_reasoning_execute,
    can_reasoning_trigger_scan,
    can_reasoning_submit,
    can_reasoning_expand_scope,
    can_reasoning_generate_poc,
    can_reasoning_override_governance,
)


class TestScopeClassificationEnum:
    """Tests for ScopeClassification enum."""
    
    def test_has_4_classifications(self):
        assert len(ScopeClassification) == 4
    
    def test_has_allowed(self):
        assert ScopeClassification.ALLOWED.value == "ALLOWED"
    
    def test_has_conditional(self):
        assert ScopeClassification.CONDITIONAL.value == "CONDITIONAL"
    
    def test_has_forbidden(self):
        assert ScopeClassification.FORBIDDEN.value == "FORBIDDEN"
    
    def test_has_read_only(self):
        assert ScopeClassification.READ_ONLY.value == "READ_ONLY"


class TestTestCategoryEnum:
    """Tests for TestCategory enum."""
    
    def test_has_11_categories(self):
        assert len(TestCategory) == 11
    
    def test_has_xss(self):
        assert TestCategory.XSS.value == "XSS"
    
    def test_has_sqli(self):
        assert TestCategory.SQLI.value == "SQLI"
    
    def test_has_idor(self):
        assert TestCategory.IDOR.value == "IDOR"
    
    def test_has_ssrf(self):
        assert TestCategory.SSRF.value == "SSRF"
    
    def test_has_rce(self):
        assert TestCategory.RCE.value == "RCE"
    
    def test_has_csrf(self):
        assert TestCategory.CSRF.value == "CSRF"
    
    def test_has_auth(self):
        assert TestCategory.AUTH.value == "AUTH"
    
    def test_has_file_upload(self):
        assert TestCategory.FILE_UPLOAD.value == "FILE_UPLOAD"
    
    def test_has_graphql(self):
        assert TestCategory.GRAPHQL.value == "GRAPHQL"


class TestContextIndicatorEnum:
    """Tests for ContextIndicator enum."""
    
    def test_has_8_indicators(self):
        assert len(ContextIndicator) == 8
    
    def test_has_static_site(self):
        assert ContextIndicator.STATIC_SITE.value == "STATIC_SITE"
    
    def test_has_oauth_present(self):
        assert ContextIndicator.OAUTH_PRESENT.value == "OAUTH_PRESENT"
    
    def test_has_graphql_detected(self):
        assert ContextIndicator.GRAPHQL_DETECTED.value == "GRAPHQL_DETECTED"


class TestSuppressionReasonEnum:
    """Tests for SuppressionReason enum."""
    
    def test_has_5_reasons(self):
        assert len(SuppressionReason) == 5
    
    def test_has_none(self):
        assert SuppressionReason.NONE.value == "NONE"
    
    def test_has_cve_overlap(self):
        assert SuppressionReason.CVE_OVERLAP.value == "CVE_OVERLAP"
    
    def test_has_high_duplicate_zone(self):
        assert SuppressionReason.HIGH_DUPLICATE_ZONE.value == "HIGH_DUPLICATE_ZONE"


class TestScopeAssetDataclass:
    """Tests for ScopeAsset dataclass."""
    
    def test_is_frozen(self):
        asset = ScopeAsset(
            asset="*.example.com",
            classification=ScopeClassification.ALLOWED,
            conditions=tuple(),
            notes="In scope",
        )
        with pytest.raises(AttributeError):
            asset.asset = "changed"
    
    def test_has_required_fields(self):
        asset = ScopeAsset(
            asset="*.example.com",
            classification=ScopeClassification.ALLOWED,
            conditions=("condition",),
            notes="Note",
        )
        assert asset.asset == "*.example.com"
        assert asset.classification == ScopeClassification.ALLOWED
        assert asset.conditions == ("condition",)
        assert asset.notes == "Note"


class TestParseScopeText:
    """Tests for parse_scope_text function."""
    
    def test_parses_allowed_assets(self):
        scope = "In scope: *.example.com"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.allowed_assets) >= 1
        assert any("example.com" in a.asset for a in result.allowed_assets)
    
    def test_parses_forbidden_assets(self):
        scope = "Out of scope: admin.example.com"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.forbidden_assets) >= 1
    
    def test_parses_conditional_assets(self):
        scope = "If permission granted: api.example.com"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.conditional_assets) >= 1
    
    def test_parses_read_only_assets(self):
        scope = "Read only: docs.example.com"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.read_only_assets) >= 1
    
    def test_has_result_id(self):
        scope = "In scope: *.example.com"
        result = parse_scope_text(scope, "TestProgram")
        assert result.result_id.startswith("SCP-")
    
    def test_has_determinism_hash(self):
        scope = "In scope: *.example.com"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.determinism_hash) == 32
    
    def test_empty_scope_returns_notes(self):
        scope = "This program focuses on security testing."
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.notes) >= 1
    
    def test_parses_url_assets(self):
        """Test URL pattern extraction (lines 284-287)."""
        # Use localhost URL which won't match the domain pattern
        scope = "In scope: https://localhost:8080/api"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.allowed_assets) >= 1
    
    def test_parses_wildcard_assets(self):
        """Test fallback word extraction (lines 289-295)."""
        # Use pattern without standard TLD that only matches fallback
        scope = "Allowed: assets.*"
        result = parse_scope_text(scope, "TestProgram")
        assert len(result.allowed_assets) >= 1
    
    def test_handles_line_without_asset(self):
        """Test line without extractable asset (line 295 - return None)."""
        scope = "Out of scope: cannot test production systems"
        result = parse_scope_text(scope, "TestProgram")
        # Line matches forbidden marker but has no extractable asset
        # so it should not add to forbidden_assets
        assert len(result.forbidden_assets) == 0




class TestDeterministicScoping:
    """Tests for determinism in scope parsing."""
    
    def test_same_input_same_hash(self):
        scope = "In scope: *.example.com\nOut of scope: admin.example.com"
        result1 = parse_scope_text(scope, "TestProgram")
        result2 = parse_scope_text(scope, "TestProgram")
        assert result1.determinism_hash == result2.determinism_hash
    
    def test_different_input_different_hash(self):
        scope1 = "In scope: *.example.com"
        scope2 = "In scope: *.other.com"
        result1 = parse_scope_text(scope1, "TestProgram")
        result2 = parse_scope_text(scope2, "TestProgram")
        assert result1.determinism_hash != result2.determinism_hash


class TestDetectContextIndicators:
    """Tests for detect_context_indicators function."""
    
    def test_detects_oauth(self):
        dom = "Login with OAuth provider"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.OAUTH_PRESENT in indicators
    
    def test_detects_upload_form(self):
        dom = "enctype=\"multipart/form-data\" upload file"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.UPLOAD_FORM in indicators
    
    def test_detects_graphql(self):
        dom = "GraphQL API endpoint /graphql"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.GRAPHQL_DETECTED in indicators
    
    def test_detects_login_form(self):
        dom = "Enter your password to login"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.LOGIN_FORM in indicators
    
    def test_detects_api_endpoint(self):
        dom = "REST API endpoint /api/users returns JSON"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.API_ENDPOINT in indicators
    
    def test_detects_no_state(self):
        dom = "Simple static page with no forms"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.NO_STATE in indicators
    
    def test_detects_database_interaction(self):
        """Test database detection (line 385)."""
        dom = "SELECT * FROM users WHERE id = 1"
        indicators = detect_context_indicators(dom)
        assert ContextIndicator.DATABASE_INTERACTION in indicators
    
    def test_returns_tuple(self):
        dom = "Test content"
        indicators = detect_context_indicators(dom)
        assert isinstance(indicators, tuple)


class TestSelectTestsForContext:
    """Tests for select_tests_for_context function."""
    
    def test_static_site_disables_sqli(self):
        indicators = (ContextIndicator.STATIC_SITE,)
        result = select_tests_for_context(indicators)
        assert TestCategory.SQLI in result.disabled_tests
    
    def test_static_site_disables_csrf(self):
        indicators = (ContextIndicator.STATIC_SITE,)
        result = select_tests_for_context(indicators)
        assert TestCategory.CSRF in result.disabled_tests
    
    def test_oauth_enables_auth(self):
        indicators = (ContextIndicator.OAUTH_PRESENT,)
        result = select_tests_for_context(indicators)
        assert TestCategory.AUTH in result.enabled_tests
    
    def test_upload_form_enables_file_upload(self):
        indicators = (ContextIndicator.UPLOAD_FORM,)
        result = select_tests_for_context(indicators)
        assert TestCategory.FILE_UPLOAD in result.enabled_tests
    
    def test_graphql_enables_graphql_tests(self):
        indicators = (ContextIndicator.GRAPHQL_DETECTED,)
        result = select_tests_for_context(indicators)
        assert TestCategory.GRAPHQL in result.enabled_tests
    
    def test_no_state_disables_csrf(self):
        indicators = (ContextIndicator.NO_STATE,)
        result = select_tests_for_context(indicators)
        assert TestCategory.CSRF in result.disabled_tests
    
    def test_has_result_id(self):
        indicators = (ContextIndicator.LOGIN_FORM,)
        result = select_tests_for_context(indicators)
        assert result.result_id.startswith("TST-")
    
    def test_has_determinism_hash(self):
        indicators = (ContextIndicator.LOGIN_FORM,)
        result = select_tests_for_context(indicators)
        assert len(result.determinism_hash) == 32
    
    def test_includes_reasoning(self):
        indicators = (ContextIndicator.OAUTH_PRESENT,)
        result = select_tests_for_context(indicators)
        assert len(result.reasoning) == len(TestCategory)


class TestDeterministicTestSelection:
    """Tests for determinism in test selection."""
    
    def test_same_context_same_hash(self):
        indicators = (ContextIndicator.OAUTH_PRESENT, ContextIndicator.LOGIN_FORM)
        result1 = select_tests_for_context(indicators)
        result2 = select_tests_for_context(indicators)
        assert result1.determinism_hash == result2.determinism_hash
    
    def test_same_context_same_tests(self):
        indicators = (ContextIndicator.GRAPHQL_DETECTED,)
        result1 = select_tests_for_context(indicators)
        result2 = select_tests_for_context(indicators)
        assert result1.enabled_tests == result2.enabled_tests
        assert result1.disabled_tests == result2.disabled_tests


class TestCheckDuplicates:
    """Tests for check_duplicates function."""
    
    def test_cve_overlap_blocks(self):
        result = check_duplicates(
            target="example.com",
            cve_overlap_count=10,  # Above threshold
            historical_acceptance_rate=0.5,
            program_age_days=30,
            platform_duplicate_density=0.1,
        )
        assert result.should_proceed == False
        assert result.suppression_reason == SuppressionReason.CVE_OVERLAP
    
    def test_high_duplicate_density_blocks(self):
        result = check_duplicates(
            target="example.com",
            cve_overlap_count=1,
            historical_acceptance_rate=0.5,
            program_age_days=30,
            platform_duplicate_density=0.9,  # Above threshold
        )
        assert result.should_proceed == False
        assert result.suppression_reason == SuppressionReason.HIGH_DUPLICATE_ZONE
    
    def test_low_acceptance_blocks(self):
        result = check_duplicates(
            target="example.com",
            cve_overlap_count=1,
            historical_acceptance_rate=0.05,  # Below threshold
            program_age_days=30,
            platform_duplicate_density=0.1,
        )
        assert result.should_proceed == False
        assert result.suppression_reason == SuppressionReason.LOW_ACCEPTANCE_AREA
    
    def test_stale_program_blocks(self):
        result = check_duplicates(
            target="example.com",
            cve_overlap_count=1,
            historical_acceptance_rate=0.5,
            program_age_days=400,  # Above threshold
            platform_duplicate_density=0.1,
        )
        assert result.should_proceed == False
        assert result.suppression_reason == SuppressionReason.STALE_PROGRAM
    
    def test_clean_target_proceeds(self):
        result = check_duplicates(
            target="example.com",
            cve_overlap_count=1,
            historical_acceptance_rate=0.5,
            program_age_days=30,
            platform_duplicate_density=0.1,
        )
        assert result.should_proceed == True
        assert result.suppression_reason == SuppressionReason.NONE
    
    def test_has_result_id(self):
        result = check_duplicates("example.com", 1, 0.5, 30, 0.1)
        assert result.result_id.startswith("DUP-")
    
    def test_has_reasoning(self):
        result = check_duplicates("example.com", 1, 0.5, 30, 0.1)
        assert len(result.reasoning) > 0


class TestGenerateReasoningExplanation:
    """Tests for generate_reasoning_explanation function."""
    
    def test_generates_explanation(self):
        explanation = generate_reasoning_explanation(
            test_category=TestCategory.XSS,
            severity="HIGH",
            target="example.com",
            context_summary="web application",
        )
        assert isinstance(explanation, ReasoningExplanation)
    
    def test_has_explanation_id(self):
        explanation = generate_reasoning_explanation(
            TestCategory.SQLI, "CRITICAL", "example.com", "API"
        )
        assert explanation.explanation_id.startswith("EXP-")
    
    def test_has_why_this_matters(self):
        explanation = generate_reasoning_explanation(
            TestCategory.RCE, "CRITICAL", "example.com", "server"
        )
        assert len(explanation.why_this_matters) > 0
        assert "RCE" in explanation.why_this_matters
    
    def test_has_business_impact(self):
        explanation = generate_reasoning_explanation(
            TestCategory.IDOR, "HIGH", "example.com", "API"
        )
        assert len(explanation.business_impact) > 0
    
    def test_no_poc_in_explanation(self):
        explanation = generate_reasoning_explanation(
            TestCategory.XSS, "HIGH", "example.com", "web"
        )
        # Check that no exploit/payload content exists
        full_text = (
            explanation.why_this_matters +
            explanation.why_likely_accepted +
            explanation.business_impact +
            explanation.risk_framing
        ).lower()
        assert "<script>" not in full_text
        assert "payload" not in full_text
        # "exploitability" is acceptable terminology, but actual exploit code is not
        assert "exploit code" not in full_text
        assert "exploit steps" not in full_text
        assert "';--" not in full_text
        assert "union select" not in full_text

    
    def test_has_determinism_hash(self):
        explanation = generate_reasoning_explanation(
            TestCategory.AUTH, "MEDIUM", "example.com", "login"
        )
        assert len(explanation.determinism_hash) == 32


class TestDeterministicExplanation:
    """Tests for determinism in explanation generation."""
    
    def test_same_input_same_hash(self):
        explanation1 = generate_reasoning_explanation(
            TestCategory.SSRF, "CRITICAL", "example.com", "API"
        )
        explanation2 = generate_reasoning_explanation(
            TestCategory.SSRF, "CRITICAL", "example.com", "API"
        )
        assert explanation1.determinism_hash == explanation2.determinism_hash
    
    def test_same_input_same_content(self):
        explanation1 = generate_reasoning_explanation(
            TestCategory.SQLI, "HIGH", "example.com", "database"
        )
        explanation2 = generate_reasoning_explanation(
            TestCategory.SQLI, "HIGH", "example.com", "database"
        )
        assert explanation1.why_this_matters == explanation2.why_this_matters
        assert explanation1.business_impact == explanation2.business_impact


class TestCanReasoningExecute:
    """Tests for can_reasoning_execute guard."""
    
    def test_returns_false(self):
        can_exec, reason = can_reasoning_execute()
        assert can_exec == False
    
    def test_has_reason(self):
        can_exec, reason = can_reasoning_execute()
        assert len(reason) > 0
    
    def test_reason_mentions_cannot(self):
        can_exec, reason = can_reasoning_execute()
        assert "cannot" in reason.lower()


class TestCanReasoningTriggerScan:
    """Tests for can_reasoning_trigger_scan guard."""
    
    def test_returns_false(self):
        can_trigger, reason = can_reasoning_trigger_scan()
        assert can_trigger == False
    
    def test_has_reason(self):
        can_trigger, reason = can_reasoning_trigger_scan()
        assert len(reason) > 0
    
    def test_reason_mentions_human(self):
        can_trigger, reason = can_reasoning_trigger_scan()
        assert "human" in reason.lower()


class TestCanReasoningSubmit:
    """Tests for can_reasoning_submit guard."""
    
    def test_returns_false(self):
        can_submit, reason = can_reasoning_submit()
        assert can_submit == False
    
    def test_has_reason(self):
        can_submit, reason = can_reasoning_submit()
        assert len(reason) > 0
    
    def test_reason_mentions_submission(self):
        can_submit, reason = can_reasoning_submit()
        assert "submit" in reason.lower() or "submission" in reason.lower()


class TestCanReasoningExpandScope:
    """Tests for can_reasoning_expand_scope guard."""
    
    def test_returns_false(self):
        can_expand, reason = can_reasoning_expand_scope()
        assert can_expand == False
    
    def test_has_reason(self):
        can_expand, reason = can_reasoning_expand_scope()
        assert len(reason) > 0
    
    def test_reason_mentions_scope(self):
        can_expand, reason = can_reasoning_expand_scope()
        assert "scope" in reason.lower()


class TestCanReasoningGeneratePoc:
    """Tests for can_reasoning_generate_poc guard."""
    
    def test_returns_false(self):
        can_generate, reason = can_reasoning_generate_poc()
        assert can_generate == False
    
    def test_has_reason(self):
        can_generate, reason = can_reasoning_generate_poc()
        assert len(reason) > 0
    
    def test_reason_mentions_governance(self):
        can_generate, reason = can_reasoning_generate_poc()
        assert "governance" in reason.lower() or "forbidden" in reason.lower()


class TestCanReasoningOverrideGovernance:
    """Tests for can_reasoning_override_governance guard."""
    
    def test_returns_false(self):
        can_override, reason = can_reasoning_override_governance()
        assert can_override == False
    
    def test_has_reason(self):
        can_override, reason = can_reasoning_override_governance()
        assert len(reason) > 0
    
    def test_reason_mentions_immutable(self):
        can_override, reason = can_reasoning_override_governance()
        assert "immutable" in reason.lower() or "cannot" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive test that ALL guards return False."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_reasoning_execute,
            can_reasoning_trigger_scan,
            can_reasoning_submit,
            can_reasoning_expand_scope,
            can_reasoning_generate_poc,
            can_reasoning_override_governance,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result == False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0, f"Guard {guard.__name__} has empty reason!"


class TestFrozenDatastructures:
    """Tests that all datastructures are frozen."""
    
    def test_scope_intelligence_result_is_frozen(self):
        result = parse_scope_text("In scope: *.example.com", "Test")
        with pytest.raises(AttributeError):
            result.result_id = "changed"
    
    def test_test_selection_result_is_frozen(self):
        result = select_tests_for_context((ContextIndicator.LOGIN_FORM,))
        with pytest.raises(AttributeError):
            result.result_id = "changed"
    
    def test_duplicate_check_result_is_frozen(self):
        result = check_duplicates("example.com", 1, 0.5, 30, 0.1)
        with pytest.raises(AttributeError):
            result.result_id = "changed"
    
    def test_reasoning_explanation_is_frozen(self):
        result = generate_reasoning_explanation(TestCategory.XSS, "HIGH", "test", "web")
        with pytest.raises(AttributeError):
            result.explanation_id = "changed"


class TestForbiddenBehaviorBlocked:
    """Tests that forbidden behaviors are blocked."""
    
    def test_no_execution_capability(self):
        """G32 must not have any execution capability."""
        # Import and check no execution functions exist
        import impl_v1.phase49.governors.g32_reasoning_scope_engine as g32
        
        # Check no dangerous functions
        assert not hasattr(g32, 'execute_scan')
        assert not hasattr(g32, 'run_test')
        assert not hasattr(g32, 'trigger_action')
        assert not hasattr(g32, 'submit_report')
        assert not hasattr(g32, 'generate_payload')
        assert not hasattr(g32, 'create_exploit')
    
    def test_no_forbidden_imports(self):
        """G32 must not import execution-related modules."""
        import impl_v1.phase49.governors.g32_reasoning_scope_engine as g32
        import inspect
        
        source = inspect.getsource(g32)
        
        # These imports are forbidden
        assert "import subprocess" not in source
        assert "import socket" not in source
        assert "import requests" not in source
        assert "from os import" not in source
        assert "exec(" not in source
        assert "eval(" not in source
        assert "compile(" not in source


class TestIntegrationScopeToTest:
    """Integration tests for scope parsing to test selection flow."""
    
    def test_full_flow(self):
        # Parse scope
        scope = """
        In scope: *.example.com
        In scope: api.example.com
        Out of scope: admin.example.com
        """
        scope_result = parse_scope_text(scope, "Example Program")
        
        # Detect context from DOM
        dom = "OAuth login, REST API /api/users, GraphQL endpoint"
        indicators = detect_context_indicators(dom)
        
        # Select tests
        test_result = select_tests_for_context(indicators)
        
        # Check duplicates
        dup_result = check_duplicates(
            target="example.com",
            cve_overlap_count=2,
            historical_acceptance_rate=0.4,
            program_age_days=60,
            platform_duplicate_density=0.2,
        )
        
        # Generate explanation
        if dup_result.should_proceed and TestCategory.XSS in test_result.enabled_tests:
            explanation = generate_reasoning_explanation(
                TestCategory.XSS, "HIGH", "example.com", "OAuth web app"
            )
            assert explanation.explanation_id.startswith("EXP-")
        
        # Verify immutability throughout
        assert scope_result.determinism_hash is not None
        assert test_result.determinism_hash is not None
