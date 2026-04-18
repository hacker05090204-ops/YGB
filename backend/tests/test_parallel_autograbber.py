"""Phase 8 parallel autograbber test suite."""

from __future__ import annotations

import pytest

from backend.ingestion.industrial_autograbber import IndustrialAutoGrabber
from backend.ingestion.parallel_autograbber import (
    FieldRouter,
    ParallelAutoGrabber,
    ParallelAutoGrabberConfig,
    route_vulnerability_text_to_expert,
)


class TestFieldRouter:
    """Test FieldRouter expert routing logic."""

    def test_route_sql_injection(self):
        """Test routing SQL injection to expert 1."""
        sample = {"description": "SQL injection vulnerability in login form"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 1, f"Expected expert 1 (SQLi), got {expert_id}"

    def test_route_xss(self):
        """Test routing XSS to expert 2."""
        sample = {"description": "Cross-site scripting vulnerability allows script injection"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 2, f"Expected expert 2 (XSS), got {expert_id}"

    def test_route_rce(self):
        """Test routing RCE to expert 3."""
        sample = {"description": "Remote code execution via command injection"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 3, f"Expected expert 3 (RCE), got {expert_id}"

    def test_route_auth_bypass(self):
        """Test routing auth bypass to expert 4."""
        sample = {"description": "Authentication bypass allows account takeover"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 4, f"Expected expert 4 (auth bypass), got {expert_id}"

    def test_route_ssrf(self):
        """Test routing SSRF to expert 5."""
        sample = {"description": "Server-side request forgery vulnerability"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 5, f"Expected expert 5 (SSRF), got {expert_id}"

    def test_route_csrf(self):
        """Test routing CSRF to expert 6."""
        sample = {"description": "Cross-site request forgery token bypass"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 6, f"Expected expert 6 (CSRF), got {expert_id}"

    def test_route_file_upload(self):
        """Test routing file upload to expert 7."""
        sample = {"description": "Unrestricted file upload vulnerability"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 7, f"Expected expert 7 (file upload), got {expert_id}"

    def test_route_graphql(self):
        """Test routing GraphQL to expert 8."""
        sample = {"description": "GraphQL introspection enabled allows schema enumeration"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 8, f"Expected expert 8 (GraphQL), got {expert_id}"

    def test_route_cloud_misconfig(self):
        """Test routing cloud misconfig to expert 9."""
        sample = {"description": "AWS S3 bucket misconfiguration exposes sensitive data"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 9, f"Expected expert 9 (cloud misconfig), got {expert_id}"

    def test_route_mobile(self):
        """Test routing mobile to expert 10."""
        sample = {"description": "Android APK vulnerability in mobile application"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 10, f"Expected expert 10 (mobile), got {expert_id}"

    def test_route_idor(self):
        """Test routing IDOR to expert 11."""
        sample = {"description": "Insecure direct object reference allows unauthorized access"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 11, f"Expected expert 11 (IDOR), got {expert_id}"

    def test_route_deserialization(self):
        """Test routing deserialization to expert 12."""
        sample = {"description": "Unsafe deserialization of pickle data"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 12, f"Expected expert 12 (deserialization), got {expert_id}"

    def test_route_rest_api(self):
        """Test routing REST API to expert 13."""
        sample = {"description": "REST API endpoint abuse vulnerability"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 13, f"Expected expert 13 (REST), got {expert_id}"

    def test_route_web_app(self):
        """Test routing web app to expert 14."""
        sample = {"description": "Web application HTTP vulnerability"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 14, f"Expected expert 14 (web app), got {expert_id}"

    def test_route_blockchain(self):
        """Test routing blockchain to expert 16."""
        sample = {"description": "Smart contract vulnerability in Ethereum Solidity code"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 16, f"Expected expert 16 (blockchain), got {expert_id}"

    def test_route_cryptography(self):
        """Test routing cryptography to expert 20."""
        sample = {"description": "Weak cipher encryption vulnerability"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 20, f"Expected expert 20 (cryptography), got {expert_id}"

    def test_route_subdomain_takeover(self):
        """Test routing subdomain takeover to expert 21."""
        sample = {"description": "Subdomain takeover via dangling CNAME record"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 21, f"Expected expert 21 (subdomain takeover), got {expert_id}"

    def test_route_race_condition(self):
        """Test routing race condition to expert 22."""
        sample = {"description": "Race condition TOCTOU vulnerability"}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 22, f"Expected expert 22 (race condition), got {expert_id}"

    def test_route_empty_sample(self):
        """Test routing empty sample defaults to expert 0."""
        sample = {"description": ""}
        expert_id = FieldRouter.route(sample)
        assert expert_id == 0, f"Expected expert 0 (general triage), got {expert_id}"

    def test_route_unknown_vulnerability(self):
        """Test routing unknown vulnerability defaults to expert 0."""
        sample = {"description": "Some unknown vulnerability type"}
        expert_id = FieldRouter.route(sample)
        # Should default to 0 if no keywords match
        assert 0 <= expert_id <= 22, f"Expert ID {expert_id} out of range"

    def test_route_with_tags(self):
        """Test routing considers tags."""
        sample = {
            "description": "Vulnerability in application",
            "tags": ["sql", "injection"]
        }
        expert_id = FieldRouter.route(sample)
        assert expert_id == 1, f"Expected expert 1 (SQLi from tags), got {expert_id}"

    def test_route_with_title(self):
        """Test routing considers title."""
        sample = {
            "title": "XSS vulnerability",
            "description": "Some description"
        }
        expert_id = FieldRouter.route(sample)
        assert expert_id == 2, f"Expected expert 2 (XSS from title), got {expert_id}"

    def test_routing_keywords_coverage(self):
        """Test all expert IDs 0-22 have routing keywords."""
        for expert_id in range(23):
            assert expert_id in FieldRouter.ROUTING_KEYWORDS, \
                f"Expert {expert_id} missing from ROUTING_KEYWORDS"
            keywords = FieldRouter.ROUTING_KEYWORDS[expert_id]
            assert len(keywords) > 0, f"Expert {expert_id} has no keywords"


class TestRouteVulnerabilityTextToExpert:
    """Test legacy route_vulnerability_text_to_expert function."""

    def test_route_sql_injection_text(self):
        """Test routing SQL injection text."""
        route = route_vulnerability_text_to_expert(
            "SQL injection vulnerability in login form"
        )
        assert route.expert_id == 1, f"Expected expert 1, got {route.expert_id}"
        assert route.expert_label == "database_injection"

    def test_route_with_tags(self):
        """Test routing with tags."""
        route = route_vulnerability_text_to_expert(
            "Vulnerability in application",
            tags=["xss", "cross-site"]
        )
        assert route.expert_id == 2, f"Expected expert 2, got {route.expert_id}"

    def test_route_empty_text(self):
        """Test routing empty text defaults to general triage."""
        route = route_vulnerability_text_to_expert("")
        assert route.expert_id == 0
        assert route.expert_label == "general_triage"


class TestParallelAutoGrabber:
    """Test ParallelAutoGrabber initialization and configuration."""

    def test_initialization(self):
        """Test ParallelAutoGrabber initializes correctly."""
        config = ParallelAutoGrabberConfig(
            sources=["nvd"],
            max_per_cycle=10,
            max_workers=2
        )
        grabber = ParallelAutoGrabber(config)
        assert isinstance(grabber, ParallelAutoGrabber)
        assert grabber.config.max_workers == 2
        assert "nvd" in grabber.config.sources

    def test_initialization_with_base_config(self):
        """Test ParallelAutoGrabber accepts base AutoGrabberConfig."""
        from backend.ingestion.autograbber import AutoGrabberConfig
        
        config = AutoGrabberConfig(
            sources=["nvd", "cisa"],
            max_per_cycle=5
        )
        grabber = ParallelAutoGrabber(config)
        assert isinstance(grabber, ParallelAutoGrabber)
        assert isinstance(grabber.config, ParallelAutoGrabberConfig)

    def test_resolve_max_workers_default(self):
        """Test max_workers resolution with default config."""
        config = ParallelAutoGrabberConfig(
            sources=["nvd", "cisa", "exploitdb"],
            max_per_cycle=10
        )
        grabber = ParallelAutoGrabber(config)
        workers = grabber._resolve_max_workers()
        assert workers >= 1, "Should have at least 1 worker"
        assert workers <= 10, "Should not exceed reasonable limit"

    def test_resolve_max_workers_explicit(self):
        """Test max_workers resolution with explicit value."""
        config = ParallelAutoGrabberConfig(
            sources=["nvd", "cisa"],
            max_per_cycle=10,
            max_workers=3
        )
        grabber = ParallelAutoGrabber(config)
        workers = grabber._resolve_max_workers()
        assert workers == 2, "Should cap at number of sources (2)"

    def test_route_sample_to_expert_scraped_sample(self):
        """Test routing ScrapedSample to expert."""
        from backend.ingestion.scrapers import ScrapedSample
        
        config = ParallelAutoGrabberConfig(sources=["nvd"], max_per_cycle=1)
        grabber = ParallelAutoGrabber(config)
        
        sample = ScrapedSample(
            source="nvd",
            advisory_id="CVE-2024-1234",
            url="https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
            title="SQL Injection",
            description="SQL injection in login form",
            severity="HIGH"
        )
        
        route = grabber.route_sample_to_expert(sample)
        assert route.expert_id == 1, f"Expected expert 1, got {route.expert_id}"

    def test_route_sample_to_expert_dict(self):
        """Test routing dict sample to expert."""
        config = ParallelAutoGrabberConfig(sources=["nvd"], max_per_cycle=1)
        grabber = ParallelAutoGrabber(config)
        
        sample = {
            "description": "Cross-site scripting XSS vulnerability allows script injection",
            "source": "nvd"
        }
        
        route = grabber.route_sample_to_expert(sample)
        assert route.expert_id == 2, f"Expected expert 2, got {route.expert_id}"

    def test_available_scraper_types(self):
        """Test _available_scraper_types returns scraper registry."""
        scraper_types = ParallelAutoGrabber._available_scraper_types()
        assert isinstance(scraper_types, dict)
        assert len(scraper_types) > 0, "Should have at least one scraper"
        assert "nvd" in scraper_types, "Should include NVD scraper"

    def test_industrial_available_scraper_types_include_group_d_sources(self):
        """Industrial registry must expose Alpine and Debian sources."""
        scraper_types = IndustrialAutoGrabber._available_scraper_types()
        assert "alpine" in scraper_types
        assert "debian" in scraper_types

    def test_industrial_grabber_accepts_alpine_and_debian_sources(self):
        """IndustrialAutoGrabber must resolve new Group D sources."""
        config = ParallelAutoGrabberConfig(
            sources=["alpine", "debian"],
            max_per_cycle=4,
            max_workers=2,
        )
        grabber = IndustrialAutoGrabber(config)
        assert isinstance(grabber, IndustrialAutoGrabber)
        assert list(grabber.config.sources) == ["alpine", "debian"]

    def test_config_validation_max_workers_positive(self):
        """Test config validation rejects non-positive max_workers."""
        with pytest.raises(ValueError, match="max_workers must be greater than zero"):
            ParallelAutoGrabberConfig(
                sources=["nvd"],
                max_per_cycle=10,
                max_workers=0
            )

    def test_config_validation_max_workers_negative(self):
        """Test config validation rejects negative max_workers."""
        with pytest.raises(ValueError, match="max_workers must be greater than zero"):
            ParallelAutoGrabberConfig(
                sources=["nvd"],
                max_per_cycle=10,
                max_workers=-1
            )


class TestParallelGrabberIntegration:
    """Integration tests for parallel grabber components."""

    def test_field_router_and_parallel_grabber_consistency(self):
        """Test FieldRouter and ParallelAutoGrabber routing consistency."""
        config = ParallelAutoGrabberConfig(sources=["nvd"], max_per_cycle=1)
        grabber = ParallelAutoGrabber(config)
        
        sample_dict = {"description": "SQL injection vulnerability"}
        
        # Both should route to same expert
        field_router_expert = FieldRouter.route(sample_dict)
        grabber_route = grabber.route_sample_to_expert(sample_dict)
        
        # FieldRouter returns int, grabber returns ExpertRoute
        assert field_router_expert == 1
        assert grabber_route.expert_id == 1

    def test_expert_distribution(self):
        """Test expert routing distributes across multiple experts."""
        samples = [
            {"description": "SQL injection"},
            {"description": "XSS vulnerability"},
            {"description": "Remote code execution"},
            {"description": "Authentication bypass"},
            {"description": "SSRF vulnerability"},
        ]
        
        experts = [FieldRouter.route(s) for s in samples]
        unique_experts = set(experts)
        
        # Should route to at least 3 different experts
        assert len(unique_experts) >= 3, \
            f"Expected diverse routing, got experts: {experts}"
