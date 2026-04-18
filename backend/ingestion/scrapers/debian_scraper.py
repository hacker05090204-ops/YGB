"""Debian security tracker scraper backed by the public JSON tracker."""

from __future__ import annotations

from typing import Any

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample


class DebianTrackerScraper(BaseScraper):
    """Scrape Debian security tracker records and normalize them into CVE samples."""

    SOURCE = "debian"
    REQUEST_DELAY_SECONDS = 1.0
    TIMEOUT_SECONDS = 60.0
    FEED_URL = "https://security-tracker.debian.org/tracker/data/json"
    DETAIL_URL_TEMPLATE = "https://security-tracker.debian.org/tracker/{cve_id}"
    _URGENCY_RANK = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "unimportant": 1,
        "not yet assigned": 0,
        "end-of-life": 0,
    }
    _URGENCY_SEVERITY = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "unimportant": "LOW",
        "not yet assigned": "UNKNOWN",
        "end-of-life": "UNKNOWN",
    }

    def _severity_from_releases(self, releases: Any) -> str:
        if not isinstance(releases, dict):
            return "UNKNOWN"
        best_urgency = "not yet assigned"
        best_rank = -1
        for release_payload in releases.values():
            if not isinstance(release_payload, dict):
                continue
            urgency = str(release_payload.get("urgency") or "not yet assigned").strip().lower()
            rank = self._URGENCY_RANK.get(urgency, 0)
            if rank > best_rank:
                best_rank = rank
                best_urgency = urgency
        return self._URGENCY_SEVERITY.get(best_urgency, "UNKNOWN")

    @staticmethod
    def _release_status_summary(releases: Any) -> str:
        if not isinstance(releases, dict):
            return ""
        entries: list[str] = []
        for release_name, release_payload in releases.items():
            if not isinstance(release_payload, dict):
                continue
            status = str(release_payload.get("status") or "unknown").strip()
            fixed_version = str(release_payload.get("fixed_version") or "").strip()
            detail = f"{release_name}:{status}"
            if fixed_version:
                detail += f" ({fixed_version})"
            entries.append(detail)
            if len(entries) >= 3:
                break
        return "; ".join(entries)

    def parse_tracker(self, payload: Any, *, max_items: int) -> list[ScrapedSample]:
        tracker_payload = self._ensure_json_object(payload, source=self.SOURCE)
        aggregated: dict[str, dict[str, Any]] = {}
        for package_name, cve_map in tracker_payload.items():
            normalized_package = str(package_name or "").strip()
            if not normalized_package or not isinstance(cve_map, dict):
                continue
            for cve_id, entry in cve_map.items():
                normalized_cve = str(cve_id or "").strip().upper()
                if not normalized_cve.startswith("CVE-") or not isinstance(entry, dict):
                    continue
                aggregate = aggregated.setdefault(
                    normalized_cve,
                    {
                        "description": "",
                        "severity": "UNKNOWN",
                        "packages": [],
                        "references": [self.DETAIL_URL_TEMPLATE.format(cve_id=normalized_cve)],
                        "status_summary": "",
                    },
                )
                if normalized_package not in aggregate["packages"]:
                    aggregate["packages"].append(normalized_package)
                description = str(entry.get("description") or "").strip()
                if description and not aggregate["description"]:
                    aggregate["description"] = description
                releases = entry.get("releases")
                severity = self._severity_from_releases(releases)
                if self._URGENCY_RANK.get(severity.lower(), 0) > self._URGENCY_RANK.get(
                    str(aggregate["severity"]).lower(),
                    0,
                ):
                    aggregate["severity"] = severity
                status_summary = self._release_status_summary(releases)
                if status_summary and not aggregate["status_summary"]:
                    aggregate["status_summary"] = status_summary

        ranked_cve_ids = sorted(
            aggregated,
            key=lambda cve_id: tuple(int(part) for part in cve_id[4:].split("-") if part.isdigit()),
            reverse=True,
        )
        samples: list[ScrapedSample] = []
        for cve_id in ranked_cve_ids[:max_items]:
            aggregate = aggregated[cve_id]
            packages = list(aggregate["packages"])
            package_summary = ", ".join(packages[:3]) if packages else "unknown package"
            description = str(aggregate["description"] or "").strip()
            if not description:
                description = f"Debian security tracker records {cve_id} for {package_summary}."
            status_summary = str(aggregate["status_summary"] or "").strip()
            if status_summary:
                description = f"{description} Release status: {status_summary}."
            samples.append(
                ScrapedSample(
                    source=self.SOURCE,
                    advisory_id=cve_id,
                    url=self.DETAIL_URL_TEMPLATE.format(cve_id=cve_id),
                    title=f"{cve_id} in Debian packages {package_summary}",
                    description=description,
                    severity=str(aggregate["severity"] or "UNKNOWN"),
                    cve_id=cve_id,
                    tags=tuple(packages[:5]),
                    aliases=(cve_id,),
                    references=tuple(aggregate["references"]),
                    vendor="Debian",
                    product=packages[0] if packages else "",
                )
            )
        return samples

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        payload = self._get_json(self.FEED_URL)
        return self.parse_tracker(payload, max_items=max_items)
