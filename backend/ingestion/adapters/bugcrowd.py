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
    BASE = "https://bugcrowd.com/programs.json"

    @staticmethod
    def _target_group_text(program: dict[str, object]) -> str:
        groups = program.get("target_groups", [])
        if isinstance(groups, dict):
            groups = [groups]
        return " ".join(str(group.get("description", "")).strip() for group in groups if group.get("description"))

    async def fetch(self) -> list[IngestedSample]:
        async with aiohttp.ClientSession() as session:
            payload = await self._get(session, self.BASE)
        programs = payload.get("programs", payload if isinstance(payload, list) else [])
        samples: list[IngestedSample] = []
        for program in programs:
            raw_text = f"{program.get('name', '')} {program.get('tagline', '')} {self._target_group_text(program)}".strip()
            if not raw_text:
                continue
            program_url = str(program.get("program_url", ""))
            samples.append(
                make_sample(
                    source=self.SOURCE,
                    raw_text=raw_text,
                    url=f"https://bugcrowd.com{program_url}",
                    cve_id="",
                    severity="INFO",
                    tags=("bug_bounty", "bugcrowd"),
                )
            )
        return samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
