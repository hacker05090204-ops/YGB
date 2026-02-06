"""
AI Calibration Enforcement - Phase 49
======================================

Implements calibration metrics for auto-mode safety:
1. Expected Calibration Error (ECE)
2. Brier Score
3. Calibration curve measurement
4. Stability over epochs

AUTO MODE RULES:
- Accuracy >= 97%
- ECE <= 0.02
- 5-epoch stability
- Deterministic replay confirmed
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# CONSTANTS
# =============================================================================

# Auto-mode thresholds
ACCURACY_THRESHOLD = 0.97  # 97%
ECE_THRESHOLD = 0.02       # 2%
MIN_STABILITY_EPOCHS = 5
BRIER_THRESHOLD = 0.03     # Below 3% for good calibration


# =============================================================================
# DATA TYPES
# =============================================================================

class CalibrationStatus(Enum):
    """Calibration check status."""
    PASS = "PASS"
    FAIL_ACCURACY = "FAIL_ACCURACY"
    FAIL_ECE = "FAIL_ECE"
    FAIL_BRIER = "FAIL_BRIER"
    FAIL_STABILITY = "FAIL_STABILITY"
    FAIL_EPOCHS = "FAIL_EPOCHS"
    FAIL_REPLAY = "FAIL_REPLAY"


@dataclass
class CalibrationMetrics:
    """Calibration metrics for a model."""
    accuracy: float
    ece: float
    brier_score: float
    epochs_completed: int
    stability_confirmed: bool
    replay_deterministic: bool
    
    def is_auto_mode_ready(self) -> Tuple[bool, CalibrationStatus]:
        """
        Check if auto-mode can be enabled.
        
        Returns:
            Tuple of (ready, status)
        """
        if self.accuracy < ACCURACY_THRESHOLD:
            return False, CalibrationStatus.FAIL_ACCURACY
        
        if self.ece > ECE_THRESHOLD:
            return False, CalibrationStatus.FAIL_ECE
        
        if self.brier_score > BRIER_THRESHOLD:
            return False, CalibrationStatus.FAIL_BRIER
        
        if self.epochs_completed < MIN_STABILITY_EPOCHS:
            return False, CalibrationStatus.FAIL_EPOCHS
        
        if not self.stability_confirmed:
            return False, CalibrationStatus.FAIL_STABILITY
        
        if not self.replay_deterministic:
            return False, CalibrationStatus.FAIL_REPLAY
        
        return True, CalibrationStatus.PASS


# =============================================================================
# CALIBRATION CALCULATIONS
# =============================================================================

def compute_ece(
    confidences: List[float],
    predictions: List[int],
    labels: List[int],
    n_bins: int = 10,
) -> float:
    """
    Compute Expected Calibration Error.
    
    ECE measures the difference between predicted confidence
    and actual accuracy across confidence bins.
    
    Args:
        confidences: Model confidence scores [0, 1]
        predictions: Model predictions
        labels: True labels
        n_bins: Number of bins for calibration
    
    Returns:
        ECE value (lower is better, 0 = perfect calibration)
    """
    if len(confidences) == 0:
        return 1.0  # No data = uncalibrated
    
    confidences = np.array(confidences)
    predictions = np.array(predictions)
    labels = np.array(labels)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    
    for i in range(n_bins):
        in_bin = (confidences > bin_boundaries[i]) & (confidences <= bin_boundaries[i + 1])
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(predictions[in_bin] == labels[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    
    return float(ece)


def compute_brier_score(
    confidences: List[float],
    labels: List[int],
) -> float:
    """
    Compute Brier Score.
    
    Brier score measures the mean squared error between
    predicted probabilities and actual outcomes.
    
    Args:
        confidences: Model confidence scores [0, 1]
        labels: True labels (0 or 1)
    
    Returns:
        Brier score (lower is better, 0 = perfect)
    """
    if len(confidences) == 0:
        return 1.0
    
    confidences = np.array(confidences)
    labels = np.array(labels)
    
    return float(np.mean((confidences - labels) ** 2))


def compute_accuracy(
    predictions: List[int],
    labels: List[int],
) -> float:
    """
    Compute classification accuracy.
    
    Args:
        predictions: Model predictions
        labels: True labels
    
    Returns:
        Accuracy [0, 1]
    """
    if len(predictions) == 0:
        return 0.0
    
    predictions = np.array(predictions)
    labels = np.array(labels)
    
    return float(np.mean(predictions == labels))


def check_stability(
    epoch_accuracies: List[float],
    min_epochs: int = MIN_STABILITY_EPOCHS,
    variance_threshold: float = 0.001,
) -> bool:
    """
    Check if training is stable over recent epochs.
    
    Args:
        epoch_accuracies: Accuracy per epoch
        min_epochs: Minimum epochs required
        variance_threshold: Maximum allowed variance
    
    Returns:
        True if stable
    """
    if len(epoch_accuracies) < min_epochs:
        return False
    
    recent = epoch_accuracies[-min_epochs:]
    variance = np.var(recent)
    
    return variance <= variance_threshold


def validate_replay_determinism(
    checkpoint_hash_1: str,
    checkpoint_hash_2: str,
) -> bool:
    """
    Validate that replay produces deterministic results.
    
    Args:
        checkpoint_hash_1: Hash from first run
        checkpoint_hash_2: Hash from replay run
    
    Returns:
        True if deterministic (hashes match)
    """
    return checkpoint_hash_1 == checkpoint_hash_2


# =============================================================================
# AUTO-MODE GOVERNOR
# =============================================================================

class AutoModeGovernor:
    """
    Governor for auto-mode activation.
    
    Enforces calibration requirements before allowing auto-mode.
    """
    
    def __init__(self):
        self._auto_mode_enabled = False
        self._last_metrics: Optional[CalibrationMetrics] = None
    
    @property
    def is_enabled(self) -> bool:
        """Check if auto-mode is enabled."""
        return self._auto_mode_enabled
    
    def check_and_enable(self, metrics: CalibrationMetrics) -> Tuple[bool, str]:
        """
        Check calibration and enable auto-mode if criteria met.
        
        Args:
            metrics: Current calibration metrics
        
        Returns:
            Tuple of (enabled, reason)
        """
        self._last_metrics = metrics
        
        ready, status = metrics.is_auto_mode_ready()
        
        if not ready:
            self._auto_mode_enabled = False
            return False, f"Auto-mode BLOCKED: {status.value}"
        
        self._auto_mode_enabled = True
        return True, "Auto-mode ENABLED: All criteria met"
    
    def force_disable(self) -> None:
        """Force disable auto-mode."""
        self._auto_mode_enabled = False
    
    def get_status(self) -> dict:
        """Get current status."""
        return {
            "auto_mode_enabled": self._auto_mode_enabled,
            "thresholds": {
                "accuracy": ACCURACY_THRESHOLD,
                "ece": ECE_THRESHOLD,
                "brier": BRIER_THRESHOLD,
                "min_epochs": MIN_STABILITY_EPOCHS,
            },
            "last_metrics": self._last_metrics,
        }
