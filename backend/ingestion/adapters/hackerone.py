"""HackerOne public program directory adapter."""

from __future__ import annotations

import logging
import re
from html import unescape

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.hackerone")


class HackerOneAdapter(BaseAdapter):
    SOURCE = "hackerone"
    DIRECTORY_URL = "https://www.hackerone.com/bug-bounty-programs"
    _CARD_PATTERN = re.compile(
        r'<a\s+href="(?P<href>https://hackerone\.com/[^"]+)"[^>]*data-item-name="(?P<name>[^"]+)"[^>]*class="[^"]*bug-bounty-list-item[^"]*"[^>]*>(?P<body>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    _POLICY_PATTERN = re.compile(
        r'<div class="bug-bounty-list-item-policy[^"]*">(?P<text>.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    _META_PATTERN = re.compile(
        r'<span class="bug-bounty-list-item-meta-item[^"]*">(?P<text>.*?)</span>',
        re.IGNORECASE | re.DOTALL,
    )

    @staticmethod
    def _clean_text(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    async def fetch(self) -> list[IngestedSample]:
        timeout = aiohttp.ClientTimeout(total=60, connect=30)
        headers = {"Accept": "text/html,application/xhtml+xml"}
        samples: list[IngestedSample] = []
        seen_urls: set[str] = set()
        async with aiohttp.ClientSession(timeout=timeout) as session:
            payload = await self._get(
                session,
                self.DIRECTORY_URL,
                headers=headers,
                timeout=timeout,
            )
        if not isinstance(payload, str):
            logger.warning("hackerone_directory_non_html", extra={"source": self.SOURCE})
            return []

        for match in self._CARD_PATTERN.finditer(payload):
            url = match.group("href").strip()
            if url in seen_urls:
                continue
            seen_urls.add(url)
            name = self._clean_text(match.group("name"))
            body = match.group("body")
            meta = " ".join(
                cleaned
                for cleaned in (self._clean_text(item.group("text")) for item in self._META_PATTERN.finditer(body))
                if cleaned
            )
            policy_match = self._POLICY_PATTERN.search(body)
            policy = self._clean_text(policy_match.group("text")) if policy_match else ""
            raw_text = " ".join(part for part in (name, meta, policy) if part).strip()
            if len(raw_text) < 20:
                continue
            samples.append(
                make_sample(
                    source=self.SOURCE,
                    raw_text=raw_text[:512],
                    url=url,
                    cve_id="",
                    severity="INFO",
                    tags=("bug_bounty", "hackerone", "program"),
                )
            )
        if not samples:
            logger.warning("hackerone_directory_empty", extra={"source": self.SOURCE, "url": self.DIRECTORY_URL})
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
