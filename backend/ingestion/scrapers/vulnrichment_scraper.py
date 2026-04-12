"""Vulnrichment scraper backed by the public CIRCL CVE API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample


class VulnrichmentScraper(BaseScraper):
    """Scrape recent Vulnrichment-enriched CVE records."""

    SOURCE = "vulnrichment"
    REQUEST_DELAY_SECONDS = 1.0
    FEED_URL = "https://cve.circl.lu/api/db/list/vulnrichment/last"
    DETAIL_URL_TEMPLATE = "https://cve.circl.lu/api/cve/{cve_id}"

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

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        feed_payload = self._get_json(self.FEED_URL)
        samples: list[ScrapedSample] = []
        for entry in self._extract_feed_entries(feed_payload, max_items=max(max_items * 2, 10)):
            if len(samples) >= max_items:
                break
            try:
                if isinstance(entry, dict) and ("containers" in entry or "cveMetadata" in entry):
                    sample = self.parse_record(entry)
                else:
                    cve_id = self._extract_cve_id(entry)
                    if not cve_id:
                        self._log_partial_failure(reason="missing_cve_id")
                        continue
                    detail_payload = self._get_json(
                        self.DETAIL_URL_TEMPLATE.format(cve_id=quote(cve_id, safe=""))
                    )
                    sample = self.parse_record(detail_payload)
                if sample is not None:
                    samples.append(sample)
            except Exception as exc:
                self._log_partial_failure(
                    reason="record_fetch_failed",
                    cve_id=self._extract_cve_id(entry) or "<missing-cve-id>",
                    error_type=type(exc).__name__,
                )
        return samples[:max_items]
