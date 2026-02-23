"""
data_source_registry.py — Trusted Source Registry (Phase 1)

Maintains trusted sources only.
Each source has reliability score.
Reject unknown sources automatically.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TrustedSource:
    """A trusted data source."""
    source_id: str
    source_type: str        # cve_feed / bounty / exploit_db / hunt_log
    reliability: float      # 0-1
    verified: bool = True
    sample_count: int = 0
    last_pull: str = ""
    active: bool = True


@dataclass
class SourceCheckResult:
    """Result of source check."""
    allowed: bool
    source_id: str
    reliability: float
    reason: str


class DataSourceRegistry:
    """Manages trusted data sources.

    Only registered sources accepted.
    Unknown sources auto-rejected.
    """

    def __init__(self, registry_path: str = ""):
        self._sources: Dict[str, TrustedSource] = {}
        self._path = registry_path

    def register(self, source: TrustedSource):
        """Register a trusted source."""
        self._sources[source.source_id] = source
        logger.info(
            f"[REGISTRY] Registered: {source.source_id} "
            f"type={source.source_type} reliability={source.reliability}"
        )

    def check_source(self, source_id: str) -> SourceCheckResult:
        """Check if source is trusted."""
        src = self._sources.get(source_id)
        if src is None:
            return SourceCheckResult(
                allowed=False, source_id=source_id,
                reliability=0.0, reason="Unknown source — rejected",
            )
        if not src.active:
            return SourceCheckResult(
                allowed=False, source_id=source_id,
                reliability=src.reliability, reason="Source deactivated",
            )
        if src.reliability < 0.3:
            return SourceCheckResult(
                allowed=False, source_id=source_id,
                reliability=src.reliability, reason="Reliability too low",
            )
        return SourceCheckResult(
            allowed=True, source_id=source_id,
            reliability=src.reliability, reason="Trusted source",
        )

    def record_pull(self, source_id: str, count: int):
        """Record a data pull from source."""
        if source_id in self._sources:
            self._sources[source_id].sample_count += count
            self._sources[source_id].last_pull = datetime.now().isoformat()

    def get_active_sources(self) -> List[TrustedSource]:
        return [s for s in self._sources.values() if s.active]

    @property
    def source_count(self) -> int:
        return len(self._sources)
