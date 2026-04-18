"""Pure Python HTTP engine for the hunter agent.
No external scanning tools. Only requests/httpx.
Handles: sessions, cookies, auth, redirects,
rate limiting, proxy support, timing analysis.
All requests logged as evidence. All controlled by governance."""

import asyncio
import hashlib
import json
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("ygb.hunter.http")


@dataclass
class HTTPRequest:
    method: str
    url: str
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    body: Optional[str] = None
    timeout: float = 15.0
    allow_redirects: bool = True
    is_payload_request: bool = False  # True → requires governance approval


@dataclass
class HTTPResponse:
    status_code: int
    headers: dict
    body: str
    url: str
    elapsed_ms: float
    redirects: list[str]
    request_id: str
    evidence_path: Optional[str]
    content_type: str
    content_length: int
    has_error_message: bool
    server_header: str
    cookies: dict

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type.lower()

    @property
    def is_html(self) -> bool:
        return "html" in self.content_type.lower()

    def json_data(self) -> Optional[dict]:
        try:
            return json.loads(self.body)
        except Exception:
            return None

    def contains(self, pattern: str, case_sensitive: bool = False) -> bool:
        text = self.body if case_sensitive else self.body.lower()
        pat = pattern if case_sensitive else pattern.lower()
        return pat in text

    def diff_from(self, other: "HTTPResponse") -> dict:
        """Find differences between two responses — for blind injection detection."""
        return {
            "status_diff": self.status_code != other.status_code,
            "length_diff": abs(self.content_length - other.content_length),
            "timing_diff_ms": abs(self.elapsed_ms - other.elapsed_ms),
            "body_changed": self.body != other.body,
            "new_errors": (self.has_error_message and not other.has_error_message),
        }


class RateLimiter:
    """Per-domain rate limiter — polite and safe."""

    def __init__(self):
        self._last_request: dict[str, float] = {}
        self._request_counts: dict[str, int] = {}
        self._max_per_minute: dict[str, int] = {}

    def set_limit(self, domain: str, max_per_minute: int = 20):
        self._max_per_minute[domain] = max_per_minute

    async def wait(self, domain: str):
        limit = self._max_per_minute.get(domain, 20)
        delay = 60.0 / limit  # seconds between requests
        last = self._last_request.get(domain, 0)
        wait_time = delay - (time.monotonic() - last)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last_request[domain] = time.monotonic()
        self._request_counts[domain] = self._request_counts.get(domain, 0) + 1

    def get_count(self, domain: str) -> int:
        return self._request_counts.get(domain, 0)


class SmartHTTPEngine:
    """The hunter's HTTP client.
    Makes intelligent requests, captures evidence, enforces rate limits.
    All payload requests require governance approval before sending."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(self, session_id: str = None, max_rps: int = 20):
        self._session_id = session_id or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self._rate_limiter = RateLimiter()
        self._session_cookies: dict = {}
        self._default_headers = {
            "User-Agent": self.USER_AGENTS[0],
            "Accept": "text/html,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        self._request_count = 0
        self._evidence_dir = Path("data/ssd/evidence/http")
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        self._client: Optional[httpx.AsyncClient] = None
        self._default_max_rps = max_rps

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                verify=True,  # always verify TLS
            )
        return self._client

    async def send(self, req: HTTPRequest, approved: bool = False) -> HTTPResponse:
        """Send one HTTP request.
        If is_payload_request=True and approved=False → raises GovernanceError."""
        if req.is_payload_request and not approved:
            from backend.governance.kill_switch import GovernanceError

            raise GovernanceError(
                "Payload request requires human approval. "
                "Call request_approval() before send()."
            )

        # Kill switch check
        from backend.governance.kill_switch import check_or_raise

        check_or_raise()

        domain = urllib.parse.urlparse(req.url).netloc
        self._rate_limiter.set_limit(domain, self._default_max_rps)
        await self._rate_limiter.wait(domain)

        client = await self._get_client()
        headers = {**self._default_headers, **req.headers}
        if self._session_cookies:
            headers["Cookie"] = "; ".join(
                f"{k}={v}" for k, v in self._session_cookies.items()
            )

        redirect_history = []
        t_start = time.perf_counter()
        req_id = hashlib.sha256(
            f"{req.method}{req.url}{time.time()}".encode()
        ).hexdigest()[:12]

        try:
            response = await client.request(
                method=req.method.upper(),
                url=req.url,
                headers=headers,
                params=req.params or None,
                content=req.body.encode() if req.body else None,
                follow_redirects=req.allow_redirects,
            )
            elapsed_ms = (time.perf_counter() - t_start) * 1000

            # Track redirects
            for hist in response.history:
                redirect_history.append(str(hist.url))

            # Update session cookies
            self._session_cookies.update(dict(response.cookies))

            body_text = ""
            try:
                body_text = response.text
            except Exception:
                body_text = response.content.decode("utf-8", errors="replace")

            has_error = self._detect_error_message(body_text, response.status_code)

            # Save evidence
            evidence_path = self._save_evidence(req_id, req, response, body_text)

            self._request_count += 1
            logger.debug(
                "HTTP %s %s → %d (%.0fms)",
                req.method,
                req.url,
                response.status_code,
                elapsed_ms,
            )

            return HTTPResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=body_text[:50000],  # cap at 50KB
                url=str(response.url),
                elapsed_ms=round(elapsed_ms, 2),
                redirects=redirect_history,
                request_id=req_id,
                evidence_path=str(evidence_path),
                content_type=response.headers.get("content-type", ""),
                content_length=len(body_text),
                has_error_message=has_error,
                server_header=response.headers.get("server", ""),
                cookies=dict(response.cookies),
            )

        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - t_start) * 1000
            logger.warning("HTTP timeout: %s after %.0fms", req.url, elapsed_ms)
            raise TimeoutError(
                f"Request timed out after {elapsed_ms:.0f}ms: {req.url}"
            )
        except httpx.ConnectError as e:
            raise ConnectionError(f"Cannot connect to {req.url}: {e}")

    def _detect_error_message(self, body: str, status: int) -> bool:
        """Detect SQL errors, stack traces, server errors in response."""
        ERROR_PATTERNS = [
            "sql syntax",
            "mysql_fetch",
            "ora-01756",
            "unclosed quotation",
            "sqlite3.operationalerror",
            "pg::syntaxerror",
            "stack trace",
            "traceback (most recent call last)",
            "exception in thread",
            "internal server error",
            "warning: mysql",
            "you have an error in your sql",
            "sqlexception",
            "sqlstate",
            "jdbc",
        ]
        body_lower = body.lower()
        return status >= 500 or any(p in body_lower for p in ERROR_PATTERNS)

    def _save_evidence(
        self, req_id: str, req: HTTPRequest, resp, body: str
    ) -> Path:
        """Save request+response as evidence."""
        evidence = {
            "request_id": req_id,
            "session_id": self._session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "request": {
                "method": req.method,
                "url": req.url,
                "headers": req.headers,
                "body": req.body,
                "is_payload": req.is_payload_request,
            },
            "response": {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body_preview": body[:2000],
                "content_length": len(body),
            },
        }
        path = self._evidence_dir / f"{req_id}.json"
        path.write_text(json.dumps(evidence, indent=2))
        return path

    async def get(self, url: str, **kwargs) -> HTTPResponse:
        return await self.send(HTTPRequest("GET", url, **kwargs))

    async def post(
        self,
        url: str,
        body: str = None,
        headers: dict = None,
        approved: bool = False,
        is_payload: bool = False,
    ) -> HTTPResponse:
        return await self.send(
            HTTPRequest(
                "POST", url, headers=headers or {}, body=body, is_payload_request=is_payload
            ),
            approved=approved,
        )

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def get_stats(self) -> dict:
        return {
            "session_id": self._session_id,
            "total_requests": self._request_count,
            "cookies_collected": len(self._session_cookies),
        }
