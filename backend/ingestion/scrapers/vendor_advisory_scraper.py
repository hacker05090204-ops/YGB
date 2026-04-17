"""Compatibility wrapper for vendor advisory scraping, currently backed by Red Hat public advisory feeds."""

from backend.ingestion.scrapers.redhat_scraper import RedHatAdvisoryScraper

VendorAdvisoryScraper = RedHatAdvisoryScraper

__all__ = ["RedHatAdvisoryScraper", "VendorAdvisoryScraper"]
