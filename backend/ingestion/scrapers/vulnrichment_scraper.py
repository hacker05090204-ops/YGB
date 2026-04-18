"""Vulnrichment scraper backed by the public GitHub contents API with a legacy fallback."""

from __future__ import annotations

import base64
import json
from typing import Any

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample


class VulnrichmentScraper(BaseScraper):
    """Scrape recent Vulnrichment-enriched CVE records."""

    SOURCE = "vulnrichment"
    REQUEST_DELAY_SECONDS = 1.0
    FEED_URL = "https://api.github.com/repos/cisagov/vulnrichment/contents"
    LEGACY_FEED_URL = "https://cve.circl.lu/api/db/list/vulnrichment/last"
    LEGACY_DETAIL_URL_TEMPLATE = "https://cve.circl.lu/api/cve/{cve_id}"
    MAX_CONTENT_LISTINGS = 12
    MAX_FILE_CANDIDATES = 64

    @staticmethod
    def _first_english_text(values: Any) -> str:
        if not isinstance(values, list):
            return ""
        for entry in values:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("lang", "")).strip().lower() == "en":
                text = str(entry.get("value") or entry.get("description") or "").strip()
                if text:
                    return text
        for entry in values:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("value") or entry.get("description") or "").strip()
            if text:
                return text
        return ""

    @classmethod
    def _extract_cvss_score(cls, payload: Any) -> float | None:
        scores: list[float] = []

        def _visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_text = str(key).lower()
                    if key_text in {"basescore", "score", "cvss3_base_score", "cvss_score"}:
                        score = cls._coerce_score(value)
                        if score is not None:
                            scores.append(score)
                    _visit(value)
            elif isinstance(node, list):
                for item in node:
                    _visit(item)

        _visit(payload)
        return max(scores) if scores else None

    def _extract_feed_entries(self, payload: Any, *, max_items: int) -> list[Any]:
        raw_entries: Any = payload
        if isinstance(payload, dict):
            if "containers" in payload or "cveMetadata" in payload:
                raw_entries = [payload]
            else:
                raw_entries = payload.get("data") or payload.get("items") or payload.get("cves") or payload.get("vulnerabilities") or []
        if not isinstance(raw_entries, list):
            raise ValueError("vulnrichment: feed payload missing list entries")
        return list(raw_entries[:max_items])

    @staticmethod
    def _extract_cve_id(entry: Any) -> str:
        if isinstance(entry, str):
            return entry.strip().upper()
        if not isinstance(entry, dict):
            return ""
        cve_metadata = entry.get("cveMetadata", {})
        if isinstance(cve_metadata, dict):
            cve_id = str(cve_metadata.get("cveId", "")).strip()
            if cve_id:
                return cve_id
        return str(entry.get("cve") or entry.get("id") or entry.get("name") or "").strip()

    @staticmethod
    def _extract_vulnrichment_container(adp_entries: Any) -> dict[str, Any] | None:
        if not isinstance(adp_entries, list):
            return None
        first_entry: dict[str, Any] | None = None
        for entry in adp_entries:
            if not isinstance(entry, dict):
                continue
            if first_entry is None:
                first_entry = entry
            provider_metadata = entry.get("providerMetadata", {})
            short_name = ""
            if isinstance(provider_metadata, dict):
                short_name = str(provider_metadata.get("shortName", "")).strip().lower()
            title = str(entry.get("title", "")).strip().lower()
            if short_name == "vulnrichment" or "vulnrichment" in title:
                return entry
        return first_entry

    def parse_feed(self, payload: Any, *, max_items: int) -> list[ScrapedSample]:
        samples: list[ScrapedSample] = []
        for entry in self._extract_feed_entries(payload, max_items=max(max_items * 2, 10)):
            if len(samples) >= max_items:
                break
            sample = self.parse_record(entry)
            if sample is not None:
                samples.append(sample)
        return samples[:max_items]

    def parse_record(self, payload: Any) -> ScrapedSample | None:
        raw_payload = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
        if isinstance(raw_payload, dict) and str(raw_payload.get("encoding", "")).strip().lower() == "base64":
            try:
                content_bytes = base64.b64decode(str(raw_payload.get("content") or ""))
                raw_payload = json.loads(content_bytes.decode("utf-8"))
            except (ValueError, TypeError, json.JSONDecodeError):
                self._log_partial_failure(reason="invalid_github_file_payload")
                return None
        record_payload = self._ensure_json_object(raw_payload, source=self.SOURCE)
        cve_id = self._extract_cve_id(record_payload)
        containers = record_payload.get("containers", {})
        if not isinstance(containers, dict):
            self._log_partial_failure(reason="missing_containers", cve_id=cve_id or "<missing-cve-id>")
            return None
        cna_container = containers.get("cna", {}) if isinstance(containers.get("cna"), dict) else {}
        vulnrichment_container = self._extract_vulnrichment_container(containers.get("adp"))
        if vulnrichment_container is None:
            self._log_partial_failure(reason="missing_vulnrichment_container", cve_id=cve_id or "<missing-cve-id>")
            return None

        title = str(cna_container.get("title") or vulnrichment_container.get("title") or cve_id).strip()
        description = " ".join(
            part
            for part in (
                self._first_english_text(vulnrichment_container.get("descriptions")),
                self._first_english_text(cna_container.get("descriptions")),
            )
            if part
        ).strip()
        if not cve_id or not description:
            self._log_partial_failure(
                reason="missing_required_fields",
                cve_id=cve_id or "<missing-cve-id>",
            )
            return None

        cvss_score = self._extract_cvss_score(vulnrichment_container.get("metrics") or cna_container.get("metrics"))
        severity = self._normalize_source_severity(vulnrichment_container.get("baseSeverity"))
        if severity == "UNKNOWN":
            severity = self._severity_from_score(cvss_score)

        tags: list[str] = []
        problem_types = vulnrichment_container.get("problemTypes", [])
        if isinstance(problem_types, list):
            for problem_type in problem_types:
                if not isinstance(problem_type, dict):
                    continue
                descriptions = problem_type.get("descriptions", [])
                if not isinstance(descriptions, list):
                    continue
                for description_entry in descriptions:
                    if not isinstance(description_entry, dict):
                        continue
                    tag = str(description_entry.get("description", "")).strip()
                    if tag and tag not in tags:
                        tags.append(tag)

        references: list[str] = []
        for container in (vulnrichment_container, cna_container):
            references_payload = container.get("references", []) if isinstance(container, dict) else []
            if not isinstance(references_payload, list):
                continue
            for reference in references_payload:
                if not isinstance(reference, dict):
                    continue
                url = str(reference.get("url", "")).strip()
                if url and url not in references:
                    references.append(url)
        if not references:
            references.append(f"https://www.cve.org/CVERecord?id={cve_id}")

        vendor = ""
        product = ""
        affected = cna_container.get("affected", []) if isinstance(cna_container, dict) else []
        if isinstance(affected, list):
            for entry in affected:
                if not isinstance(entry, dict):
                    continue
                vendor = str(entry.get("vendor", "")).strip()
                product = str(entry.get("product", "")).strip()
                if vendor or product:
                    break

        cve_metadata = record_payload.get("cveMetadata", {}) if isinstance(record_payload.get("cveMetadata"), dict) else {}
        provider_metadata = (
            vulnrichment_container.get("providerMetadata", {})
            if isinstance(vulnrichment_container.get("providerMetadata"), dict)
            else {}
        )

        return ScrapedSample(
            source=self.SOURCE,
            advisory_id=cve_id,
            url=references[0],
            title=title or cve_id,
            description=description,
            severity=severity,
            cve_id=cve_id,
            cvss_score=cvss_score,
            tags=tuple(tags),
            references=tuple(references),
            published_at=str(cve_metadata.get("datePublished", "") or "") or None,
            modified_at=str(provider_metadata.get("dateUpdated") or cve_metadata.get("dateUpdated") or "") or None,
            vendor=vendor,
            product=product,
        )

    @staticmethod
    def _sort_contents_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            entries,
            key=lambda item: (
                str(item.get("type") or "") != "dir",
                str(item.get("name") or ""),
            ),
            reverse=True,
        )

    def _list_contents(self, url: str) -> list[dict[str, Any]]:
        payload = self._get_json(url)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        raise ValueError("vulnrichment: invalid GitHub contents payload")

    def _load_github_record(self, entry: dict[str, Any]) -> Any:
        download_url = str(entry.get("download_url") or "").strip()
        if download_url:
            return self._get_json(download_url)
        entry_url = str(entry.get("url") or "").strip()
        if entry_url:
            return self._get_json(entry_url)
        raise ValueError("vulnrichment: contents entry missing url")

    def _fetch_from_github_contents(self, max_items: int) -> list[ScrapedSample]:
        pending_urls = [self.FEED_URL]
        listing_requests = 0
        file_entries: list[dict[str, Any]] = []
        while pending_urls and listing_requests < self.MAX_CONTENT_LISTINGS and len(file_entries) < self.MAX_FILE_CANDIDATES:
            listing_url = pending_urls.pop(0)
            listing_requests += 1
            entries = self._sort_contents_entries(self._list_contents(listing_url))
            for entry in entries:
                entry_type = str(entry.get("type") or "").strip().lower()
                if entry_type == "dir":
                    next_url = str(entry.get("url") or "").strip()
                    if next_url:
                        pending_urls.append(next_url)
                    continue
                if entry_type == "file" and str(entry.get("name") or "").strip().lower().endswith(".json"):
                    file_entries.append(entry)
                    if len(file_entries) >= self.MAX_FILE_CANDIDATES:
                        break

        samples: list[ScrapedSample] = []
        for entry in file_entries:
            if len(samples) >= max_items:
                break
            try:
                sample = self.parse_record(self._load_github_record(entry))
                if sample is not None:
                    samples.append(sample)
            except Exception as exc:
                self._log_partial_failure(
                    reason="github_record_fetch_failed",
                    path=str(entry.get("path") or entry.get("name") or "<unknown-path>"),
                    error_type=type(exc).__name__,
                )
        return samples[:max_items]

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        try:
            github_samples = self._fetch_from_github_contents(max_items)
            if github_samples:
                return github_samples[:max_items]
        except Exception as exc:
            self._log_partial_failure(
                reason="github_contents_fetch_failed",
                error_type=type(exc).__name__,
            )

        feed_payload = self._get_json(self.LEGACY_FEED_URL)
        samples: list[ScrapedSample] = []
        for entry in self._extract_feed_entries(feed_payload, max_items=max(max_items * 2, 10)):
            if len(samples) >= max_items:
                break
            try:
                sample = self.parse_record(entry)
                if sample is not None:
                    samples.append(sample)
            except Exception as exc:
                self._log_partial_failure(
                    reason="legacy_record_fetch_failed",
                    cve_id=self._extract_cve_id(entry) or "<missing-cve-id>",
                    error_type=type(exc).__name__,
                )
        return samples[:max_items]
