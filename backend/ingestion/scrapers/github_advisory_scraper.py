"""Public GitHub advisory scraper using the unauthenticated advisory API."""

from __future__ import annotations

import logging
from typing import Any

from backend.ingestion.models import normalize_severity
from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample

logger = logging.getLogger("ygb.ingestion.scrapers.github")


class GitHubAdvisoryScraper(BaseScraper):
    """Scrape public GitHub security advisories from the REST API."""

    SOURCE = "github"
    REQUEST_DELAY_SECONDS = 2.0
    API_URL = "https://api.github.com/advisories"

    @staticmethod
    def _extract_next_link(link_header: str) -> str | None:
        for part in str(link_header or "").split(","):
            if 'rel="next"' not in part:
                continue
            return part.split(";", 1)[0].strip().strip("<>")
        return None

    @staticmethod
    def _extract_cve_id(advisory: dict[str, Any]) -> str:
        direct_cve = str(advisory.get("cve_id", "")).strip()
        if direct_cve:
            return direct_cve
        identifiers = advisory.get("identifiers", [])
        if not isinstance(identifiers, list):
            return ""
        for identifier in identifiers:
            if not isinstance(identifier, dict):
                continue
            value = str(identifier.get("value", "")).strip()
            if value.upper().startswith("CVE-"):
                return value
        return ""

    @staticmethod
    def _extract_aliases(advisory: dict[str, Any]) -> tuple[str, ...]:
        identifiers = advisory.get("identifiers", [])
        if not isinstance(identifiers, list):
            return ()
        aliases: list[str] = []
        for identifier in identifiers:
            if not isinstance(identifier, dict):
                continue
            value = str(identifier.get("value", "")).strip()
            if value and value not in aliases:
                aliases.append(value)
        return tuple(aliases)

    @staticmethod
    def _extract_tags(advisory: dict[str, Any]) -> tuple[str, ...]:
        tags: list[str] = []
        cwes = advisory.get("cwes", [])
        if isinstance(cwes, list):
            for cwe in cwes:
                if not isinstance(cwe, dict):
                    continue
                cwe_id = str(cwe.get("cwe_id", "")).strip()
                if cwe_id and cwe_id not in tags:
                    tags.append(cwe_id)
        vulnerabilities = advisory.get("vulnerabilities", [])
        if isinstance(vulnerabilities, list):
            for vulnerability in vulnerabilities:
                if not isinstance(vulnerability, dict):
                    continue
                package = vulnerability.get("package", {})
                if not isinstance(package, dict):
                    continue
                ecosystem = str(package.get("ecosystem", "")).strip()
                if ecosystem and ecosystem not in tags:
                    tags.append(ecosystem)
        return tuple(tags)

    def parse_page(self, payload: Any, *, max_items: int) -> list[ScrapedSample]:
        advisories = self._ensure_json_array(payload, source=self.SOURCE)
        samples: list[ScrapedSample] = []
        for advisory in advisories:
            if len(samples) >= max_items:
                break
            if not isinstance(advisory, dict):
                logger.warning("github_advisory_skipped reason=not_object")
                continue
            advisory_id = str(advisory.get("ghsa_id", "")).strip() or str(advisory.get("id", "")).strip()
            summary = str(advisory.get("summary", "")).strip()
            description = str(advisory.get("description", "")).strip()
            combined_description = " ".join(part for part in (summary, description) if part).strip()
            if not advisory_id or not combined_description:
                logger.debug(
                    "github_advisory_skipped reason=missing_required_fields advisory_id=%s",
                    advisory_id,
                )
                continue
            samples.append(
                ScrapedSample(
                    source=self.SOURCE,
                    advisory_id=advisory_id,
                    url=str(advisory.get("html_url", "")).strip(),
                    title=summary or advisory_id,
                    description=combined_description,
                    severity=normalize_severity(str(advisory.get("severity", "UNKNOWN"))),
                    cve_id=self._extract_cve_id(advisory),
                    tags=self._extract_tags(advisory),
                    aliases=self._extract_aliases(advisory),
                    published_at=str(advisory.get("published_at", "") or "") or None,
                    modified_at=str(advisory.get("updated_at", "") or "") or None,
                )
            )
        return samples

    def fetch(self, max_items: int) -> list[ScrapedSample]:
        if max_items <= 0:
            return []
        headers = {"Accept": "application/vnd.github+json"}
        next_url: str | None = self.API_URL
        first_page = True
        samples: list[ScrapedSample] = []
        while next_url and len(samples) < max_items:
            params = None
            if first_page:
                params = {"per_page": min(max_items, 100), "type": "reviewed"}
            payload = self._get_json(next_url, headers=headers, params=params)
            samples.extend(self.parse_page(payload, max_items=max_items - len(samples)))
            next_url = self._extract_next_link(self._last_response_headers.get("Link", ""))
            first_page = False
        return samples[:max_items]
