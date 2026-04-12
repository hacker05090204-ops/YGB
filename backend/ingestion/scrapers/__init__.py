"""Synchronous public-source scrapers used by the autograbber."""

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample
from backend.ingestion.scrapers.cisa_scraper import CISAScraper
from backend.ingestion.scrapers.exploitdb_scraper import ExploitDBScraper
from backend.ingestion.scrapers.github_advisory_scraper import GitHubAdvisoryScraper
from backend.ingestion.scrapers.msrc_scraper import MSRCScraper
from backend.ingestion.scrapers.nvd_scraper import NVDScraper
from backend.ingestion.scrapers.osv_scraper import OSVScraper
from backend.ingestion.scrapers.redhat_scraper import RedHatAdvisoryScraper
from backend.ingestion.scrapers.snyk_scraper import SnykScraper
from backend.ingestion.scrapers.vulnrichment_scraper import VulnrichmentScraper

__all__ = [
    "BaseScraper",
    "CISAScraper",
    "ExploitDBScraper",
    "GitHubAdvisoryScraper",
    "MSRCScraper",
    "NVDScraper",
    "OSVScraper",
    "RedHatAdvisoryScraper",
    "ScrapedSample",
    "SnykScraper",
    "VulnrichmentScraper",
]
