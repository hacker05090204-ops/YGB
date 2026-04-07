"""CISA KEV scraper backed by the public JSON feed."""

from __future__ import annotations

import logging
from typing import Any

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample

logger = logging.getLogger("ygb.ingestion.scrapers.cisa")


class CISAScraper(BaseScraper):
    """Scrape the public CISA Known Exploited Vulnerabilities feed."""

    SOURCE = "cisa"
    REQUEST_DELAY_SECONDS = 1.0
    FEED_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"

    @staticmethod
    def _extract_tags(entry: dict[str, Any]) -> tuple[str, ...]:
        tags = ["kev", "exploited_in_wild"]
        ransomware_text = str(entry.get("knownRansomwareCampaignUse", "")).strip().lower()
        if ransomware_text == "known":
            tags.append("ransomware")
        return tuple(tags)

    def parse_feed(self, payload: dict[str, Any], *, max_items: int) -> list[ScrapedSample]:
        feed_payload = self._ensure_json_object(payload, source=self.SOURCE)
        vulnerabilities = feed_payload.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            raise ValueError("cisa: feed payload missing vulnerabilities list")
        samples: list[ScrapedSample] = []
        for entry in vulnerabilities:
            if len(samples) >= max_items:
                break
            if not isinstance(entry, dict):
                logger.warning("cisa_entry_skipped reason=not_object")
                continue
            cve_id = str(entry.get("cveID", "")).strip()
            short_description = str(entry.get("shortDescription", "")).strip()
            if not cve_id or not short_description:
                logger.debug(
                    "cisa_entry_skipped reason=missing_required_fields cve_id=%s",
                    cve_id,
                )
                continue
            required_action = str(entry.get("requiredAction", "")).strip()
            vulnerability_name = str(entry.get("vulnerabilityName", "")).strip() or cve_id
            description = " ".join(
                part
                for part in (short_description, required_action)
                if part
            )
            samples.append(
                ScrapedSample(
                    source=self.SOURCE,
                    advisory_id=cve_id,
                    url=self.CATALOG_URL,
                    title=vulnerability_name,
                    description=description,
                    severity="CRITICAL",
                    cve_id=cve_id,
                    tags=self._extract_tags(entry),
                    published_at=str(entry.get("dateAdded", "") or "") or None,
                    modified_at=str(feed_payload.get("dateReleased", "") or "") or None,
                    is_exploited=True,
                    vendor=str(entry.get("vendorProject", "") or ""),
                    product=str(entry.get("product", "") or ""),
                )
            )
        return samples

    def fetch(self, max_items: int) -> list[ScrapedSample]:
        if max_items <= 0:
            return []
        payload = self._get_json(self.FEED_URL)
        return self.parse_feed(payload, max_items=max_items)
