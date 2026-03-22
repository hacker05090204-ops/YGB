"""Adapter base class with safety and rate-limiting controls."""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from aiolimiter import AsyncLimiter

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.models import IngestedSample
from backend.observability.metrics import metrics_registry
from impl_v1.phase49.governors.g38_self_trained_model import can_ai_use_network

logger = logging.getLogger("ygb.ingestion.base_adapter")
USER_AGENT = "YGB-Research-Bot/1.0"


class BaseAdapter(abc.ABC):
    SOURCE = "base"
    _robots_cache: "OrderedDict[str, RobotFileParser]" = OrderedDict()
    _domain_limiters: "OrderedDict[str, AsyncLimiter]" = OrderedDict()

    def __init__(self, semaphore: asyncio.Semaphore, limiter: AsyncLimiter) -> None:
        self.semaphore = semaphore
        self.limiter = limiter
        self._last_response_headers: dict[str, str] = {}

    @abc.abstractmethod
    async def fetch(self) -> list[IngestedSample]:
        """Fetch samples from a source."""

    @classmethod
    def _metric_key(cls, value: str) -> str:
        return "".join(character if character.isalnum() else "_" for character in value.lower())

    @classmethod
    def _get_domain_limiter(cls, domain: str) -> AsyncLimiter:
        cached = cls._domain_limiters.get(domain)
        if cached is not None:
            cls._domain_limiters.move_to_end(domain)
            return cached
        limiter = AsyncLimiter(2, 1)
        cls._domain_limiters[domain] = limiter
        if len(cls._domain_limiters) > 100:
            cls._domain_limiters.popitem(last=False)
        return limiter

    async def _perform_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        **kwargs: Any,
    ) -> tuple[int, str, dict[str, str]]:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        headers.update(kwargs.pop("headers", {}) or {})
        method = kwargs.pop("method", "GET")
        timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=30))

        async with self.semaphore:
            async with self.limiter:
                async with self._get_domain_limiter(domain):
                    start = time.perf_counter()
                    async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                        body = await response.text()
                        response_headers = dict(response.headers)
                        status = response.status
                    latency_ms = (time.perf_counter() - start) * 1000

        metrics_registry.increment("ingest_http_requests_total")
        metrics_registry.increment(f"ingest_http_requests_total_{self._metric_key(domain)}")
        logger.info(
            "ingest_http_request",
            extra={
                "event": "ingest_http_request",
                "domain": domain,
                "status_code": status,
                "latency_ms": round(latency_ms, 2),
            },
        )
        return status, body, response_headers

    async def _get_robot_parser(self, session: aiohttp.ClientSession, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        cached = self._robots_cache.get(domain)
        if cached is not None:
            self._robots_cache.move_to_end(domain)
            return cached

        robots_url = f"{parsed.scheme or 'https'}://{domain}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        status, body, _ = await self._perform_request(
            session,
            robots_url,
            headers={"Accept": "text/plain"},
        )
        parser.parse(body.splitlines() if status < 400 else [])
        self._robots_cache[domain] = parser
        if len(self._robots_cache) > 100:
            self._robots_cache.popitem(last=False)
        return parser

    async def _robots_allowed(self, session: aiohttp.ClientSession, url: str) -> bool:
        parser = await self._get_robot_parser(session, url)
        return parser.can_fetch(USER_AGENT, url)

    @staticmethod
    def _decode_body(body: str, content_type: str) -> dict[str, Any] | list[Any] | str:
        stripped = body.strip()
        if "json" in content_type.lower() or stripped.startswith("{") or stripped.startswith("["):
            return json.loads(body)
        return body

    async def _get(self, session: aiohttp.ClientSession, url: str, **kwargs: Any) -> dict[str, Any] | list[Any] | str:
        if can_ai_use_network()[0]:
            raise RuntimeError("GUARD")
        if not await self._robots_allowed(session, url):
            raise PermissionError(f"robots.txt disallowed: {url}")

        rate_limit_retries = 0
        server_error_retried = False
        while True:
            status, body, headers = await self._perform_request(session, url, **kwargs)
            self._last_response_headers = headers
            if status == 429 and rate_limit_retries < 3:
                rate_limit_retries += 1
                await asyncio.sleep(2 ** rate_limit_retries)
                continue
            if 500 <= status <= 599 and not server_error_retried:
                server_error_retried = True
                await asyncio.sleep(5)
                continue
            if status >= 400:
                raise RuntimeError(f"HTTP {status} for {url}")
            return self._decode_body(body, headers.get("Content-Type", ""))


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
