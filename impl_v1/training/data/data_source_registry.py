"""
data_source_registry.py — Data Source Trust Registry (Phase 1)

██████████████████████████████████████████████████████████████████████
BOUNTY-READY DATA QUALITY — SOURCE TRUST SCORING
██████████████████████████████████████████████████████████████████████

Governance layer:
  - Every data source gets a 0–100 trust score
  - Only sources with trust ≥ 80 are allowed for training
  - Scores decay over time if not re-verified
  - Scores increase with successful training runs
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REGISTRY_FILE = _PROJECT_ROOT / "secure_data" / "data_source_registry.json"

TRUST_THRESHOLD = 80  # Minimum trust score to allow training
DECAY_RATE_PER_DAY = 0.5  # Trust decay per day without verification
MAX_TRUST = 100
MIN_TRUST = 0


@dataclass
class DataSource:
    """A registered data source with trust scoring."""
    source_id: str
    name: str
    source_type: str  # "INGESTION_PIPELINE", "EXTERNAL_FEED", "MANUAL_UPLOAD"
    trust_score: float = 0.0
    total_samples_provided: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    last_verified: str = ""
    last_used: str = ""
    created_at: str = ""
    hash_fingerprint: str = ""
    blocked: bool = False
    block_reason: str = ""
    tags: List[str] = field(default_factory=list)


class DataSourceRegistry:
    """
    Registry of all known data sources with trust scoring.

    Trust score rules:
      - New source starts at 0
      - Manual verification: +30
      - Successful training run: +10 (capped at 100)
      - Failed training run: -20
      - Data quality violation: -40
      - Decay: -0.5 per day since last verification
      - Blocked source: always 0
    """

    def __init__(self):
        self._sources: Dict[str, DataSource] = {}
        self._load()

    def _load(self):
        """Load registry from disk."""
        if _REGISTRY_FILE.exists():
            try:
                with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for sid, sdata in data.items():
                    self._sources[sid] = DataSource(**sdata)
            except Exception as e:
                logger.error(f"[REGISTRY] Failed to load: {e}")

    def _save(self):
        """Persist registry to disk."""
        _REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: asdict(s) for sid, s in self._sources.items()}
        with open(_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def register_source(
        self, name: str, source_type: str, tags: Optional[List[str]] = None
    ) -> DataSource:
        """Register a new data source."""
        sid = hashlib.sha256(f"{name}:{source_type}".encode()).hexdigest()[:16]
        now = datetime.now().isoformat()
        source = DataSource(
            source_id=sid,
            name=name,
            source_type=source_type,
            trust_score=0.0,
            created_at=now,
            tags=tags or [],
        )
        self._sources[sid] = source
        self._save()
        logger.info(f"[REGISTRY] Registered: {name} ({source_type}) → {sid}")
        return source

    def get_source(self, source_id: str) -> Optional[DataSource]:
        """Get a source by ID."""
        return self._sources.get(source_id)

    def verify_source(self, source_id: str) -> bool:
        """Manually verify a source. Adds +30 trust."""
        src = self._sources.get(source_id)
        if not src:
            return False
        if src.blocked:
            logger.warning(f"[REGISTRY] Cannot verify blocked source: {src.name}")
            return False
        src.trust_score = min(MAX_TRUST, src.trust_score + 30)
        src.last_verified = datetime.now().isoformat()
        self._save()
        logger.info(f"[REGISTRY] Verified: {src.name} → trust={src.trust_score:.1f}")
        return True

    def record_success(self, source_id: str):
        """Record a successful training run. +10 trust."""
        src = self._sources.get(source_id)
        if not src:
            return
        src.successful_runs += 1
        src.trust_score = min(MAX_TRUST, src.trust_score + 10)
        src.last_used = datetime.now().isoformat()
        self._save()

    def record_failure(self, source_id: str, reason: str = ""):
        """Record a failed training run. -20 trust."""
        src = self._sources.get(source_id)
        if not src:
            return
        src.failed_runs += 1
        src.trust_score = max(MIN_TRUST, src.trust_score - 20)
        src.last_used = datetime.now().isoformat()
        self._save()
        logger.warning(f"[REGISTRY] Failure recorded: {src.name} → trust={src.trust_score:.1f} ({reason})")

    def record_violation(self, source_id: str, reason: str):
        """Record a data quality violation. -40 trust."""
        src = self._sources.get(source_id)
        if not src:
            return
        src.trust_score = max(MIN_TRUST, src.trust_score - 40)
        if src.trust_score <= 0:
            src.blocked = True
            src.block_reason = reason
        self._save()
        logger.error(f"[REGISTRY] Violation: {src.name} → trust={src.trust_score:.1f} ({reason})")

    def block_source(self, source_id: str, reason: str):
        """Permanently block a source."""
        src = self._sources.get(source_id)
        if not src:
            return
        src.blocked = True
        src.block_reason = reason
        src.trust_score = 0
        self._save()
        logger.error(f"[REGISTRY] BLOCKED: {src.name} — {reason}")

    def apply_decay(self):
        """Apply daily trust decay to unverified sources."""
        now = datetime.now()
        for src in self._sources.values():
            if src.blocked or src.trust_score <= 0:
                continue
            if src.last_verified:
                last = datetime.fromisoformat(src.last_verified)
                days = (now - last).days
                if days > 0:
                    decay = days * DECAY_RATE_PER_DAY
                    src.trust_score = max(MIN_TRUST, src.trust_score - decay)
        self._save()

    def is_trusted(self, source_id: str) -> bool:
        """Check if a source meets the trust threshold."""
        src = self._sources.get(source_id)
        if not src or src.blocked:
            return False
        return src.trust_score >= TRUST_THRESHOLD

    def get_trusted_sources(self) -> List[DataSource]:
        """Get all sources with trust ≥ threshold."""
        self.apply_decay()
        return [s for s in self._sources.values()
                if not s.blocked and s.trust_score >= TRUST_THRESHOLD]

    def get_all_sources(self) -> List[DataSource]:
        """Get all registered sources."""
        return list(self._sources.values())

    def get_summary(self) -> dict:
        """Get registry summary for API/UI."""
        all_src = self.get_all_sources()
        return {
            "total_sources": len(all_src),
            "trusted_sources": sum(1 for s in all_src if not s.blocked and s.trust_score >= TRUST_THRESHOLD),
            "blocked_sources": sum(1 for s in all_src if s.blocked),
            "trust_threshold": TRUST_THRESHOLD,
            "sources": [asdict(s) for s in all_src],
        }
