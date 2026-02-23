"""
data_source_scoring.py — Data Source Scoring (Phase 5)

Each dataset tagged with:
- Source reliability score (0-1)
- Manual validation weight (0-1)
- Exploit realism score (0-1)

Low-score sources require stronger semantic gate.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

RELIABILITY_THRESHOLD = 0.5
REALISM_THRESHOLD = 0.4


@dataclass
class DataSourceScore:
    """Scores for a data source."""
    source_id: str
    field_name: str
    reliability: float      # 0-1
    manual_validation: float # 0-1
    exploit_realism: float   # 0-1
    composite_score: float = 0.0
    trusted: bool = True


@dataclass
class SourceGateResult:
    """Result of source quality gating."""
    source_id: str
    composite_score: float
    requires_stronger_gate: bool
    reason: str


class DataSourceScorer:
    """Scores and gates data sources.

    Composite = 0.4*reliability + 0.3*manual + 0.3*realism
    If composite < 0.5 → require stronger semantic gate.
    """

    def __init__(
        self,
        reliability_min: float = RELIABILITY_THRESHOLD,
        realism_min: float = REALISM_THRESHOLD,
    ):
        self.reliability_min = reliability_min
        self.realism_min = realism_min
        self._sources: Dict[str, DataSourceScore] = {}

    def register_source(
        self,
        source_id: str,
        field_name: str,
        reliability: float,
        manual_validation: float,
        exploit_realism: float,
    ) -> DataSourceScore:
        """Register and score a data source."""
        composite = round(
            0.4 * reliability + 0.3 * manual_validation + 0.3 * exploit_realism,
            4,
        )
        trusted = (
            reliability >= self.reliability_min
            and exploit_realism >= self.realism_min
            and composite >= 0.5
        )

        score = DataSourceScore(
            source_id=source_id,
            field_name=field_name,
            reliability=reliability,
            manual_validation=manual_validation,
            exploit_realism=exploit_realism,
            composite_score=composite,
            trusted=trusted,
        )
        self._sources[source_id] = score

        icon = "✓" if trusted else "⚠"
        logger.info(
            f"[SOURCE] {icon} {source_id}: "
            f"composite={composite:.2f} trusted={trusted}"
        )
        return score

    def gate_check(self, source_id: str) -> SourceGateResult:
        """Check if source needs stronger semantic gate."""
        score = self._sources.get(source_id)
        if score is None:
            return SourceGateResult(
                source_id=source_id,
                composite_score=0.0,
                requires_stronger_gate=True,
                reason="Unknown source — requires strongest gate",
            )

        stronger = not score.trusted

        return SourceGateResult(
            source_id=source_id,
            composite_score=score.composite_score,
            requires_stronger_gate=stronger,
            reason=(
                "Trusted source — standard gate" if not stronger
                else f"Low score ({score.composite_score:.2f}) — stronger gate required"
            ),
        )

    def get_source(self, source_id: str) -> Optional[DataSourceScore]:
        return self._sources.get(source_id)

    def get_untrusted(self) -> List[DataSourceScore]:
        return [s for s in self._sources.values() if not s.trusted]

    @property
    def source_count(self) -> int:
        return len(self._sources)
