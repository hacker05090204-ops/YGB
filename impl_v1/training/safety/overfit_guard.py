"""
overfit_guard.py — Overfitting Guard & Generalization Gap Monitor

Monitors:
  generalization_gap = train_loss - val_loss

If gap > threshold:
  - Emit warning
  - Disable early stopping
  - Log overfit_warning in telemetry

Runs per-epoch and cumulatively.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_GAP_THRESHOLD = 0.15  # Max allowed generalization gap
MIN_EPOCHS_BEFORE_CHECK = 3   # Don't check until min epochs trained


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class OverfitMetrics:
    """Per-epoch overfitting metrics."""
    epoch: int
    train_loss: float
    val_loss: float
    generalization_gap: float
    overfit_warning: bool


@dataclass
class OverfitStatus:
    """Cumulative overfitting guard status."""
    overfit_warning: bool = False
    consecutive_warnings: int = 0
    max_gap_seen: float = 0.0
    early_stop_disabled: bool = False
    epoch_metrics: List[OverfitMetrics] = field(default_factory=list)


# =============================================================================
# GUARD
# =============================================================================

class OverfitGuard:
    """Monitor generalization gap and guard against overfitting.
    
    If gap exceeds threshold:
      - Emits warning
      - Disables early stopping
      - Sets overfit_warning in telemetry
    """
    
    def __init__(self, threshold: float = DEFAULT_GAP_THRESHOLD):
        self._threshold = threshold
        self._status = OverfitStatus()
    
    @property
    def threshold(self) -> float:
        return self._threshold
    
    @property
    def status(self) -> OverfitStatus:
        return self._status
    
    @property
    def overfit_warning(self) -> bool:
        return self._status.overfit_warning
    
    @property
    def should_disable_early_stop(self) -> bool:
        return self._status.early_stop_disabled
    
    def check_epoch(
        self, epoch: int, train_loss: float, val_loss: float
    ) -> OverfitMetrics:
        """Check for overfitting after an epoch.
        
        Args:
            epoch: Current epoch number.
            train_loss: Training loss.
            val_loss: Validation loss.
        
        Returns:
            OverfitMetrics for this epoch.
        """
        gap = train_loss - val_loss
        warning = False
        
        if epoch >= MIN_EPOCHS_BEFORE_CHECK and gap > self._threshold:
            warning = True
            self._status.consecutive_warnings += 1
            
            if not self._status.early_stop_disabled:
                self._status.early_stop_disabled = True
                logger.warning(
                    f"[OVERFIT] Early stopping DISABLED due to overfitting "
                    f"(gap={gap:.4f} > threshold={self._threshold:.4f})"
                )
        else:
            self._status.consecutive_warnings = 0
        
        self._status.overfit_warning = warning
        self._status.max_gap_seen = max(self._status.max_gap_seen, gap)
        
        metrics = OverfitMetrics(
            epoch=epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            generalization_gap=gap,
            overfit_warning=warning,
        )
        self._status.epoch_metrics.append(metrics)
        
        if warning:
            logger.warning(
                f"[OVERFIT] Epoch {epoch}: gap={gap:.4f} "
                f"(train={train_loss:.4f}, val={val_loss:.4f}) — WARNING"
            )
        else:
            logger.info(
                f"[OVERFIT] Epoch {epoch}: gap={gap:.4f} "
                f"(train={train_loss:.4f}, val={val_loss:.4f}) — OK"
            )
        
        return metrics
    
    def get_telemetry(self) -> dict:
        """Get overfitting telemetry as JSON-serializable dict."""
        return {
            'overfit_warning': self._status.overfit_warning,
            'consecutive_warnings': self._status.consecutive_warnings,
            'max_gap_seen': self._status.max_gap_seen,
            'early_stop_disabled': self._status.early_stop_disabled,
            'threshold': self._threshold,
            'epochs_checked': len(self._status.epoch_metrics),
        }
    
    def reset(self):
        """Reset the guard state."""
        self._status = OverfitStatus()
