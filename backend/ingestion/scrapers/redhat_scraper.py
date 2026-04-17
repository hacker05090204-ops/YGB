"""Red Hat advisory scraper backed by the public securitydata API with Hydra fallback."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample


class RedHatAdvisoryScraper(BaseScraper):
    """Scrape recent Red Hat CVE entries and enrich them with detail records."""

    SOURCE = "redhat"
    REQUEST_DELAY_SECONDS = 1.0
    LIST_URLS = (
        "https://access.redhat.com/hydra/rest/securitydata/cve.json",
        "https://access.redhat.com/labs/securitydataapi/cve.json",
    )
    DETAIL_URL_TEMPLATES = (
        "https://access.redhat.com/hydra/rest/securitydata/cve/{cve_id}.json",
        "https://access.redhat.com/labs/securitydataapi/cve/{cve_id}.json",
    )
    DETAIL_PAGE_URL_TEMPLATE = "https://access.redhat.com/security/cve/{cve_id}"

    def _fetch_from_candidates(
        self,
        urls: tuple[str, ...],
        *,
        params: dict[str, Any] | None = None,
        cve_id: str = "",
    ) -> Any:
        last_error: Exception | None = None
        for url in urls:
            try:
                return self._get_json(url, params=params)
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else 0
                self._log_partial_failure(
                    reason=f"candidate_http_{status_code}",
                    url=url,
                    cve_id=cve_id,
                )
                if status_code in {404, 410}:
                    continue
                raise RuntimeError(f"redhat: upstream request failed (HTTP {status_code})") from exc
            except requests.RequestException as exc:
                last_error = exc
                self._log_partial_failure(
                    reason="candidate_request_exception",
                    url=url,
                    cve_id=cve_id,
                    error_type=type(exc).__name__,
                )
                continue
        if last_error is not None:
            raise RuntimeError(f"redhat: no working advisory endpoint: {last_error}") from last_error
        raise RuntimeError("redhat: no advisory endpoint candidates configured")

    def extract_recent_ids(self, payload: Any, *, max_items: int) -> list[str]:
        raw_entries: Any = payload
        if isinstance(payload, dict):
            raw_entries = payload.get("data") or payload.get("items") or payload.get("cves") or []
        if not isinstance(raw_entries, list):
            raise ValueError("redhat: list payload missing array entries")
        ranked_entries: list[tuple[str, str]] = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                self._log_partial_failure(reason="list_entry_not_object")
                continue
            cve_id = str(entry.get("CVE") or entry.get("name") or entry.get("cve") or "").strip()
            if not cve_id:
                self._log_partial_failure(reason="missing_cve_id")
                continue
            sort_key = str(
                entry.get("public_date")
                or entry.get("publicDate")
                or entry.get("last_modified")
                or entry.get("lastModified")
                or ""
            ).strip()
            ranked_entries.append((cve_id, sort_key))
        ranked_entries.sort(key=lambda item: item[1], reverse=True)
        return [item[0] for item in ranked_entries[:max_items]]

    @staticmethod
    def _extract_reference_urls(payload: dict[str, Any], *, cve_id: str) -> tuple[str, ...]:
        urls: list[str] = []
        references = payload.get("references", [])
        if isinstance(references, list):
            for reference in references:
                url = str(reference or "").strip()
                if url and url not in urls:
                    urls.append(url)
        bugzilla = payload.get("bugzilla", {})
        if isinstance(bugzilla, dict):
            bugzilla_url = str(bugzilla.get("url", "")).strip()
            if bugzilla_url and bugzilla_url not in urls:
                urls.append(bugzilla_url)
        mitre_url = str(payload.get("mitre_url", "")).strip()
        if mitre_url and mitre_url not in urls:
            urls.append(mitre_url)
        if not urls:
            urls.append(f"https://access.redhat.com/security/cve/{cve_id}")
        return tuple(urls)

    @staticmethod
    def _extract_product(payload: dict[str, Any]) -> str:
        package_state = payload.get("package_state", [])
        if isinstance(package_state, list):
            for entry in package_state:
                if not isinstance(entry, dict):
                    continue
                product_name = str(entry.get("product_name", "")).strip()
                if product_name:
                    return product_name
        affected_release = payload.get("affected_release", [])
        if isinstance(affected_release, list):
            for entry in affected_release:
                if not isinstance(entry, dict):
                    continue
                product_name = str(entry.get("product_name", "")).strip()
                if product_name:
                    return product_name
        return ""

    @staticmethod
    def _extract_tags(payload: dict[str, Any]) -> tuple[str, ...]:
        tags: list[str] = []
        package_state = payload.get("package_state", [])
        if isinstance(package_state, list):
            for entry in package_state:
                if not isinstance(entry, dict):
                    continue
                package_name = str(entry.get("package_name", "")).strip()
                if package_name and package_name not in tags:
                    tags.append(package_name)
        return tuple(tags)

    def parse_detail(self, payload: dict[str, Any]) -> ScrapedSample | None:
        detail_payload = self._ensure_json_object(payload, source=self.SOURCE)
        cve_id = str(detail_payload.get("name") or detail_payload.get("CVE") or detail_payload.get("cve") or "").strip()
        bugzilla = detail_payload.get("bugzilla", {})
        bugzilla_description = ""
        bugzilla_title = ""
        if isinstance(bugzilla, dict):
            bugzilla_description = str(bugzilla.get("description", "")).strip()
            bugzilla_title = str(bugzilla.get("title", "")).strip()
        details = detail_payload.get("details", [])
        detail_parts: list[str] = []
        if isinstance(details, list):
            detail_parts.extend(str(item or "").strip() for item in details if str(item or "").strip())
        statement = str(detail_payload.get("statement", "")).strip()
        description = " ".join(
            part
            for part in (
                bugzilla_description,
                statement,
                " ".join(detail_parts).strip(),
            )
            if part
        ).strip()
        if not cve_id or not description:
            self._log_partial_failure(
                reason="missing_required_fields",
                cve_id=cve_id or "<missing-cve-id>",
            )
            return None

        cvss3 = detail_payload.get("cvss3", {}) if isinstance(detail_payload.get("cvss3"), dict) else {}
        cvss2 = detail_payload.get("cvss", {}) if isinstance(detail_payload.get("cvss"), dict) else {}
        cvss_score = self._coerce_score(cvss3.get("cvss3_base_score") or cvss2.get("cvss_base_score"))
        severity = self._normalize_source_severity(detail_payload.get("threat_severity"))
        if severity == "UNKNOWN":
            severity = self._severity_from_score(cvss_score)
        references = self._extract_reference_urls(detail_payload, cve_id=cve_id)
        product = self._extract_product(detail_payload)

        return ScrapedSample(
            source=self.SOURCE,
            advisory_id=cve_id,
            url=self.DETAIL_PAGE_URL_TEMPLATE.format(cve_id=cve_id),
            title=bugzilla_title or cve_id,
            description=description,
            severity=severity,
            cve_id=cve_id,
            cvss_score=cvss_score,
            tags=self._extract_tags(detail_payload),
            references=references,
            published_at=str(detail_payload.get("public_date", "") or "") or None,
            modified_at=str(detail_payload.get("last_modified", "") or "") or None,
            vendor="Red Hat",
            product=product,
        )

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        list_payload = self._fetch_from_candidates(
            self.LIST_URLS,
            params={"after": "2024-01-01", "per_page": min(max(max_items * 4, 20), 100), "page": 1},
        )
        cve_ids = self.extract_recent_ids(list_payload, max_items=max(max_items * 2, 10))
        samples: list[ScrapedSample] = []
        for cve_id in cve_ids:
            if len(samples) >= max_items:
                break
            try:
                detail_urls = tuple(
                    template.format(cve_id=quote(cve_id, safe=""))
                    for template in self.DETAIL_URL_TEMPLATES
                )
                detail_payload = self._fetch_from_candidates(detail_urls, cve_id=cve_id)
                sample = self.parse_detail(detail_payload)
                if sample is not None:
                    samples.append(sample)
            except Exception as exc:
                self._log_partial_failure(
                    reason="detail_fetch_failed",
                    cve_id=cve_id,
                    error_type=type(exc).__name__,
                )
        return samples[:max_items]
