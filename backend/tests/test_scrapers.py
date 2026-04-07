from __future__ import annotations

import json
from pathlib import Path

import pytest

import backend.ingestion.scrapers.base_scraper as base_scraper_module
from backend.ingestion.scrapers import CISAScraper, GitHubAdvisoryScraper, NVDScraper, OSVScraper


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ingestion"


def _load_fixture(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


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


@pytest.mark.parametrize(
    "scraper_cls",
    [NVDScraper, CISAScraper, OSVScraper, GitHubAdvisoryScraper],
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
