"""Synchronous public-source scrapers used by the autograbber."""

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample
from backend.ingestion.scrapers.cisa_scraper import CISAScraper
from backend.ingestion.scrapers.github_advisory_scraper import GitHubAdvisoryScraper
from backend.ingestion.scrapers.nvd_scraper import NVDScraper
from backend.ingestion.scrapers.osv_scraper import OSVScraper

__all__ = [
    "BaseScraper",
    "CISAScraper",
    "GitHubAdvisoryScraper",
    "NVDScraper",
    "OSVScraper",
    "ScrapedSample",
]
