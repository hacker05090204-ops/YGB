"""OSV scraper using the public index plus OSV detail retrieval with safe fallbacks."""

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
    QUERY_URL = "https://api.osv.dev/v1/query"
    QUERY_BATCH_URL = "https://api.osv.dev/v1/querybatch"
    INDEX_URL = "https://osv-vulnerabilities.storage.googleapis.com/index.json"
    API_URL_TEMPLATE = "https://api.osv.dev/v1/vulns/{vuln_id}"
    DEFAULT_QUERY_BATCH = (
        {"package": {"ecosystem": "PyPI", "name": "requests"}},
        {"package": {"ecosystem": "npm", "name": "lodash"}},
        {"package": {"ecosystem": "Go", "name": "github.com/gin-gonic/gin"}},
        {"package": {"ecosystem": "Maven", "name": "org.apache.logging.log4j:log4j-core"}},
    )

    def _fetch_query_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response_payload = self._post_json(self.QUERY_URL, payload)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            if status_code == 400:
                raise ValueError("osv: query payload rejected (HTTP 400)") from exc
            if status_code == 404:
                raise RuntimeError("osv: query endpoint moved (HTTP 404)") from exc
            if status_code == 410:
                raise RuntimeError("osv: query endpoint removed (HTTP 410)") from exc
            if status_code == 429:
                raise RuntimeError("osv: rate limited (HTTP 429)") from exc
            raise RuntimeError(f"osv: query endpoint failed (HTTP {status_code})") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"osv: query request failed: {exc}") from exc
        return self._ensure_json_object(response_payload, source=self.SOURCE)

    def _fetch_query_batch(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            response_payload = self._post_json(self.QUERY_BATCH_URL, {"queries": queries})
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            if status_code == 400:
                raise ValueError("osv: querybatch payload rejected (HTTP 400)") from exc
            if status_code == 404:
                raise RuntimeError("osv: querybatch endpoint moved (HTTP 404)") from exc
            if status_code == 410:
                raise RuntimeError("osv: querybatch endpoint removed (HTTP 410)") from exc
            if status_code == 429:
                raise RuntimeError("osv: querybatch rate limited (HTTP 429)") from exc
            raise RuntimeError(f"osv: querybatch endpoint failed (HTTP {status_code})") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"osv: querybatch request failed: {exc}") from exc

        payload = self._ensure_json_object(response_payload, source=self.SOURCE)
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError("osv: querybatch payload missing results list")
        return [item for item in results if isinstance(item, dict)]

    @staticmethod
    def _extract_query_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        vulns = payload.get("vulns", [])
        if not isinstance(vulns, list):
            raise ValueError("osv: query payload missing vuln list")
        next_page_token = str(payload.get("next_page_token") or "").strip()
        normalized = [item for item in vulns if isinstance(item, dict)]
        return normalized, next_page_token

    def _fetch_recent_from_query(self, max_items: int) -> list[ScrapedSample]:
        samples: list[ScrapedSample] = []
        seen_ids: set[str] = set()
        for package_query in self.DEFAULT_QUERY_BATCH:
            try:
                query_payload = self._fetch_query_page(dict(package_query))
            except (RuntimeError, ValueError) as exc:
                self._log_partial_failure(
                    reason="query_fetch_failed",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
                continue
            vuln_payloads, _ = self._extract_query_items(query_payload)
            for vuln_payload in vuln_payloads:
                advisory_id = str(vuln_payload.get("id", "")).strip()
                if not advisory_id or advisory_id in seen_ids:
                    continue
                seen_ids.add(advisory_id)
                sample = self.parse_vulnerability(vuln_payload)
                if sample is not None:
                    samples.append(sample)
                if len(samples) >= max_items:
                    return samples
        return samples

    def _fetch_recent_from_querybatch(self, max_items: int) -> list[ScrapedSample]:
        samples: list[ScrapedSample] = []
        seen_ids: set[str] = set()
        for result in self._fetch_query_batch(list(self.DEFAULT_QUERY_BATCH)):
            vuln_payloads = result.get("vulns", [])
            if not isinstance(vuln_payloads, list):
                continue
            for vuln_payload in vuln_payloads:
                if not isinstance(vuln_payload, dict):
                    continue
                advisory_id = str(vuln_payload.get("id", "")).strip()
                if not advisory_id or advisory_id in seen_ids:
                    continue
                seen_ids.add(advisory_id)
                try:
                    detail_payload = self._get_json(
                        self.API_URL_TEMPLATE.format(vuln_id=quote(advisory_id, safe=""))
                    )
                    sample = self.parse_vulnerability(detail_payload)
                    if sample is not None:
                        samples.append(sample)
                except Exception as exc:
                    self._log_partial_failure(
                        reason="querybatch_detail_fetch_failed",
                        advisory_id=advisory_id,
                        error_type=type(exc).__name__,
                    )
                if len(samples) >= max_items:
                    return samples
        return samples

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
            self._log_partial_failure(
                reason="missing_required_fields",
                advisory_id=advisory_id or "<missing-advisory-id>",
            )
            return None
        resolved_identifier = self._extract_cve_id(vulnerability_payload) or advisory_id
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
            cve_id=resolved_identifier,
            cvss_score=self._extract_cvss_score(vulnerability_payload),
            tags=self._extract_tags(vulnerability_payload),
            aliases=aliases,
            references=self._extract_references(vulnerability_payload),
            published_at=str(vulnerability_payload.get("published", "") or "") or None,
            modified_at=str(vulnerability_payload.get("modified", "") or "") or None,
        )

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        try:
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
                except Exception as exc:
                    self._log_partial_failure(
                        reason="vulnerability_fetch_failed",
                        advisory_id=vulnerability_id,
                        error_type=type(exc).__name__,
                    )
            if samples:
                return samples
        except Exception as exc:
            self._log_partial_failure(
                reason="index_fetch_failed",
                error_type=type(exc).__name__,
                detail=str(exc),
            )

        try:
            batch_samples = self._fetch_recent_from_querybatch(max_items)
            if batch_samples:
                return batch_samples[:max_items]
        except (RuntimeError, ValueError) as exc:
            self._log_partial_failure(
                reason="querybatch_fetch_failed",
                error_type=type(exc).__name__,
                detail=str(exc),
            )

        try:
            query_samples = self._fetch_recent_from_query(max_items)
            if query_samples:
                return query_samples[:max_items]
        except (RuntimeError, ValueError) as exc:
            self._log_partial_failure(
                reason="query_fetch_failed",
                error_type=type(exc).__name__,
                detail=str(exc),
            )
        return []
