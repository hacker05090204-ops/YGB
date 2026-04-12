"""Microsoft MSRC scraper backed by the public CVRF API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample


class MSRCScraper(BaseScraper):
    """Scrape recent Microsoft advisories from the public MSRC CVRF API."""

    SOURCE = "msrc"
    REQUEST_DELAY_SECONDS = 1.0
    UPDATES_URL = "https://api.msrc.microsoft.com/cvrf/v3.0/updates"
    DOCUMENT_URL_TEMPLATE = "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/{document_id}"

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("Value", "value", "Title", "title", "Description", "description"):
                if key in value:
                    text = MSRCScraper._stringify(value.get(key))
                    if text:
                        return text
            for nested_value in value.values():
                text = MSRCScraper._stringify(nested_value)
                if text:
                    return text
        if isinstance(value, list):
            for item in value:
                text = MSRCScraper._stringify(item)
                if text:
                    return text
        return ""

    def extract_document_ids(self, payload: Any, *, max_documents: int) -> list[str]:
        raw_entries: Any = payload
        if isinstance(payload, dict):
            raw_entries = payload.get("value") or payload.get("updates") or payload.get("items") or []
        if not isinstance(raw_entries, list):
            raise ValueError("msrc: updates payload missing list entries")
        ranked_entries: list[tuple[str, str]] = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                self._log_partial_failure(reason="update_entry_not_object")
                continue
            document_id = str(entry.get("ID") or entry.get("id") or entry.get("Alias") or "").strip()
            if not document_id:
                self._log_partial_failure(reason="missing_document_id")
                continue
            released_at = str(
                entry.get("CurrentReleaseDate")
                or entry.get("InitialReleaseDate")
                or entry.get("currentReleaseDate")
                or entry.get("releaseDate")
                or ""
            ).strip()
            ranked_entries.append((document_id, released_at))
        ranked_entries.sort(key=lambda item: item[1], reverse=True)
        return [item[0] for item in ranked_entries[:max_documents]]

    @classmethod
    def _extract_cvss_score(cls, payload: Any) -> float | None:
        scores: list[float] = []

        def _visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_text = str(key).lower()
                    if key_text in {"basescore", "score", "cvssscore", "cvss_score"}:
                        score = cls._coerce_score(value)
                        if score is not None:
                            scores.append(score)
                    _visit(value)
            elif isinstance(node, list):
                for item in node:
                    _visit(item)

        _visit(payload)
        return max(scores) if scores else None

    def _extract_severity(self, vulnerability: dict[str, Any]) -> str:
        threats = vulnerability.get("Threats", [])
        if isinstance(threats, list):
            for threat in threats:
                if not isinstance(threat, dict):
                    continue
                for candidate in (
                    threat.get("Severity"),
                    threat.get("Description"),
                    threat.get("Value"),
                ):
                    severity = self._normalize_source_severity(self._stringify(candidate))
                    if severity != "UNKNOWN":
                        return severity
        return self._severity_from_score(self._extract_cvss_score(vulnerability))

    def _extract_references(self, vulnerability: dict[str, Any], *, cve_id: str) -> tuple[str, ...]:
        references = vulnerability.get("References", [])
        if not isinstance(references, list):
            return (f"https://msrc.microsoft.com/update-guide/vulnerability/{cve_id}",)
        urls: list[str] = []
        for reference in references:
            if not isinstance(reference, dict):
                continue
            url = str(reference.get("URL") or reference.get("Url") or reference.get("url") or "").strip()
            if url and url not in urls:
                urls.append(url)
        if not urls:
            urls.append(f"https://msrc.microsoft.com/update-guide/vulnerability/{cve_id}")
        return tuple(urls)

    def _extract_description(self, vulnerability: dict[str, Any]) -> str:
        title = self._stringify(vulnerability.get("Title"))
        note_values: list[str] = []
        notes = vulnerability.get("Notes", [])
        if isinstance(notes, list):
            for note in notes:
                if not isinstance(note, dict):
                    continue
                value = self._stringify(note.get("Value") or note.get("Description") or note)
                if value and value not in note_values:
                    note_values.append(value)
        parts = [part for part in (title, " ".join(note_values[:3]).strip()) if part]
        return " ".join(parts).strip()

    def parse_document(self, payload: dict[str, Any], *, max_items: int) -> list[ScrapedSample]:
        document_payload = self._ensure_json_object(payload, source=self.SOURCE)
        document_tracking = document_payload.get("DocumentTracking", {})
        vulnerabilities = document_payload.get("Vulnerability", []) or document_payload.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            raise ValueError("msrc: document payload missing vulnerability list")
        published_at = str(
            (document_tracking.get("CurrentReleaseDate") if isinstance(document_tracking, dict) else "")
            or (document_tracking.get("InitialReleaseDate") if isinstance(document_tracking, dict) else "")
            or document_payload.get("CurrentReleaseDate")
            or ""
        ).strip()
        samples: list[ScrapedSample] = []
        for vulnerability in vulnerabilities:
            if len(samples) >= max_items:
                break
            if not isinstance(vulnerability, dict):
                self._log_partial_failure(reason="vulnerability_not_object")
                continue
            cve_id = str(vulnerability.get("CVE") or vulnerability.get("cve") or "").strip()
            description = self._extract_description(vulnerability)
            if not cve_id or not description:
                self._log_partial_failure(
                    reason="missing_required_fields",
                    cve_id=cve_id or "<missing-cve-id>",
                )
                continue
            cvss_score = self._extract_cvss_score(vulnerability)
            severity = self._extract_severity(vulnerability)
            references = self._extract_references(vulnerability, cve_id=cve_id)
            title = self._stringify(vulnerability.get("Title")) or cve_id
            tags: list[str] = []
            threats = vulnerability.get("Threats", [])
            if isinstance(threats, list):
                for threat in threats:
                    if not isinstance(threat, dict):
                        continue
                    tag = self._stringify(threat.get("Type"))
                    if tag and tag not in tags:
                        tags.append(tag)
            samples.append(
                ScrapedSample(
                    source=self.SOURCE,
                    advisory_id=cve_id,
                    url=references[0],
                    title=title,
                    description=description,
                    severity=severity,
                    cve_id=cve_id,
                    cvss_score=cvss_score,
                    tags=tuple(tags),
                    references=references,
                    published_at=published_at or None,
                    modified_at=published_at or None,
                    vendor="Microsoft",
                )
            )
        return samples

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        updates_payload = self._get_json(self.UPDATES_URL)
        document_ids = self.extract_document_ids(updates_payload, max_documents=max(1, min(max_items, 12)))
        samples: list[ScrapedSample] = []
        for document_id in document_ids:
            if len(samples) >= max_items:
                break
            try:
                payload = self._get_json(
                    self.DOCUMENT_URL_TEMPLATE.format(document_id=quote(document_id, safe=""))
                )
                samples.extend(self.parse_document(payload, max_items=max_items - len(samples)))
            except Exception as exc:
                self._log_partial_failure(
                    reason="document_fetch_failed",
                    document_id=document_id,
                    error_type=type(exc).__name__,
                )
        return samples[:max_items]
