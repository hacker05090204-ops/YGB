"""
training_monitor.py — Energy Metrics + Drift Detection (Phases 3+7)

Phase 3 — Energy Metrics:
  Accepts avg_power_watts + epoch_duration from C++ GPU monitor.
  Computes energy_per_epoch = power * time (joules).

Phase 7 — Drift Detection:
  Tracks val_loss, grad_norm, accuracy history.
  Detects: loss spikes, grad explosion, accuracy drops.
  Returns DriftReport with anomaly type and severity.
"""

import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# ENERGY METRICS (Phase 3)
# =============================================================================

@dataclass
class EnergyMetrics:
    """Energy consumption for one epoch."""
    epoch: int
    avg_power_watts: float
    epoch_duration_sec: float
    energy_joules: float       # power * time
    energy_kwh: float
    node_id: str = ""


class EnergyTracker:
    """Tracks per-epoch energy consumption across nodes.

    C++ GPU monitor collects avg_power_watts + epoch_duration.
    Python computes energy_per_epoch = power * time.
    """

    def __init__(self):
        self.epoch_energy: List[EnergyMetrics] = []
        self.total_energy_joules: float = 0.0

    def record_epoch(
        self,
        epoch: int,
        avg_power_watts: float,
        epoch_duration_sec: float,
        node_id: str = "",
    ) -> EnergyMetrics:
        """Record energy for one epoch.

        Args:
            epoch: Epoch number.
            avg_power_watts: Average GPU power draw (from C++ monitor).
            epoch_duration_sec: Epoch wall-clock time.
            node_id: Optional node identifier.

        Returns:
            EnergyMetrics.
        """
        energy_j = avg_power_watts * epoch_duration_sec
        energy_kwh = energy_j / 3_600_000

        metrics = EnergyMetrics(
            epoch=epoch,
            avg_power_watts=round(avg_power_watts, 2),
            epoch_duration_sec=round(epoch_duration_sec, 3),
            energy_joules=round(energy_j, 2),
            energy_kwh=round(energy_kwh, 6),
            node_id=node_id,
        )

        self.epoch_energy.append(metrics)
        self.total_energy_joules += energy_j

        logger.info(
            f"[ENERGY] Epoch {epoch}: {avg_power_watts:.1f}W × "
            f"{epoch_duration_sec:.1f}s = {energy_j:.1f}J "
            f"({energy_kwh:.6f} kWh)"
        )

        return metrics

    def get_average_energy(self) -> float:
        """Average energy per epoch in joules."""
        if not self.epoch_energy:
            return 0.0
        return self.total_energy_joules / len(self.epoch_energy)

    def get_summary(self) -> dict:
        """Energy summary across all epochs."""
        return {
            'total_epochs': len(self.epoch_energy),
            'total_energy_joules': round(self.total_energy_joules, 2),
            'total_energy_kwh': round(self.total_energy_joules / 3_600_000, 6),
            'avg_energy_per_epoch': round(self.get_average_energy(), 2),
            'avg_power_watts': round(
                sum(e.avg_power_watts for e in self.epoch_energy) /
                max(len(self.epoch_energy), 1), 2
            ),
        }


# =============================================================================
# DRIFT DETECTION (Phase 7)
# =============================================================================

class DriftType(str, Enum):
    """Types of training drift."""
    LOSS_SPIKE = "loss_spike"
    GRAD_EXPLOSION = "grad_explosion"
    ACCURACY_DROP = "accuracy_drop"
    LOSS_PLATEAU = "loss_plateau"


class DriftSeverity(str, Enum):
    """Drift severity levels."""
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftAnomaly:
    """Single drift anomaly."""
    drift_type: str
    severity: str
    epoch: int
    current_value: float
    previous_value: float
    threshold: float
    message: str


@dataclass
class DriftReport:
    """Drift detection report for one epoch."""
    epoch: int
    anomalies: List[DriftAnomaly] = field(default_factory=list)
    should_pause: bool = False
    recommendation: str = "continue"
    timestamp: str = ""


# Thresholds
LOSS_SPIKE_WARN = 2.0       # 2× previous loss
LOSS_SPIKE_CRIT = 5.0       # 5× previous loss
GRAD_NORM_WARN = 10.0       # 10× previous grad norm
GRAD_NORM_CRIT = 100.0      # 100× previous grad norm
ACC_DROP_WARN = 0.05         # 5% accuracy drop
ACC_DROP_CRIT = 0.10         # 10% accuracy drop
LOSS_PLATEAU_EPOCHS = 5      # Epochs with <0.1% improvement


class DriftDetector:
    """Monitors training health and detects drift.

    After each epoch, call check_epoch() with current metrics.
    Returns DriftReport with anomalies and recommendations.
    """

    def __init__(self):
        self.val_loss_history: List[float] = []
        self.grad_norm_history: List[float] = []
        self.accuracy_history: List[float] = []
        self.drift_reports: List[DriftReport] = []

    def check_epoch(
        self,
        epoch: int,
        val_loss: float,
        grad_norm: float,
        accuracy: float,
    ) -> DriftReport:
        """Check for drift anomalies after an epoch.

        Args:
            epoch: Current epoch number.
            val_loss: Validation loss.
            grad_norm: Average gradient L2 norm.
            accuracy: Validation accuracy.

        Returns:
            DriftReport with any detected anomalies.
        """
        anomalies = []

        # --- Loss spike ---
        if self.val_loss_history:
            prev_loss = self.val_loss_history[-1]
            if prev_loss > 0:
                ratio = val_loss / prev_loss
                if ratio >= LOSS_SPIKE_CRIT:
                    anomalies.append(DriftAnomaly(
                        drift_type=DriftType.LOSS_SPIKE,
                        severity=DriftSeverity.CRITICAL,
                        epoch=epoch,
                        current_value=val_loss,
                        previous_value=prev_loss,
                        threshold=LOSS_SPIKE_CRIT,
                        message=f"Loss spiked {ratio:.1f}× (CRITICAL)",
                    ))
                elif ratio >= LOSS_SPIKE_WARN:
                    anomalies.append(DriftAnomaly(
                        drift_type=DriftType.LOSS_SPIKE,
                        severity=DriftSeverity.WARNING,
                        epoch=epoch,
                        current_value=val_loss,
                        previous_value=prev_loss,
                        threshold=LOSS_SPIKE_WARN,
                        message=f"Loss spiked {ratio:.1f}× (WARNING)",
                    ))

        # --- Gradient explosion ---
        if self.grad_norm_history:
            prev_norm = self.grad_norm_history[-1]
            if prev_norm > 0:
                ratio = grad_norm / prev_norm
                if ratio >= GRAD_NORM_CRIT:
                    anomalies.append(DriftAnomaly(
                        drift_type=DriftType.GRAD_EXPLOSION,
                        severity=DriftSeverity.CRITICAL,
                        epoch=epoch,
                        current_value=grad_norm,
                        previous_value=prev_norm,
                        threshold=GRAD_NORM_CRIT,
                        message=f"Grad norm exploded {ratio:.1f}× (CRITICAL)",
                    ))
                elif ratio >= GRAD_NORM_WARN:
                    anomalies.append(DriftAnomaly(
                        drift_type=DriftType.GRAD_EXPLOSION,
                        severity=DriftSeverity.WARNING,
                        epoch=epoch,
                        current_value=grad_norm,
                        previous_value=prev_norm,
                        threshold=GRAD_NORM_WARN,
                        message=f"Grad norm spike {ratio:.1f}× (WARNING)",
                    ))

        # --- Accuracy drop ---
        if self.accuracy_history:
            prev_acc = self.accuracy_history[-1]
            drop = prev_acc - accuracy
            if drop >= ACC_DROP_CRIT:
                anomalies.append(DriftAnomaly(
                    drift_type=DriftType.ACCURACY_DROP,
                    severity=DriftSeverity.CRITICAL,
                    epoch=epoch,
                    current_value=accuracy,
                    previous_value=prev_acc,
                    threshold=ACC_DROP_CRIT,
                    message=f"Accuracy dropped {drop:.1%} (CRITICAL)",
                ))
            elif drop >= ACC_DROP_WARN:
                anomalies.append(DriftAnomaly(
                    drift_type=DriftType.ACCURACY_DROP,
                    severity=DriftSeverity.WARNING,
                    epoch=epoch,
                    current_value=accuracy,
                    previous_value=prev_acc,
                    threshold=ACC_DROP_WARN,
                    message=f"Accuracy dropped {drop:.1%} (WARNING)",
                ))

        # --- Loss plateau ---
        if len(self.val_loss_history) >= LOSS_PLATEAU_EPOCHS:
            recent = self.val_loss_history[-LOSS_PLATEAU_EPOCHS:]
            if all(abs(recent[i] - recent[i-1]) / max(abs(recent[i-1]), 1e-10) < 0.001
                   for i in range(1, len(recent))):
                anomalies.append(DriftAnomaly(
                    drift_type=DriftType.LOSS_PLATEAU,
                    severity=DriftSeverity.WARNING,
                    epoch=epoch,
                    current_value=val_loss,
                    previous_value=recent[0],
                    threshold=LOSS_PLATEAU_EPOCHS,
                    message=f"Loss plateau for {LOSS_PLATEAU_EPOCHS} epochs",
                ))

        # Update history
        self.val_loss_history.append(val_loss)
        self.grad_norm_history.append(grad_norm)
        self.accuracy_history.append(accuracy)

        # Determine recommendation
        has_critical = any(
            a.severity == DriftSeverity.CRITICAL for a in anomalies
        )
        should_pause = has_critical

        if should_pause:
            recommendation = "PAUSE — critical drift detected"
        elif anomalies:
            recommendation = "MONITOR — warnings detected"
        else:
            recommendation = "continue"

        report = DriftReport(
            epoch=epoch,
            anomalies=anomalies,
            should_pause=should_pause,
            recommendation=recommendation,
            timestamp=datetime.now().isoformat(),
        )

        self.drift_reports.append(report)

        # Log
        if has_critical:
            for a in anomalies:
                logger.error(f"[DRIFT] {a.message}")
            logger.error(f"[DRIFT] Epoch {epoch}: PAUSE RECOMMENDED")
        elif anomalies:
            for a in anomalies:
                logger.warning(f"[DRIFT] {a.message}")
        else:
            logger.info(f"[DRIFT] Epoch {epoch}: healthy")

        return report

    def get_summary(self) -> dict:
        """Get drift detection summary."""
        total_anomalies = sum(len(r.anomalies) for r in self.drift_reports)
        pauses = sum(1 for r in self.drift_reports if r.should_pause)
        return {
            'epochs_monitored': len(self.drift_reports),
            'total_anomalies': total_anomalies,
            'pause_recommendations': pauses,
            'current_val_loss': self.val_loss_history[-1] if self.val_loss_history else None,
            'current_accuracy': self.accuracy_history[-1] if self.accuracy_history else None,
        }
