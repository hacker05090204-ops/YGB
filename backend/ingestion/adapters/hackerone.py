"""HackerOne public disclosure adapter."""

from __future__ import annotations

import logging

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.hackerone")


class HackerOneAdapter(BaseAdapter):
    SOURCE = "hackerone"
    ENDPOINT = "https://hackerone.com/graphql"
    QUERY = """
      query ($cursor: String) { opportunities(first: 100, after: $cursor) {
        nodes { title description severity { rating } disclosedAt url }
        pageInfo { hasNextPage endCursor }
      }}
    """
    _SEVERITY_MAP = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "none": "INFO",
        "informational": "INFO",
    }

    async def fetch(self) -> list[IngestedSample]:
        samples: list[IngestedSample] = []
        cursor: str | None = None
        async with aiohttp.ClientSession() as session:
            while len(samples) < 1000:
                payload = await self._get(
                    session,
                    self.ENDPOINT,
                    method="POST",
                    json={"query": self.QUERY, "variables": {"cursor": cursor}},
                    headers={"Content-Type": "application/json"},
                )
                opportunity_root = payload.get("data", {}).get("opportunities", {})
                nodes = opportunity_root.get("nodes", [])
                for node in nodes:
                    raw_text = f"{node.get('title', '')} {node.get('description', '')}".strip()
                    if not raw_text:
                        continue
                    rating = str(node.get("severity", {}).get("rating", "info")).lower()
                    samples.append(
                        make_sample(
                            source=self.SOURCE,
                            raw_text=raw_text,
                            url=node.get("url", ""),
                            cve_id="",
                            severity=self._SEVERITY_MAP.get(rating, "INFO"),
                            tags=("bug_bounty", "hackerone"),
                        )
                    )
                    if len(samples) >= 1000:
                        break
                page_info = opportunity_root.get("pageInfo", {})
                if not page_info.get("hasNextPage") or not nodes:
                    break
                cursor = page_info.get("endCursor")
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
