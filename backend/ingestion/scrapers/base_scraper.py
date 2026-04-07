"""Shared synchronous scraping primitives for real public vulnerability sources."""

from __future__ import annotations

import abc
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.ingestion.models import normalize_severity

logger = logging.getLogger("ygb.ingestion.scrapers.base")
REAL_USER_AGENT = "YGB-Autograbber/1.0 (+https://github.com/)"


@dataclass(frozen=True)
class ScrapedSample:
    """Normalized scrape result before ingestion-model conversion."""

    source: str
    advisory_id: str
    url: str
    title: str
    description: str
    severity: str
    cve_id: str = ""
    cvss_score: float | None = None
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    published_at: str | None = None
    modified_at: str | None = None
    is_exploited: bool | None = None
    vendor: str = ""
    product: str = ""

    def render_text(self) -> str:
        parts: list[str] = []
        description_text = str(self.description or "").strip()
        title_text = str(self.title or "").strip()
        if title_text and title_text.lower() not in description_text.lower():
            parts.append(title_text)
        if self.vendor or self.product:
            parts.append(
                " ".join(
                    value
                    for value in (
                        f"Vendor: {self.vendor}." if self.vendor else "",
                        f"Product: {self.product}." if self.product else "",
                    )
                    if value
                )
            )
        if description_text:
            parts.append(description_text)
        if self.cvss_score is not None:
            parts.append(f"CVSS base score: {self.cvss_score:.1f}.")
        severity_text = normalize_severity(self.severity)
        if severity_text != "UNKNOWN":
            parts.append(f"Severity: {severity_text}.")
        if self.aliases:
            parts.append("Aliases: " + ", ".join(self.aliases[:5]) + ".")
        if self.references:
            parts.append("References: " + "; ".join(self.references[:3]) + ".")
        return " ".join(part for part in parts if part).strip()


class BaseScraper(abc.ABC):
    """Real HTTP scraper base with retries, timeout, user-agent, and polite delay."""

    SOURCE = "base"
    REQUEST_DELAY_SECONDS = 1.0
    TIMEOUT_SECONDS = 30.0
    USER_AGENT = REAL_USER_AGENT

    def __init__(
        self,
        *,
        session: Session | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if float(self.REQUEST_DELAY_SECONDS) < 1.0:
            raise ValueError(
                f"{self.__class__.__name__}.REQUEST_DELAY_SECONDS must be at least 1.0"
            )
        self.timeout_seconds = float(timeout_seconds or self.TIMEOUT_SECONDS)
        self._owns_session = session is None
        self.session = session or self._build_session()
        self._last_request_monotonic: float | None = None
        self._last_response_headers: dict[str, str] = {}

    @staticmethod
    def _build_retry() -> Retry:
        return Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )

    def _build_session(self) -> Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json, application/octet-stream;q=0.9, text/plain;q=0.8",
            }
        )
        adapter = HTTPAdapter(max_retries=self._build_retry())
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def _respect_polite_delay(self) -> None:
        if self._last_request_monotonic is None:
            return
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining_delay = float(self.REQUEST_DELAY_SECONDS) - elapsed
        if remaining_delay > 0:
            logger.debug(
                "scraper_polite_delay source=%s sleep_seconds=%.3f",
                self.SOURCE,
                remaining_delay,
            )
            time.sleep(remaining_delay)

    def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        self._respect_polite_delay()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("User-Agent", self.USER_AGENT)
        timeout = kwargs.pop("timeout", self.timeout_seconds)
        response: Response | None = None
        try:
            response = self.session.request(method=method, url=url, headers=headers, timeout=timeout, **kwargs)
            self._last_response_headers = dict(response.headers)
            response.raise_for_status()
            logger.info(
                "scraper_request_ok source=%s method=%s url=%s status=%s",
                self.SOURCE,
                method,
                url,
                response.status_code,
            )
            return response
        except requests.RequestException as exc:
            logger.error(
                "scraper_request_failed source=%s method=%s url=%s error=%s",
                self.SOURCE,
                method,
                url,
                exc,
            )
            raise
        finally:
            self._last_request_monotonic = time.monotonic()

    def _get_json(self, url: str, **kwargs: Any) -> Any:
        response = self._request("GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            preview = response.text[:200].replace("\n", " ")
            logger.error(
                "scraper_json_decode_failed source=%s url=%s preview=%s",
                self.SOURCE,
                url,
                preview,
            )
            raise ValueError(f"{self.SOURCE}: invalid JSON from {url}") from exc

    def _get_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self._request("GET", url, **kwargs).content

    @staticmethod
    def _coerce_score(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _ensure_json_object(payload: Any, *, source: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError(f"{source}: expected JSON object, got {type(payload).__name__}")
        return payload

    @staticmethod
    def _ensure_json_array(payload: Any, *, source: str) -> list[Any]:
        if not isinstance(payload, list):
            raise ValueError(f"{source}: expected JSON array, got {type(payload).__name__}")
        return payload

    @staticmethod
    def _load_json_bytes(raw_bytes: bytes, *, source: str) -> Any:
        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{source}: invalid JSON payload") from exc

    @abc.abstractmethod
    def fetch(self, max_items: int) -> list[ScrapedSample]:
        """Fetch real vulnerability entries from the upstream source."""
