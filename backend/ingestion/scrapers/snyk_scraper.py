"""Snyk scraper backed by public advisory listing and detail pages."""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample
from backend.ingestion.scrapers.osv_scraper import OSVScraper


class SnykScraper(BaseScraper):
    """Scrape npm vulnerability data using OSV as the maintained Snyk replacement path."""

    SOURCE = "snyk"
    MAX_RETRIES = 0
    REQUEST_DELAY_SECONDS = 1.0
    TIMEOUT_SECONDS = 3.0
    LISTING_ID_MULTIPLIER = 2
    MIN_LISTING_IDS = 5
    ECOSYSTEMS = ("npm", "pip", "maven", "nuget")
    QUERY_URL = "https://api.osv.dev/v1/query"
    OSV_DETAIL_URL_TEMPLATE = "https://api.osv.dev/v1/vulns/{advisory_id}"
    DEFAULT_QUERY_PACKAGES = ("lodash", "minimist", "ws", "axios", "serialize-javascript")
    LIST_URL_TEMPLATE = "https://security.snyk.io/vuln/{ecosystem}"
    DETAIL_URL_TEMPLATE = "https://security.snyk.io/vuln/{advisory_id}"
    ADVISORY_ID_PATTERN = re.compile(r"/vuln/(SNYK-[A-Z0-9-]+)", re.IGNORECASE)
    NEXT_DATA_PATTERN = re.compile(
        r"<script[^>]+id=[\"']__NEXT_DATA__[\"'][^>]*>(?P<json>.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    META_DESCRIPTION_PATTERN = re.compile(
        r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'](?P<content>.*?)[\"']",
        re.IGNORECASE | re.DOTALL,
    )
    TITLE_PATTERN = re.compile(r"<title>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)
    CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)

    @staticmethod
    def _clean_html_text(value: object) -> str:
        return " ".join(html.unescape(str(value or "")).split())

    def extract_advisory_ids(self, html_text: str, *, max_items: int) -> list[str]:
        advisory_ids: list[str] = []
        for advisory_id in self.ADVISORY_ID_PATTERN.findall(html_text):
            normalized = advisory_id.upper()
            if normalized not in advisory_ids:
                advisory_ids.append(normalized)
            if len(advisory_ids) >= max_items:
                break
        return advisory_ids

    def _extract_next_data(self, html_text: str) -> dict[str, Any] | None:
        match = self.NEXT_DATA_PATTERN.search(html_text)
        if match is None:
            return None
        try:
            payload = json.loads(html.unescape(match.group("json")))
        except json.JSONDecodeError as exc:
            raise ValueError("snyk: invalid __NEXT_DATA__ payload") from exc
        return self._ensure_json_object(payload, source=self.SOURCE)

    def _find_advisory_payload(self, node: Any, advisory_id: str) -> dict[str, Any] | None:
        if isinstance(node, dict):
            node_id = str(node.get("id") or node.get("advisoryId") or "").strip().upper()
            if node_id == advisory_id.upper():
                return node
            for value in node.values():
                found = self._find_advisory_payload(value, advisory_id)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_advisory_payload(item, advisory_id)
                if found is not None:
                    return found
        return None

    def _extract_identifier_list(self, payload: dict[str, Any], key: str) -> tuple[str, ...]:
        identifiers = payload.get("identifiers", {})
        if not isinstance(identifiers, dict):
            return ()
        for identifier_key, identifier_value in identifiers.items():
            if str(identifier_key).strip().upper() != key.upper():
                continue
            if isinstance(identifier_value, list):
                return tuple(
                    str(item).strip()
                    for item in identifier_value
                    if str(item or "").strip()
                )
        return ()

    def _extract_references(self, payload: dict[str, Any]) -> tuple[str, ...]:
        references = payload.get("references", [])
        if not isinstance(references, list):
            return ()
        urls: list[str] = []
        for reference in references:
            if isinstance(reference, dict):
                url = str(reference.get("url") or reference.get("URL") or "").strip()
            else:
                url = str(reference or "").strip()
            if url and url not in urls:
                urls.append(url)
        return tuple(urls)

    @staticmethod
    def _extract_osv_aliases(payload: dict[str, Any]) -> tuple[str, ...]:
        aliases_payload = payload.get("aliases", [])
        if not isinstance(aliases_payload, list):
            return ()
        aliases: list[str] = []
        for alias in aliases_payload:
            alias_text = str(alias or "").strip()
            if alias_text and alias_text not in aliases:
                aliases.append(alias_text)
        return tuple(aliases)

    @staticmethod
    def _extract_osv_package_names(payload: dict[str, Any]) -> tuple[str, ...]:
        package_names: list[str] = []
        affected = payload.get("affected", [])
        if not isinstance(affected, list):
            return ()
        for item in affected:
            if not isinstance(item, dict):
                continue
            package = item.get("package", {})
            if not isinstance(package, dict):
                continue
            package_name = str(package.get("name", "")).strip()
            if package_name and package_name not in package_names:
                package_names.append(package_name)
        return tuple(package_names)

    def parse_osv_vulnerability(
        self,
        payload: dict[str, Any],
        *,
        ecosystem: str,
        package_name: str = "",
    ) -> ScrapedSample | None:
        advisory_payload = self._ensure_json_object(payload, source=self.SOURCE)
        advisory_id = str(advisory_payload.get("id", "")).strip()
        summary = self._clean_html_text(advisory_payload.get("summary"))
        description = self._clean_html_text(advisory_payload.get("details"))
        full_description = " ".join(part for part in (summary, description) if part).strip()
        if not advisory_id or not full_description:
            self._log_partial_failure(
                reason="missing_osv_required_fields",
                advisory_id=advisory_id or "<missing-advisory-id>",
            )
            return None

        aliases = self._extract_osv_aliases(advisory_payload)
        cve_aliases = tuple(alias for alias in aliases if alias.upper().startswith("CVE-"))
        resolved_identifier = cve_aliases[0] if cve_aliases else advisory_id
        package_names = self._extract_osv_package_names(advisory_payload)
        effective_package = package_name or (package_names[0] if package_names else "")
        tags = list(
            dict.fromkeys(
                tag
                for tag in (ecosystem, effective_package, *OSVScraper._extract_tags(advisory_payload))
                if str(tag or "").strip()
            )
        )
        return ScrapedSample(
            source=self.SOURCE,
            advisory_id=advisory_id,
            url=f"https://osv.dev/vulnerability/{advisory_id}",
            title=summary or advisory_id,
            description=full_description,
            severity=OSVScraper._extract_severity(advisory_payload),
            cve_id=resolved_identifier,
            cvss_score=OSVScraper._extract_cvss_score(advisory_payload),
            tags=tuple(tags),
            aliases=aliases,
            references=OSVScraper._extract_references(advisory_payload),
            published_at=str(advisory_payload.get("published", "") or "") or None,
            modified_at=str(advisory_payload.get("modified", "") or "") or None,
            product=effective_package,
        )

    def _fetch_recent_from_osv(self, max_items: int) -> list[ScrapedSample]:
        samples: list[ScrapedSample] = []
        seen_advisory_ids: set[str] = set()
        for package_name in self.DEFAULT_QUERY_PACKAGES:
            if len(samples) >= max_items:
                break
            try:
                payload = self._post_json(
                    self.QUERY_URL,
                    {"package": {"ecosystem": "npm", "name": package_name}},
                )
                query_payload = self._ensure_json_object(payload, source=self.SOURCE)
            except Exception as exc:
                self._log_partial_failure(
                    reason="osv_query_failed",
                    package_name=package_name,
                    error_type=type(exc).__name__,
                )
                continue

            vuln_payloads = query_payload.get("vulns", [])
            if not isinstance(vuln_payloads, list):
                continue
            for vuln_payload in vuln_payloads:
                if len(samples) >= max_items or not isinstance(vuln_payload, dict):
                    break
                advisory_id = str(vuln_payload.get("id", "")).strip()
                if not advisory_id or advisory_id in seen_advisory_ids:
                    continue
                seen_advisory_ids.add(advisory_id)
                detail_payload = vuln_payload
                if not str(vuln_payload.get("summary") or vuln_payload.get("details") or "").strip():
                    try:
                        detail_payload = self._get_json(
                            self.OSV_DETAIL_URL_TEMPLATE.format(
                                advisory_id=quote(advisory_id, safe="")
                            )
                        )
                    except Exception as exc:
                        self._log_partial_failure(
                            reason="osv_detail_fetch_failed",
                            advisory_id=advisory_id,
                            error_type=type(exc).__name__,
                        )
                        continue
                sample = self.parse_osv_vulnerability(
                    detail_payload,
                    ecosystem="npm",
                    package_name=package_name,
                )
                if sample is not None:
                    samples.append(sample)
        return samples[:max_items]

    def parse_detail_html(
        self,
        advisory_id: str,
        html_text: str,
        *,
        ecosystem: str = "",
    ) -> ScrapedSample | None:
        next_data = self._extract_next_data(html_text)
        advisory_payload = self._find_advisory_payload(next_data, advisory_id) if next_data else None

        if advisory_payload is None:
            self._log_partial_failure(
                reason="missing_advisory_payload",
                advisory_id=advisory_id,
            )
            return None

        cve_aliases = self._extract_identifier_list(advisory_payload, "CVE")
        if not cve_aliases:
            fallback_cves = [match.upper() for match in self.CVE_PATTERN.findall(html_text)]
            cve_aliases = tuple(dict.fromkeys(fallback_cves))
        cwe_tags = self._extract_identifier_list(advisory_payload, "CWE")

        title = self._clean_html_text(advisory_payload.get("title"))
        if not title:
            title_match = self.TITLE_PATTERN.search(html_text)
            title = self._clean_html_text(title_match.group("title")) if title_match else advisory_id
            if title.endswith(" | Snyk"):
                title = title[: -len(" | Snyk")].strip()

        description = self._clean_html_text(
            advisory_payload.get("description") or advisory_payload.get("overview")
        )
        if not description:
            meta_match = self.META_DESCRIPTION_PATTERN.search(html_text)
            description = self._clean_html_text(meta_match.group("content")) if meta_match else ""
        if not cve_aliases or not description:
            self._log_partial_failure(
                reason="missing_required_fields",
                advisory_id=advisory_id,
            )
            return None

        cvss_score = self._coerce_score(advisory_payload.get("cvssScore") or advisory_payload.get("cvss_score"))
        severity = self._normalize_source_severity(advisory_payload.get("severity"))
        if severity == "UNKNOWN":
            severity = self._severity_from_score(cvss_score)

        tags = list(dict.fromkeys(tag for tag in (*cwe_tags, ecosystem, str(advisory_payload.get("packageManager", "")).strip()) if tag))
        product = self._clean_html_text(advisory_payload.get("packageName") or advisory_payload.get("package"))
        references = self._extract_references(advisory_payload)
        url = self.DETAIL_URL_TEMPLATE.format(advisory_id=advisory_id)

        return ScrapedSample(
            source=self.SOURCE,
            advisory_id=advisory_id,
            url=url,
            title=title or advisory_id,
            description=description,
            severity=severity,
            cve_id=cve_aliases[0],
            cvss_score=cvss_score,
            tags=tuple(tags),
            aliases=cve_aliases,
            references=references,
            published_at=str(advisory_payload.get("publicationTime", "") or "") or None,
            modified_at=str(advisory_payload.get("modificationTime", "") or "") or None,
            product=product,
        )

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        osv_samples = self._fetch_recent_from_osv(max_items)
        if osv_samples:
            return osv_samples[:max_items]

        samples: list[ScrapedSample] = []
        seen_advisory_ids: set[str] = set()
        max_detail_attempts = max(max_items * self.LISTING_ID_MULTIPLIER, self.MIN_LISTING_IDS)
        detail_attempts = 0
        for ecosystem in self.ECOSYSTEMS:
            if len(samples) >= max_items or detail_attempts >= max_detail_attempts:
                break
            try:
                listing_html = self._get_text(self.LIST_URL_TEMPLATE.format(ecosystem=ecosystem))
                advisory_ids = self.extract_advisory_ids(
                    listing_html,
                    max_items=max(max_items * self.LISTING_ID_MULTIPLIER, self.MIN_LISTING_IDS),
                )
            except Exception as exc:
                self._log_partial_failure(
                    reason="listing_fetch_failed",
                    ecosystem=ecosystem,
                    error_type=type(exc).__name__,
                )
                continue

            for advisory_id in advisory_ids:
                if len(samples) >= max_items or detail_attempts >= max_detail_attempts:
                    break
                if advisory_id in seen_advisory_ids:
                    continue
                seen_advisory_ids.add(advisory_id)
                detail_attempts += 1
                try:
                    detail_html = self._get_text(self.DETAIL_URL_TEMPLATE.format(advisory_id=advisory_id))
                    sample = self.parse_detail_html(advisory_id, detail_html, ecosystem=ecosystem)
                    if sample is not None:
                        samples.append(sample)
                except Exception as exc:
                    self._log_partial_failure(
                        reason="detail_fetch_failed",
                        advisory_id=advisory_id,
                        ecosystem=ecosystem,
                        error_type=type(exc).__name__,
                    )
        return samples[:max_items]
