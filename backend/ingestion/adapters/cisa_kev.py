"""CISA KEV adapter."""

from __future__ import annotations

import logging

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.cisa_kev")


class CISAKEVAdapter(BaseAdapter):
    SOURCE = "cisa_kev"
    URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    async def fetch(self) -> list[IngestedSample]:
        async with aiohttp.ClientSession() as session:
            payload = await self._get(session, self.URL)
        return [
            make_sample(
                source=self.SOURCE,
                raw_text=f"{entry.get('vendorProject', '')} {entry.get('product', '')} {entry.get('shortDescription', '')}".strip(),
                url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                cve_id=entry.get("cveID", ""),
                severity="CRITICAL",
                tags=("kev", "exploited_in_wild"),
            )
            for entry in payload.get("vulnerabilities", [])
            if f"{entry.get('vendorProject', '')} {entry.get('product', '')} {entry.get('shortDescription', '')}".strip()
        ]


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
