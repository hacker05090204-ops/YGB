"""Recent NVD feed scraper backed by the public recent feed archive."""

from __future__ import annotations

import gzip
import logging
from typing import Any

from backend.ingestion.models import normalize_severity
from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample

logger = logging.getLogger("ygb.ingestion.scrapers.nvd")


class NVDScraper(BaseScraper):
    """Scrape the public NVD recent feed."""

    SOURCE = "nvd"
    REQUEST_DELAY_SECONDS = 1.0
    RECENT_FEED_URL = "https://nvd.nist.gov/feeds/json/cves/2.0/nvdcve-2.0-recent.json.gz"

    @staticmethod
    def _extract_description(cve_payload: dict[str, Any]) -> str:
        descriptions = cve_payload.get("descriptions", [])
        if not isinstance(descriptions, list):
            return ""
        for entry in descriptions:
            if isinstance(entry, dict) and str(entry.get("lang", "")).lower() == "en":
                value = str(entry.get("value", "")).strip()
                if value:
                    return value
        for entry in descriptions:
            if isinstance(entry, dict):
                value = str(entry.get("value", "")).strip()
                if value:
                    return value
        return ""

    @staticmethod
    def _extract_cvss_score(cve_payload: dict[str, Any]) -> float | None:
        metrics = cve_payload.get("metrics", {})
        if not isinstance(metrics, dict):
            return None
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            entries = metrics.get(key, [])
            if not isinstance(entries, list) or not entries:
                continue
            first_entry = entries[0] if isinstance(entries[0], dict) else {}
            cvss_data = first_entry.get("cvssData", {}) if isinstance(first_entry, dict) else {}
            if isinstance(cvss_data, dict):
                score = BaseScraper._coerce_score(cvss_data.get("baseScore"))
                if score is not None:
                    return score
        return None

    @classmethod
    def _extract_severity(cls, cve_payload: dict[str, Any]) -> str:
        metrics = cve_payload.get("metrics", {})
        if isinstance(metrics, dict):
            for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                entries = metrics.get(key, [])
                if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
                    continue
                cvss_data = entries[0].get("cvssData", {})
                if isinstance(cvss_data, dict):
                    severity = normalize_severity(str(cvss_data.get("baseSeverity", "UNKNOWN")))
                    if severity != "UNKNOWN":
                        return severity
        score = cls._extract_cvss_score(cve_payload)
        if score is None:
            return "UNKNOWN"
        if score >= 9.0:
            return "CRITICAL"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MEDIUM"
        if score > 0.0:
            return "LOW"
        return "UNKNOWN"

    @staticmethod
    def _extract_tags(cve_payload: dict[str, Any]) -> tuple[str, ...]:
        tags: list[str] = []
        weaknesses = cve_payload.get("weaknesses", [])
        if not isinstance(weaknesses, list):
            return ()
        for weakness in weaknesses:
            if not isinstance(weakness, dict):
                continue
            descriptions = weakness.get("description", [])
            if not isinstance(descriptions, list):
                continue
            for description in descriptions:
                if not isinstance(description, dict):
                    continue
                value = str(description.get("value", "")).strip()
                if value and value not in tags:
                    tags.append(value)
        return tuple(tags)

    @staticmethod
    def _extract_references(cve_payload: dict[str, Any]) -> tuple[str, ...]:
        references = cve_payload.get("references", [])
        if not isinstance(references, list):
            return ()
        urls: list[str] = []
        for reference in references:
            if not isinstance(reference, dict):
                continue
            url = str(reference.get("url", "")).strip()
            if url and url not in urls:
                urls.append(url)
        return tuple(urls)

    def parse_feed(self, payload: dict[str, Any], *, max_items: int) -> list[ScrapedSample]:
        feed_payload = self._ensure_json_object(payload, source=self.SOURCE)
        vulnerabilities = feed_payload.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            raise ValueError("nvd: feed payload missing vulnerabilities list")
        samples: list[ScrapedSample] = []
        for entry in vulnerabilities:
            if len(samples) >= max_items:
                break
            if not isinstance(entry, dict):
                logger.warning("nvd_entry_skipped reason=not_object")
                continue
            cve_payload = entry.get("cve", {})
            if not isinstance(cve_payload, dict):
                logger.warning("nvd_entry_skipped reason=missing_cve_object")
                continue
            cve_id = str(cve_payload.get("id", "")).strip()
            description = self._extract_description(cve_payload)
            if not cve_id or not description:
                logger.debug(
                    "nvd_entry_skipped reason=missing_required_fields cve_id=%s",
                    cve_id,
                )
                continue
            samples.append(
                ScrapedSample(
                    source=self.SOURCE,
                    advisory_id=cve_id,
                    url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    title=cve_id,
                    description=description,
                    severity=self._extract_severity(cve_payload),
                    cve_id=cve_id,
                    cvss_score=self._extract_cvss_score(cve_payload),
                    tags=self._extract_tags(cve_payload),
                    references=self._extract_references(cve_payload),
                    published_at=str(cve_payload.get("published", "") or "") or None,
                    modified_at=str(cve_payload.get("lastModified", "") or "") or None,
                )
            )
        return samples

    def fetch(self, max_items: int) -> list[ScrapedSample]:
        if max_items <= 0:
            return []
        raw_bytes = self._get_bytes(self.RECENT_FEED_URL)
        try:
            decoded_bytes = gzip.decompress(raw_bytes)
        except OSError:
            decoded_bytes = raw_bytes
        payload = self._load_json_bytes(decoded_bytes, source=self.SOURCE)
        return self.parse_feed(payload, max_items=max_items)
