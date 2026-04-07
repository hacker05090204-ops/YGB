"""OSV scraper using the public index plus unauthenticated OSV API detail retrieval."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from backend.ingestion.models import normalize_severity
from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample

logger = logging.getLogger("ygb.ingestion.scrapers.osv")


class OSVScraper(BaseScraper):
    """Scrape recent OSV advisories using the public index and OSV detail API."""

    SOURCE = "osv"
    REQUEST_DELAY_SECONDS = 1.0
    INDEX_URL = "https://osv-vulnerabilities.storage.googleapis.com/index.json"
    API_URL_TEMPLATE = "https://api.osv.dev/v1/vulns/{vuln_id}"

    @staticmethod
    def _extract_recent_ids(payload: Any, *, max_items: int) -> list[str]:
        raw_entries: Any = payload
        if isinstance(payload, dict):
            raw_entries = (
                payload.get("items")
                or payload.get("entries")
                or payload.get("vulns")
                or payload.get("index")
                or []
            )
        if not isinstance(raw_entries, list):
            raise ValueError("osv: index payload missing list entries")
        ranked_entries: list[tuple[str, str]] = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            vulnerability_id = str(entry.get("id", "")).strip()
            if not vulnerability_id:
                path_value = str(entry.get("path", "")).strip()
                if path_value:
                    vulnerability_id = Path(path_value).stem
            if not vulnerability_id:
                continue
            modified = str(
                entry.get("modified")
                or entry.get("last_modified")
                or entry.get("updated")
                or ""
            ).strip()
            ranked_entries.append((vulnerability_id, modified))
        ranked_entries.sort(key=lambda item: item[1], reverse=True)
        return [item[0] for item in ranked_entries[:max_items]]

    @staticmethod
    def _extract_cve_id(payload: dict[str, Any]) -> str:
        aliases = payload.get("aliases", [])
        if not isinstance(aliases, list):
            return ""
        for alias in aliases:
            alias_text = str(alias).strip()
            if alias_text.upper().startswith("CVE-"):
                return alias_text
        return ""

    @staticmethod
    def _extract_tags(payload: dict[str, Any]) -> tuple[str, ...]:
        tags: list[str] = []
        affected = payload.get("affected", [])
        if not isinstance(affected, list):
            return ()
        for item in affected:
            if not isinstance(item, dict):
                continue
            package = item.get("package", {})
            if not isinstance(package, dict):
                continue
            ecosystem = str(package.get("ecosystem", "")).strip()
            if ecosystem and ecosystem not in tags:
                tags.append(ecosystem)
        return tuple(tags)

    @staticmethod
    def _extract_references(payload: dict[str, Any]) -> tuple[str, ...]:
        references = payload.get("references", [])
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

    @classmethod
    def _extract_cvss_score(cls, payload: Any) -> float | None:
        scores: list[float] = []

        def _visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_text = str(key).lower()
                    if key_text in {"score", "basescore", "cvss_score"}:
                        score = cls._coerce_score(value)
                        if score is not None:
                            scores.append(score)
                    _visit(value)
            elif isinstance(node, list):
                for item in node:
                    _visit(item)

        _visit(payload)
        return max(scores) if scores else None

    @classmethod
    def _extract_severity(cls, payload: dict[str, Any]) -> str:
        explicit_candidates = [
            payload.get("database_specific", {}).get("severity") if isinstance(payload.get("database_specific"), dict) else None,
            payload.get("ecosystem_specific", {}).get("severity") if isinstance(payload.get("ecosystem_specific"), dict) else None,
        ]
        affected = payload.get("affected", [])
        if isinstance(affected, list):
            for item in affected:
                if not isinstance(item, dict):
                    continue
                ecosystem_specific = item.get("ecosystem_specific", {})
                if isinstance(ecosystem_specific, dict):
                    explicit_candidates.append(ecosystem_specific.get("severity"))
                database_specific = item.get("database_specific", {})
                if isinstance(database_specific, dict):
                    explicit_candidates.append(database_specific.get("severity"))
        for candidate in explicit_candidates:
            severity = normalize_severity(str(candidate or "UNKNOWN"))
            if severity != "UNKNOWN":
                return severity
        score = cls._extract_cvss_score(payload)
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

    def parse_vulnerability(self, payload: dict[str, Any]) -> ScrapedSample | None:
        vulnerability_payload = self._ensure_json_object(payload, source=self.SOURCE)
        advisory_id = str(vulnerability_payload.get("id", "")).strip()
        summary = str(vulnerability_payload.get("summary", "")).strip()
        details = str(vulnerability_payload.get("details", "")).strip()
        description = " ".join(part for part in (summary, details) if part).strip()
        if not advisory_id or not description:
            logger.debug(
                "osv_entry_skipped reason=missing_required_fields advisory_id=%s",
                advisory_id,
            )
            return None
        aliases = tuple(
            str(alias).strip()
            for alias in vulnerability_payload.get("aliases", [])
            if str(alias or "").strip()
        ) if isinstance(vulnerability_payload.get("aliases", []), list) else ()
        return ScrapedSample(
            source=self.SOURCE,
            advisory_id=advisory_id,
            url=f"https://osv.dev/vulnerability/{advisory_id}",
            title=summary or advisory_id,
            description=description,
            severity=self._extract_severity(vulnerability_payload),
            cve_id=self._extract_cve_id(vulnerability_payload),
            cvss_score=self._extract_cvss_score(vulnerability_payload),
            tags=self._extract_tags(vulnerability_payload),
            aliases=aliases,
            references=self._extract_references(vulnerability_payload),
            published_at=str(vulnerability_payload.get("published", "") or "") or None,
            modified_at=str(vulnerability_payload.get("modified", "") or "") or None,
        )

    def fetch(self, max_items: int) -> list[ScrapedSample]:
        if max_items <= 0:
            return []
        index_payload = self._get_json(self.INDEX_URL)
        vulnerability_ids = self._extract_recent_ids(index_payload, max_items=max_items)
        samples: list[ScrapedSample] = []
        for vulnerability_id in vulnerability_ids:
            if len(samples) >= max_items:
                break
            try:
                payload = self._get_json(self.API_URL_TEMPLATE.format(vuln_id=quote(vulnerability_id, safe="")))
                sample = self.parse_vulnerability(payload)
                if sample is not None:
                    samples.append(sample)
            except (requests.RequestException, ValueError) as exc:
                logger.error(
                    "osv_vulnerability_fetch_failed advisory_id=%s error=%s",
                    vulnerability_id,
                    exc,
                )
        return samples
