"""GitHub public advisory adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.github_advisory")


class GitHubAdvisoryAdapter(BaseAdapter):
    SOURCE = "github_advisory"
    BASE = "https://api.github.com/advisories"

    @staticmethod
    def _extract_next_link(link_header: str) -> str | None:
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    async def fetch(self) -> list[IngestedSample]:
        samples: list[IngestedSample] = []
        next_url: str | None = self.BASE
        page_number = 0
        lookback_days = int(os.environ.get("YGB_GITHUB_ADVISORY_LOOKBACK_DAYS", "30"))
        max_pages = int(os.environ.get("YGB_GITHUB_ADVISORY_MAX_PAGES", "3"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        timeout = aiohttp.ClientTimeout(total=120, connect=20)
        headers = {"Accept": "application/vnd.github+json"}
        github_token = os.environ.get("GITHUB_TOKEN", "").strip()
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while next_url and page_number < max_pages:
                params = {"per_page": 50, "type": "reviewed"} if page_number == 0 else None
                payload = await self._get(
                    session,
                    next_url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                advisories = payload if isinstance(payload, list) else []
                reached_cutoff = False
                for advisory in advisories:
                    published_at = self._parse_timestamp(advisory.get("published_at"))
                    if published_at is not None and published_at < cutoff:
                        reached_cutoff = True
                        break
                    raw_text = f"{advisory.get('summary', '')} {advisory.get('description', '')}".strip()
                    if not raw_text:
                        continue
                    cwes = tuple(item.get("cwe_id", "") for item in advisory.get("cwes", []) if item.get("cwe_id"))
                    samples.append(
                        make_sample(
                            source=self.SOURCE,
                            raw_text=raw_text,
                            url=advisory.get("html_url", ""),
                            cve_id=advisory.get("cve_id", "") or "",
                            severity=advisory.get("severity", "UNKNOWN"),
                            tags=cwes,
                        )
                    )
                if reached_cutoff:
                    break
                next_url = self._extract_next_link(self._last_response_headers.get("Link", ""))
                page_number += 1
                remaining = self._last_response_headers.get("X-RateLimit-Remaining", "")
                reset = self._last_response_headers.get("X-RateLimit-Reset", "")
                if next_url and remaining.isdigit() and int(remaining) < 10:
                    sleep_seconds = max(int(reset) - int(time.time()), 1) if reset.isdigit() else 60
                    await asyncio.sleep(sleep_seconds)
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
