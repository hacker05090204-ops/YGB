"""
live_feedback_collector.py — Live Feedback Loop (Phase 3)

Captures: true positive, false positive, rejected, accepted.
Stores outcome linked to feature vector.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEntry:
    """A single feedback entry from real hunting."""
    entry_id: str
    field_name: str
    outcome: str            # true_positive / false_positive / rejected / accepted
    confidence: float
    feature_hash: str
    exploit_type: str = ""
    timestamp: str = ""


@dataclass
class FeedbackStats:
    """Aggregated feedback statistics."""
    total: int
    true_positives: int
    false_positives: int
    rejected: int
    accepted: int
    precision: float
    fpr: float


class LiveFeedbackCollector:
    """Collects real-world hunting feedback.

    Stores outcomes linked to feature vectors for reinforcement.
    """

    def __init__(self):
        self._entries: List[FeedbackEntry] = []

    def record(
        self,
        entry_id: str,
        field_name: str,
        outcome: str,
        confidence: float,
        feature_hash: str,
        exploit_type: str = "",
    ):
        """Record a feedback entry."""
        entry = FeedbackEntry(
            entry_id=entry_id,
            field_name=field_name,
            outcome=outcome,
            confidence=confidence,
            feature_hash=feature_hash,
            exploit_type=exploit_type,
            timestamp=datetime.now().isoformat(),
        )
        self._entries.append(entry)
        logger.info(
            f"[FEEDBACK] {outcome}: {field_name} "
            f"conf={confidence:.2f} id={entry_id[:12]}"
        )

    def get_stats(self, field_name: Optional[str] = None) -> FeedbackStats:
        """Get aggregated stats, optionally filtered by field."""
        entries = self._entries
        if field_name:
            entries = [e for e in entries if e.field_name == field_name]

        tp = sum(1 for e in entries if e.outcome == "true_positive")
        fp = sum(1 for e in entries if e.outcome == "false_positive")
        rej = sum(1 for e in entries if e.outcome == "rejected")
        acc = sum(1 for e in entries if e.outcome == "accepted")
        total = len(entries)

        precision = tp / max(tp + fp, 1)
        fpr = fp / max(fp + (total - tp - fp), 1)

        return FeedbackStats(total, tp, fp, rej, acc, round(precision, 4), round(fpr, 4))

    def get_for_reinforcement(self, field_name: Optional[str] = None) -> List[FeedbackEntry]:
        """Get entries for reinforcement learning."""
        entries = self._entries
        if field_name:
            entries = [e for e in entries if e.field_name == field_name]
        return entries

    @property
    def entry_count(self) -> int:
        return len(self._entries)
