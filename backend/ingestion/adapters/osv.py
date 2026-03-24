"""OSV vulnerability adapter."""

from __future__ import annotations

import io
import json
import logging
import zipfile

import aiohttp

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.models import IngestedSample, make_sample
from impl_v1.phase49.governors.g38_self_trained_model import can_ai_use_network

logger = logging.getLogger("ygb.ingestion.adapters.osv")


class OSVAdapter(BaseAdapter):
    SOURCE = "osv"
    URL = "https://osv-vulnerabilities.storage.googleapis.com/all.zip"

    @staticmethod
    def _extract_cvss_score(payload: object) -> float | None:
        scores: list[float] = []

        def visit(node: object) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if str(key).lower() in {"score", "basescore", "cvss_score"}:
                        if isinstance(value, (int, float)):
                            scores.append(float(value))
                        elif isinstance(value, str):
                            try:
                                scores.append(float(value))
                            except ValueError:
                                pass
                    visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)

        visit(payload)
        return max(scores) if scores else None

    @classmethod
    def _extract_severity(cls, entry: dict[str, object]) -> str:
        score = cls._extract_cvss_score(entry)
        if score is None:
            return "UNKNOWN"
        if score > 7:
            return "HIGH"
        if score > 4:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _extract_tags(entry: dict[str, object]) -> tuple[str, ...]:
        ecosystems: list[str] = []
        for affected in entry.get("affected", []):
            if not isinstance(affected, dict):
                continue
            package = affected.get("package", {})
            if not isinstance(package, dict):
                continue
            ecosystem = str(package.get("ecosystem", "")).strip()
            if ecosystem and ecosystem not in ecosystems:
                ecosystems.append(ecosystem)
        return tuple(ecosystems)

    @staticmethod
    def _extract_cve_id(entry: dict[str, object]) -> str:
        for alias in entry.get("aliases", []):
            alias_text = str(alias).strip()
            if alias_text.upper().startswith("CVE-"):
                return alias_text
        return ""

    @staticmethod
    def _extract_raw_text(entry: dict[str, object]) -> str:
        summary = str(entry.get("summary", "")).strip()
        details = str(entry.get("details", "")).strip()
        return f"{summary} {details}".strip()[:512]

    async def _fetch_archive_bytes(self, session: aiohttp.ClientSession) -> bytes:
        allowed = await self._robots_allowed(session, self.URL)
        if not allowed:
            logger.warning("OSV archive blocked by robots.txt: %s", self.URL)
            return b""
        blocked, reason = can_ai_use_network()
        if blocked:
            raise RuntimeError(f"Network access denied by governance: {reason}")
        async with self.semaphore:
            async with self.limiter:
                async with session.get(self.URL) as response:
                    response.raise_for_status()
                    return await response.read()

    async def fetch(self) -> list[IngestedSample]:
        timeout = aiohttp.ClientTimeout(total=600, connect=30)
        samples: list[IngestedSample] = []
        async with aiohttp.ClientSession(timeout=timeout) as session:
            archive_bytes = await self._fetch_archive_bytes(session)
        if not archive_bytes:
            return samples

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for member_name in archive.namelist():
                if not member_name.endswith(".json"):
                    continue
                with archive.open(member_name) as member:
                    entry = json.load(member)
                if not isinstance(entry, dict):
                    continue
                raw_text = self._extract_raw_text(entry)
                vulnerability_id = str(entry.get("id", "")).strip()
                if not raw_text or not vulnerability_id:
                    continue
                samples.append(
                    make_sample(
                        source=self.SOURCE,
                        raw_text=raw_text,
                        url=f"https://osv.dev/vulnerability/{vulnerability_id}",
                        cve_id=self._extract_cve_id(entry),
                        severity=self._extract_severity(entry),
                        tags=self._extract_tags(entry),
                    )
                )
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
