"""
Calibration Enforcement - Safe Training
=========================================

Every N epochs, compute and enforce:
- Accuracy
- ECE (Expected Calibration Error)
- Brier Score
- Confidence histogram

Block auto-mode if below thresholds.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import math


# =============================================================================
# CALIBRATION THRESHOLDS
# =============================================================================

@dataclass
class CalibrationThresholds:
    """Thresholds for auto-mode unlock."""
    min_accuracy: float = 0.97
    max_ece: float = 0.02
    max_brier: float = 0.03
    min_stable_epochs: int = 10
    min_checkpoints: int = 50


# =============================================================================
# CALIBRATION METRICS
# =============================================================================

@dataclass
class CalibrationMetrics:
    """Calibration metrics at a point in time."""
    epoch: int
    accuracy: float
    ece: float
    brier: float
    avg_confidence: float
    confidence_histogram: Dict[str, int]
    timestamp: str


# =============================================================================
# CALIBRATION CALCULATOR
# =============================================================================

class CalibrationCalculator:
    """Calculate calibration metrics."""
    
    @staticmethod
    def compute_accuracy(predictions: list, labels: list) -> float:
        """Compute accuracy."""
        if len(predictions) == 0:
            return 0.0
        correct = sum(1 for p, l in zip(predictions, labels) if p == l)
        return correct / len(predictions)
    
    @staticmethod
    def compute_ece(
        confidences: list,
        predictions: list,
        labels: list,
        n_bins: int = 10,
    ) -> float:
        """Compute Expected Calibration Error."""
        if len(confidences) == 0:
            return 0.0
        
        bin_boundaries = [i / n_bins for i in range(n_bins + 1)]
        ece = 0.0
        
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            
            # Find samples in this bin
            in_bin = [
                (c, p, l) for c, p, l in zip(confidences, predictions, labels)
                if bin_lower <= c < bin_upper
            ]
            
            if len(in_bin) == 0:
                continue
            
            # Calculate accuracy and avg confidence in bin
            bin_correct = sum(1 for _, p, l in in_bin if p == l)
            bin_accuracy = bin_correct / len(in_bin)
            bin_confidence = sum(c for c, _, _ in in_bin) / len(in_bin)
            
            # Add to ECE
            ece += (len(in_bin) / len(confidences)) * abs(bin_accuracy - bin_confidence)
        
        return ece
    
    @staticmethod
    def compute_brier(confidences: list, labels: list) -> float:
        """Compute Brier score."""
        if len(confidences) == 0:
            return 0.0
        
        # For binary: Brier = mean((confidence - label)^2)
        total = sum((c - l) ** 2 for c, l in zip(confidences, labels))
        return total / len(confidences)
    
    @staticmethod
    def compute_confidence_histogram(
        confidences: list,
        n_bins: int = 10,
    ) -> Dict[str, int]:
        """Compute confidence histogram."""
        histogram = {f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}": 0 for i in range(n_bins)}
        
        for c in confidences:
            bin_idx = min(int(c * n_bins), n_bins - 1)
            bin_key = f"{bin_idx/n_bins:.1f}-{(bin_idx+1)/n_bins:.1f}"
            histogram[bin_key] += 1
        
        return histogram


# =============================================================================
# CALIBRATION ENFORCER
# =============================================================================

class CalibrationEnforcer:
    """Enforce calibration requirements for auto-mode."""
    
    def __init__(self, thresholds: CalibrationThresholds = None):
        self.thresholds = thresholds or CalibrationThresholds()
        self.history: List[CalibrationMetrics] = []
        self.stable_epoch_count = 0
        self.auto_mode_unlocked = False
    
    def record_metrics(
        self,
        epoch: int,
        confidences: list,
        predictions: list,
        labels: list,
    ) -> CalibrationMetrics:
        """Record calibration metrics for an epoch."""
        calc = CalibrationCalculator()
        
        accuracy = calc.compute_accuracy(predictions, labels)
        ece = calc.compute_ece(confidences, predictions, labels)
        brier = calc.compute_brier(confidences, labels)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        histogram = calc.compute_confidence_histogram(confidences)
        
        metrics = CalibrationMetrics(
            epoch=epoch,
            accuracy=round(accuracy, 4),
            ece=round(ece, 4),
            brier=round(brier, 4),
            avg_confidence=round(avg_conf, 4),
            confidence_histogram=histogram,
            timestamp=datetime.now().isoformat(),
        )
        
        self.history.append(metrics)
        self._update_stability(metrics)
        
        return metrics
    
    def _update_stability(self, metrics: CalibrationMetrics) -> None:
        """Update stability counter."""
        meets_thresholds = (
            metrics.accuracy >= self.thresholds.min_accuracy and
            metrics.ece <= self.thresholds.max_ece and
            metrics.brier <= self.thresholds.max_brier
        )
        
        if meets_thresholds:
            self.stable_epoch_count += 1
        else:
            self.stable_epoch_count = 0
    
    def check_auto_mode_unlock(
        self,
        checkpoint_count: int,
        drift_events: int = 0,
        replay_verified: bool = True,
    ) -> Tuple[bool, Dict[str, bool]]:
        """
        Check if auto-mode can be unlocked.
        
        Returns:
            Tuple of (can_unlock, requirement_status)
        """
        if not self.history:
            return False, {"no_metrics": True}
        
        latest = self.history[-1]
        
        requirements = {
            "accuracy_97": latest.accuracy >= self.thresholds.min_accuracy,
            "ece_002": latest.ece <= self.thresholds.max_ece,
            "brier_003": latest.brier <= self.thresholds.max_brier,
            "stable_epochs_10": self.stable_epoch_count >= self.thresholds.min_stable_epochs,
            "no_drift_events": drift_events == 0,
            "checkpoints_50": checkpoint_count >= self.thresholds.min_checkpoints,
            "replay_verified": replay_verified,
        }
        
        can_unlock = all(requirements.values())
        
        if can_unlock:
            self.auto_mode_unlocked = True
        
        return can_unlock, requirements
    
    def get_unlock_status(self) -> dict:
        """Get current unlock status."""
        if not self.history:
            return {"status": "no_data"}
        
        latest = self.history[-1]
        
        return {
            "auto_mode_unlocked": self.auto_mode_unlocked,
            "latest_accuracy": latest.accuracy,
            "latest_ece": latest.ece,
            "latest_brier": latest.brier,
            "stable_epochs": self.stable_epoch_count,
            "total_epochs": len(self.history),
        }
