"""Bugcrowd public programs adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample

logger = logging.getLogger("ygb.ingestion.adapters.bugcrowd")


@dataclass(frozen=True)
class BugcrowdFeedResult:
    fetched_at: str
    source: str
    samples_fetched: int
    available: bool
    failure_reason: str | None = None

    @classmethod
    def from_samples(
        cls,
        *,
        fetched_at: str,
        source: str,
        available: bool,
        failure_reason: str | None = None,
        samples: list[IngestedSample] | tuple[IngestedSample, ...] = (),
    ) -> "BugcrowdFeedResult":
        result = cls(
            fetched_at=fetched_at,
            source=source,
            samples_fetched=len(samples),
            available=available,
            failure_reason=failure_reason,
        )
        object.__setattr__(result, "_samples", tuple(samples))
        return result

    def __iter__(self):
        return iter(getattr(self, "_samples", ()))

    def __len__(self) -> int:
        return len(getattr(self, "_samples", ()))

    def __getitem__(self, index: int) -> IngestedSample:
        return getattr(self, "_samples", ())[index]


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

    @staticmethod
    def _extract_entries(
        payload: dict[str, object] | list[object] | str,
        payload_key: str,
    ) -> list[object]:
        if isinstance(payload, dict):
            items = payload.get(payload_key, [])
            return items if isinstance(items, list) else []
        if isinstance(payload, list):
            return payload
        return []

    async def fetch(self) -> BugcrowdFeedResult:
        fetched_at = datetime.now(timezone.utc).isoformat()
        timeout = aiohttp.ClientTimeout(total=60, connect=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    payload = await self._get(
                        session,
                        self.BASE,
                        params=self.PARAMS,
                        timeout=timeout,
                    )
                    engagements = self._extract_entries(payload, "engagements")
                except Exception as primary_error:
                    logger.warning(
                        "bugcrowd_engagements_unavailable",
                        extra={
                            "source": self.SOURCE,
                            "error": str(primary_error),
                            "url": self.BASE,
                        },
                    )
                    try:
                        payload = await self._get(
                            session,
                            self.FALLBACK_BASE,
                            timeout=timeout,
                        )
                        engagements = self._extract_entries(payload, "disclosures")
                    except Exception as fallback_error:
                        failure_reason = (
                            f"primary={type(primary_error).__name__}: {primary_error}; "
                            f"fallback={type(fallback_error).__name__}: {fallback_error}"
                        )
                        logger.warning(
                            "bugcrowd_public_api_unavailable",
                            extra={
                                "source": self.SOURCE,
                                "error": str(fallback_error),
                                "url": self.FALLBACK_BASE,
                            },
                        )
                        return BugcrowdFeedResult.from_samples(
                            fetched_at=fetched_at,
                            source=self.SOURCE,
                            available=False,
                            failure_reason=failure_reason,
                        )
        except Exception as session_error:
            failure_reason = f"session={type(session_error).__name__}: {session_error}"
            logger.warning(
                "bugcrowd_session_unavailable",
                extra={
                    "source": self.SOURCE,
                    "error": str(session_error),
                    "url": self.BASE,
                },
            )
            return BugcrowdFeedResult.from_samples(
                fetched_at=fetched_at,
                source=self.SOURCE,
                available=False,
                failure_reason=failure_reason,
            )

        samples: list[IngestedSample] = []
        for engagement in engagements:
            if not isinstance(engagement, dict):
                continue
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
        return BugcrowdFeedResult.from_samples(
            fetched_at=fetched_at,
            source=self.SOURCE,
            available=True,
            failure_reason=None,
            samples=samples,
        )


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
