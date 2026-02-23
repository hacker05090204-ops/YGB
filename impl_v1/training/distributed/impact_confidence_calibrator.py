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

    # ═══════════════════════════════════════════════════════════════════
    # CVSS v3.1 Vector Generation
    # ═══════════════════════════════════════════════════════════════════

    def generate_cvss_vector(
        self,
        attack_vector: str = "NETWORK",       # NETWORK / ADJACENT / LOCAL / PHYSICAL
        attack_complexity: str = "LOW",         # LOW / HIGH
        privileges_required: str = "NONE",      # NONE / LOW / HIGH
        user_interaction: str = "NONE",         # NONE / REQUIRED
        scope: str = "UNCHANGED",               # UNCHANGED / CHANGED
        conf_impact: str = "HIGH",              # NONE / LOW / HIGH
        integ_impact: str = "HIGH",             # NONE / LOW / HIGH
        avail_impact: str = "NONE",             # NONE / LOW / HIGH
    ) -> tuple:
        """Generate CVSS v3.1 vector string and base score.

        Returns:
            (vector_string, base_score)
        """
        vector = (
            f"CVSS:3.1/AV:{attack_vector[0]}/AC:{attack_complexity[0]}/"
            f"PR:{privileges_required[0]}/UI:{user_interaction[0]}/"
            f"S:{scope[0]}/C:{conf_impact[0]}/I:{integ_impact[0]}/"
            f"A:{avail_impact[0]}"
        )

        # Simplified CVSS scoring
        av_scores = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
        ac_scores = {"L": 0.77, "H": 0.44}
        pr_scores = {"N": 0.85, "L": 0.62, "H": 0.27}
        ui_scores = {"N": 0.85, "R": 0.62}
        impact_scores = {"N": 0.0, "L": 0.22, "H": 0.56}

        exploitability = (
            8.22
            * av_scores.get(attack_vector[0], 0.85)
            * ac_scores.get(attack_complexity[0], 0.77)
            * pr_scores.get(privileges_required[0], 0.85)
            * ui_scores.get(user_interaction[0], 0.85)
        )

        isc_base = 1.0 - (
            (1.0 - impact_scores.get(conf_impact[0], 0.56))
            * (1.0 - impact_scores.get(integ_impact[0], 0.56))
            * (1.0 - impact_scores.get(avail_impact[0], 0.0))
        )

        if scope[0] == "U":
            impact = 6.42 * isc_base
        else:
            impact = 7.52 * (isc_base - 0.029) - 3.25 * ((isc_base - 0.02) ** 15)

        if impact <= 0:
            base_score = 0.0
        elif scope[0] == "U":
            base_score = min(exploitability + impact, 10.0)
        else:
            base_score = min(1.08 * (exploitability + impact), 10.0)

        # Round up to 1 decimal
        base_score = round(min(base_score, 10.0), 1)

        logger.info(f"[CALIBRATOR] CVSS {vector} = {base_score}")
        return vector, base_score

    # ═══════════════════════════════════════════════════════════════════
    # Historical Triager Bias Adjustment
    # ═══════════════════════════════════════════════════════════════════

    def __init_triager_bias(self):
        """Lazy-init triager bias tracking."""
        if not hasattr(self, "_triager_history"):
            self._triager_history: Dict[str, Dict[str, int]] = {}

    def record_triager_decision(
        self, severity: str, accepted: bool
    ):
        """Record a triager accept/reject decision for bias tracking."""
        self.__init_triager_bias()
        if severity not in self._triager_history:
            self._triager_history[severity] = {"accepted": 0, "rejected": 0}
        key = "accepted" if accepted else "rejected"
        self._triager_history[severity][key] += 1

    def get_triager_bias(self) -> Dict[str, float]:
        """Get accept rate per severity level.

        Returns dict of severity -> accept_rate (0.0-1.0)
        """
        self.__init_triager_bias()
        bias = {}
        for sev, counts in self._triager_history.items():
            total = counts["accepted"] + counts["rejected"]
            bias[sev] = counts["accepted"] / total if total > 0 else 0.5
        return bias

    def calibrate_with_bias(
        self,
        raw_confidence: float,
        exploit_delta: float,
        privilege_escalation: bool = False,
        data_exposure: bool = False,
    ) -> CalibratedImpact:
        """Calibrate with triager bias adjustment.

        If a severity level has a low accept rate, we boost confidence
        to compensate (stricter threshold needed for submission).
        """
        result = self.calibrate(
            raw_confidence, exploit_delta,
            privilege_escalation, data_exposure
        )

        # Apply triager bias
        bias = self.get_triager_bias()
        if result.severity in bias:
            accept_rate = bias[result.severity]
            if accept_rate < 0.5:
                # Triagers reject this severity often — raise bar
                penalty = 1.0 - accept_rate  # e.g., 0.3 accept → 0.7 penalty
                adjusted = result.calibrated_confidence * (1.0 - penalty * 0.2)
                result = CalibratedImpact(
                    raw_confidence=result.raw_confidence,
                    calibrated_confidence=round(adjusted, 4),
                    severity=result.severity,
                    cvss_estimate=result.cvss_estimate,
                    exploit_delta=result.exploit_delta,
                    reliable=result.reliable and adjusted >= 0.5,
                )
                logger.info(
                    f"[CALIBRATOR] Triager bias adjustment: "
                    f"{result.severity} accept_rate={accept_rate:.2f} "
                    f"adjusted_conf={adjusted:.4f}"
                )

        return result

    # ═══════════════════════════════════════════════════════════════════
    # Program-Specific Severity Heuristic
    # ═══════════════════════════════════════════════════════════════════

    def __init_program_profiles(self):
        """Lazy-init program profiles."""
        if not hasattr(self, "_program_profiles"):
            self._program_profiles: Dict[str, Dict] = {}

    def register_program(
        self,
        program_id: str,
        avg_severity: str = "MEDIUM",
        payout_multiplier: float = 1.0,
        historical_accept_rate: float = 0.5,
    ):
        """Register program-specific heuristics."""
        self.__init_program_profiles()
        self._program_profiles[program_id] = {
            "avg_severity": avg_severity,
            "payout_multiplier": payout_multiplier,
            "accept_rate": historical_accept_rate,
        }

    def calibrate_for_program(
        self,
        program_id: str,
        raw_confidence: float,
        exploit_delta: float,
        privilege_escalation: bool = False,
        data_exposure: bool = False,
    ) -> CalibratedImpact:
        """Calibrate with program-specific heuristic."""
        self.__init_program_profiles()

        result = self.calibrate(
            raw_confidence, exploit_delta,
            privilege_escalation, data_exposure
        )

        profile = self._program_profiles.get(program_id)
        if profile:
            # Multiply confidence by payout_multiplier
            adjusted = min(
                result.calibrated_confidence * profile["payout_multiplier"],
                1.0
            )
            # Adjust based on program accept rate
            if profile["accept_rate"] < 0.4:
                adjusted *= 0.85  # Conservative for picky programs

            result = CalibratedImpact(
                raw_confidence=result.raw_confidence,
                calibrated_confidence=round(adjusted, 4),
                severity=result.severity,
                cvss_estimate=result.cvss_estimate,
                exploit_delta=result.exploit_delta,
                reliable=result.reliable,
            )
            logger.info(
                f"[CALIBRATOR] Program {program_id}: "
                f"multiplier={profile['payout_multiplier']} "
                f"accept={profile['accept_rate']:.2f} "
                f"adjusted={adjusted:.4f}"
            )

        return result
