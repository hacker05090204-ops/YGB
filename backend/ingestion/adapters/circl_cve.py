"""CIRCL CVE adapter."""

from __future__ import annotations

import logging

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.circl_cve")


class CIRCLCVEAdapter(BaseAdapter):
    SOURCE = "circl_cve"
    URL = "https://cve.circl.lu/api/last/100"

    @staticmethod
    def _extract_score(entry: dict[str, object]) -> float | None:
        score = entry.get("cvss")
        if isinstance(score, (int, float)):
            return float(score)
        if isinstance(score, str):
            try:
                return float(score)
            except ValueError:
                return None
        return None

    @classmethod
    def _extract_severity(cls, entry: dict[str, object]) -> str:
        score = cls._extract_score(entry)
        if score is None:
            return "INFO"
        if score >= 9:
            return "CRITICAL"
        if score >= 7:
            return "HIGH"
        if score >= 4:
            return "MEDIUM"
        if score > 0:
            return "LOW"
        return "INFO"

    async def fetch(self) -> list[IngestedSample]:
        timeout = aiohttp.ClientTimeout(total=60, connect=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            payload = await self._get(session, self.URL, timeout=timeout)

        entries = payload if isinstance(payload, list) else []
        samples: list[IngestedSample] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            cve_id = str(entry.get("id", "")).strip()
            summary = str(entry.get("summary", "")).strip()[:512]
            if not cve_id or not summary:
                continue
            samples.append(
                make_sample(
                    source=self.SOURCE,
                    raw_text=summary,
                    url=f"https://cve.circl.lu/cve/{cve_id}",
                    cve_id=cve_id,
                    severity=self._extract_severity(entry),
                    tags=("circl", "cve"),
                )
            )
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
