"""NVD CVE adapter."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.nvd")


class NVDAdapter(BaseAdapter):
    SOURCE = "nvd"
    BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    @staticmethod
    def _extract_description(entry: dict[str, object]) -> str:
        descriptions = entry.get("descriptions", [])
        english = next((item.get("value", "") for item in descriptions if item.get("lang") == "en"), "")
        if english:
            return str(english)
        if descriptions:
            return str(descriptions[0].get("value", ""))
        return ""

    @staticmethod
    def _extract_severity(entry: dict[str, object]) -> str:
        metrics = entry.get("metrics", {})
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            values = metrics.get(key, [])
            if values:
                cvss = values[0].get("cvssData", {})
                return str(cvss.get("baseSeverity", "UNKNOWN"))
        return "UNKNOWN"

    @staticmethod
    def _extract_tags(entry: dict[str, object]) -> tuple[str, ...]:
        tags: list[str] = []
        for weakness in entry.get("weaknesses", []):
            for description in weakness.get("description", []):
                value = str(description.get("value", "")).strip()
                if value:
                    tags.append(value)
        return tuple(tags)

    async def fetch(self) -> list[IngestedSample]:
        samples: list[IngestedSample] = []
        start_index = 0
        total_results = None
        now = datetime.now(timezone.utc).replace(microsecond=0)
        results_per_page = 500
        timeout = aiohttp.ClientTimeout(total=120, connect=30)
        pub_start_date = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
        pub_end_date = now.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while total_results is None or start_index < total_results:
                payload = await self._get(
                    session,
                    self.BASE,
                    params={
                        "resultsPerPage": results_per_page,
                        "startIndex": start_index,
                        "pubStartDate": pub_start_date,
                        "pubEndDate": pub_end_date,
                    },
                    timeout=timeout,
                )
                total_results = int(payload.get("totalResults", 0))
                vulnerabilities = payload.get("vulnerabilities", [])
                if not vulnerabilities:
                    break
                for vulnerability in vulnerabilities:
                    cve = vulnerability.get("cve", {})
                    cve_id = str(cve.get("id", ""))
                    raw_text = self._extract_description(cve)
                    if not raw_text:
                        continue
                    samples.append(
                        make_sample(
                            source=self.SOURCE,
                            raw_text=raw_text,
                            url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                            cve_id=cve_id,
                            severity=self._extract_severity(cve),
                            tags=self._extract_tags(cve),
                        )
                    )
                start_index += int(payload.get("resultsPerPage", results_per_page))
                if total_results is not None and start_index < total_results:
                    remaining = self._last_response_headers.get("X-RateLimit-Remaining", "")
                    reset = self._last_response_headers.get("X-RateLimit-Reset", "")
                    if remaining.isdigit() and reset.isdigit() and int(remaining) <= 1:
                        sleep_seconds = max(int(reset) - int(datetime.now(timezone.utc).timestamp()), 1)
                    else:
                        sleep_seconds = 6
                    await asyncio.sleep(sleep_seconds)
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
