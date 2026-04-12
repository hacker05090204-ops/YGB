from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

import backend.ingestion.scrapers.base_scraper as base_scraper_module
from backend.ingestion.scrapers import (
    CISAScraper,
    ExploitDBScraper,
    GitHubAdvisoryScraper,
    MSRCScraper,
    NVDScraper,
    OSVScraper,
    RedHatAdvisoryScraper,
    SnykScraper,
    VulnrichmentScraper,
)
from backend.ingestion.scrapers.base_scraper import BaseScraper


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ingestion"


def _load_fixture(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def test_nvd_scraper_parses_known_recent_feed_fixture():
    scraper = NVDScraper()
    try:
        samples = scraper.parse_feed(_load_fixture("nvd_recent.json"), max_items=10)
    finally:
        scraper.close()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.cve_id == "CVE-2026-0001"
    assert sample.severity == "CRITICAL"
    assert sample.cvss_score == pytest.approx(9.8)
    assert sample.tags == ("CWE-79",)
    assert sample.url.endswith("/CVE-2026-0001")


def test_cisa_scraper_parses_known_kev_fixture():
    scraper = CISAScraper()
    try:
        samples = scraper.parse_feed(_load_fixture("cisa_kev.json"), max_items=10)
    finally:
        scraper.close()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.cve_id == "CVE-2026-1001"
    assert sample.is_exploited is True
    assert sample.severity == "CRITICAL"
    assert sample.tags == ("kev", "exploited_in_wild", "ransomware")
    assert sample.vendor == "Acme Security"


def test_osv_scraper_parses_known_fixture():
    scraper = OSVScraper()
    try:
        recent_ids = scraper._extract_recent_ids(_load_fixture("osv_index.json"), max_items=1)
        sample = scraper.parse_vulnerability(_load_fixture("osv_vuln.json"))
    finally:
        scraper.close()
    assert recent_ids == ["GHSA-9wx4-h78v-vm56"]
    assert sample is not None
    assert sample.cve_id == "CVE-2026-2001"
    assert sample.severity == "HIGH"
    assert sample.tags == ("PyPI",)
    assert sample.references == ("https://github.com/advisories/GHSA-9wx4-h78v-vm56",)


def test_github_advisory_scraper_parses_known_fixture():
    scraper = GitHubAdvisoryScraper()
    try:
        samples = scraper.parse_page(_load_fixture("github_advisories.json"), max_items=10)
    finally:
        scraper.close()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.advisory_id == "GHSA-4h2x-9jgm-6wph"
    assert sample.cve_id == "CVE-2026-3001"
    assert sample.severity == "HIGH"
    assert sample.tags == ("CWE-89", "pip")


def test_exploitdb_scraper_parses_known_fixture():
    scraper = ExploitDBScraper()
    try:
        samples = scraper.parse_csv(_load_text_fixture("exploitdb_recent.csv"), max_items=10)
    finally:
        scraper.close()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.advisory_id == "51001"
    assert sample.cve_id == "CVE-2026-4101"
    assert sample.severity == "UNKNOWN"
    assert sample.is_exploited is True
    assert sample.url.endswith("/51001")


def test_msrc_scraper_parses_known_fixture():
    scraper = MSRCScraper()
    try:
        document_ids = scraper.extract_document_ids(_load_fixture("msrc_updates.json"), max_documents=1)
        samples = scraper.parse_document(_load_fixture("msrc_document.json"), max_items=10)
    finally:
        scraper.close()
    assert document_ids == ["2026-Mar"]
    assert len(samples) == 1
    sample = samples[0]
    assert sample.cve_id == "CVE-2026-4201"
    assert sample.severity == "CRITICAL"
    assert sample.cvss_score == pytest.approx(9.8)
    assert sample.vendor == "Microsoft"


def test_redhat_scraper_parses_known_fixture():
    scraper = RedHatAdvisoryScraper()
    try:
        cve_ids = scraper.extract_recent_ids(_load_fixture("redhat_cve_list.json"), max_items=1)
        sample = scraper.parse_detail(_load_fixture("redhat_cve_detail.json"))
    finally:
        scraper.close()
    assert cve_ids == ["CVE-2026-4301"]
    assert sample is not None
    assert sample.cve_id == "CVE-2026-4301"
    assert sample.severity == "HIGH"
    assert sample.cvss_score == pytest.approx(8.1)
    assert sample.vendor == "Red Hat"


def test_snyk_scraper_parses_known_fixture():
    scraper = SnykScraper()
    try:
        advisory_ids = scraper.extract_advisory_ids(_load_text_fixture("snyk_listing.html"), max_items=1)
        sample = scraper.parse_detail_html(
            "SNYK-JS-LODASH-567746",
            _load_text_fixture("snyk_detail.html"),
            ecosystem="npm",
        )
    finally:
        scraper.close()
    assert advisory_ids == ["SNYK-JS-LODASH-567746"]
    assert sample is not None
    assert sample.cve_id == "CVE-2026-4501"
    assert sample.severity == "HIGH"
    assert sample.tags == ("CWE-79", "npm")
    assert sample.product == "lodash"


def test_vulnrichment_scraper_parses_known_fixture():
    scraper = VulnrichmentScraper()
    try:
        samples = scraper.parse_feed(_load_fixture("vulnrichment_list.json"), max_items=10)
    finally:
        scraper.close()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.cve_id == "CVE-2026-4401"
    assert sample.severity == "HIGH"
    assert sample.cvss_score == pytest.approx(8.8)
    assert sample.tags == ("CWE-94",)


class _ErrorScraper(BaseScraper):
    SOURCE = "error"

    def _fetch_impl(self, max_items: int):
        raise RuntimeError("boom")


def test_base_scraper_returns_empty_list_on_error_and_logs(caplog):
    scraper = _ErrorScraper()
    try:
        with caplog.at_level("INFO"):
            samples = scraper.fetch(5)
    finally:
        scraper.close()
    assert samples == []
    assert "scraper_fetch_failed source=error" in caplog.text
    assert "scraper_empty_result source=error reason=fetch_failed" in caplog.text


@pytest.mark.parametrize(
    "scraper_cls",
    [
        NVDScraper,
        CISAScraper,
        OSVScraper,
        GitHubAdvisoryScraper,
        ExploitDBScraper,
        MSRCScraper,
        RedHatAdvisoryScraper,
        SnykScraper,
        VulnrichmentScraper,
    ],
)
def test_each_scraper_returns_empty_list_on_network_error(monkeypatch, scraper_cls, caplog):
    scraper = scraper_cls()

    def _raise_request_exception(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr(scraper, "_request", _raise_request_exception)
    try:
        with caplog.at_level("INFO"):
            samples = scraper.fetch(5)
    finally:
        scraper.close()

    assert samples == []
    assert f"source={scraper.SOURCE}" in caplog.text
    assert f"scraper_empty_result source={scraper.SOURCE}" in caplog.text


@pytest.mark.parametrize(
    "scraper_cls",
    [
        NVDScraper,
        CISAScraper,
        OSVScraper,
        GitHubAdvisoryScraper,
        ExploitDBScraper,
        MSRCScraper,
        RedHatAdvisoryScraper,
        SnykScraper,
        VulnrichmentScraper,
    ],
)
def test_scrapers_use_consistent_non_commercial_research_user_agent(scraper_cls):
    scraper = scraper_cls()
    try:
        assert scraper.session.headers["User-Agent"] == base_scraper_module.REAL_USER_AGENT
        assert "non-commercial research" in scraper.session.headers["User-Agent"].lower()
    finally:
        scraper.close()


@pytest.mark.parametrize(
    "scraper_cls",
    [
        NVDScraper,
        CISAScraper,
        OSVScraper,
        GitHubAdvisoryScraper,
        ExploitDBScraper,
        MSRCScraper,
        RedHatAdvisoryScraper,
        SnykScraper,
        VulnrichmentScraper,
    ],
)
def test_scrapers_enforce_polite_delay(monkeypatch, scraper_cls):
    sleep_calls: list[float] = []
    monkeypatch.setattr(base_scraper_module.time, "monotonic", lambda: 100.25)
    monkeypatch.setattr(base_scraper_module.time, "sleep", sleep_calls.append)
    scraper = scraper_cls()
    try:
        assert scraper.REQUEST_DELAY_SECONDS >= 1.0
        scraper._last_request_monotonic = 100.0
        scraper._respect_polite_delay()
    finally:
        scraper.close()
    assert sleep_calls, "expected polite delay sleep to be enforced"
    assert sleep_calls[0] == pytest.approx(scraper.REQUEST_DELAY_SECONDS - 0.25, abs=1e-6)
