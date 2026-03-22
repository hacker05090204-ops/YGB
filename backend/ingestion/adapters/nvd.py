"""NVD CVE adapter."""

from __future__ import annotations

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
        pub_start_date = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        pub_end_date = now.isoformat().replace("+00:00", "Z")
        async with aiohttp.ClientSession() as session:
            while total_results is None or start_index < total_results:
                payload = await self._get(
                    session,
                    self.BASE,
                    params={
                        "resultsPerPage": 2000,
                        "startIndex": start_index,
                        "pubStartDate": pub_start_date,
                        "pubEndDate": pub_end_date,
                    },
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
                start_index += int(payload.get("resultsPerPage", 2000))
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
