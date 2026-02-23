"""
impact_confidence_calibrator.py — Impact Confidence Calibrator (Phase 0)

Map exploit delta to calibrated severity.
C-style severity binning: CRITICAL/HIGH/MEDIUM/LOW/INFO.
Isotonic-style calibration for confidence.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CalibratedImpact:
    """Calibrated impact assessment."""
    raw_confidence: float
    calibrated_confidence: float
    severity: str             # CRITICAL / HIGH / MEDIUM / LOW / INFO
    cvss_estimate: float
    exploit_delta: float
    reliable: bool


class ImpactConfidenceCalibrator:
    """Calibrates exploit confidence to severity.

    Maps raw detection delta to CVSS-compatible severity bin.
    Applies isotonic-style monotonic calibration.
    """

    SEVERITY_BINS = [
        (0.90, "CRITICAL", 9.5),
        (0.75, "HIGH", 7.5),
        (0.50, "MEDIUM", 5.0),
        (0.25, "LOW", 2.5),
        (0.00, "INFO", 0.5),
    ]

    def __init__(self, calibration_factor: float = 1.0):
        self.factor = calibration_factor
        self._history: List[CalibratedImpact] = []

    def calibrate(
        self,
        raw_confidence: float,
        exploit_delta: float,
        privilege_escalation: bool = False,
        data_exposure: bool = False,
    ) -> CalibratedImpact:
        """Calibrate raw confidence to severity."""
        # Base calibration: weighted mean of confidence and delta
        base = 0.6 * raw_confidence + 0.4 * exploit_delta

        # Boost for high-impact indicators
        if privilege_escalation:
            base = min(base * 1.3, 1.0)
        if data_exposure:
            base = min(base * 1.2, 1.0)

        # Apply calibration factor
        calibrated = min(base * self.factor, 1.0)

        # Severity binning
        severity = "INFO"
        cvss = 0.5
        for thresh, sev, cv in self.SEVERITY_BINS:
            if calibrated >= thresh:
                severity = sev
                cvss = cv
                break

        reliable = calibrated >= 0.5 and exploit_delta >= 0.3

        result = CalibratedImpact(
            raw_confidence=round(raw_confidence, 4),
            calibrated_confidence=round(calibrated, 4),
            severity=severity,
            cvss_estimate=cvss,
            exploit_delta=round(exploit_delta, 4),
            reliable=reliable,
        )
        self._history.append(result)

        logger.info(
            f"[CALIBRATOR] {severity} conf={calibrated:.4f} "
            f"delta={exploit_delta:.4f} CVSS≈{cvss}"
        )
        return result

    def batch_calibrate(
        self,
        confidences: np.ndarray,
        deltas: np.ndarray,
    ) -> List[CalibratedImpact]:
        """Calibrate a batch."""
        results = []
        for c, d in zip(confidences, deltas):
            results.append(self.calibrate(float(c), float(d)))
        return results

    @property
    def calibration_count(self) -> int:
        return len(self._history)
