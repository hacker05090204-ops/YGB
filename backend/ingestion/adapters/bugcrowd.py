"""Bugcrowd public programs adapter."""

from __future__ import annotations

import logging

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.bugcrowd")


class BugcrowdAdapter(BaseAdapter):
    SOURCE = "bugcrowd"
    BASE = "https://bugcrowd.com/engagements.json"
    FALLBACK_BASE = "https://bugcrowd.com/disclosures.json"
    PARAMS = {
        "category": "bug_bounty",
        "sort_by": "promoted",
        "sort_direction": "desc",
        "page": 1,
    }

    async def fetch(self) -> list[IngestedSample]:
        timeout = aiohttp.ClientTimeout(total=60, connect=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                payload = await self._get(
                    session,
                    self.BASE,
                    params=self.PARAMS,
                    timeout=timeout,
                )
                engagements = payload.get("engagements", payload if isinstance(payload, list) else [])
            except Exception as primary_error:
                logger.warning(
                    "bugcrowd_engagements_unavailable",
                    extra={"source": self.SOURCE, "error": str(primary_error), "url": self.BASE},
                )
                try:
                    payload = await self._get(session, self.FALLBACK_BASE, timeout=timeout)
                    engagements = payload.get("disclosures", payload if isinstance(payload, list) else [])
                except Exception as fallback_error:
                    logger.warning(
                        "bugcrowd_public_api_unavailable",
                        extra={"source": self.SOURCE, "error": str(fallback_error), "url": self.FALLBACK_BASE},
                    )
                    return []
        samples: list[IngestedSample] = []
        for engagement in engagements:
            name = str(engagement.get("name", "")).strip()
            tagline = str(engagement.get("tagline", "")).strip()
            raw_text = " ".join(part for part in (name, tagline) if part).strip()
            if not raw_text:
                continue
            program_url = str(
                engagement.get("briefUrl")
                or engagement.get("program_url")
                or engagement.get("url")
                or ""
            ).strip()
            if program_url and not program_url.startswith("http"):
                program_url = f"https://bugcrowd.com{program_url}"
            samples.append(
                make_sample(
                    source=self.SOURCE,
                    raw_text=raw_text,
                    url=program_url,
                    cve_id="",
                    severity="INFO",
                    tags=("bug_bounty", "bugcrowd"),
                )
            )
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
