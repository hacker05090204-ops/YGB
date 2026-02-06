"""
Model Drift Monitor - Phase 50
================================

Track model health over time:
- Rolling accuracy (1000 scan window)
- Rolling calibration error
- Confidence inflation detection

Alerts:
- Accuracy drop > 3%
- ECE increase > 0.01
- Confidence inflation > 5%
"""

from dataclasses import dataclass, field
from typing import List, Optional, Deque
from collections import deque
from datetime import datetime
from pathlib import Path
from enum import Enum
import json


# =============================================================================
# CONFIGURATION
# =============================================================================

WINDOW_SIZE = 1000
ACCURACY_THRESHOLD = 0.03      # 3% drop
ECE_THRESHOLD = 0.01           # 0.01 increase
CONFIDENCE_THRESHOLD = 0.05   # 5% inflation

DRIFT_LOG_DIR = Path("reports/drift")
BASELINE_FILE = Path(__file__).parent.parent / "DRIFT_BASELINE.json"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class DriftType(Enum):
    """Types of drift."""
    ACCURACY = "accuracy_drop"
    CALIBRATION = "calibration_error"
    CONFIDENCE = "confidence_inflation"
    NONE = "no_drift"


@dataclass
class ScanResult:
    """Result from a single scan."""
    timestamp: str
    predicted: bool
    actual: bool
    confidence: float


@dataclass
class DriftAlert:
    """Alert for detected drift."""
    drift_type: DriftType
    baseline_value: float
    current_value: float
    delta: float
    timestamp: str
    action: str


@dataclass
class DriftBaseline:
    """Baseline metrics for drift comparison."""
    accuracy: float
    ece: float  # Expected Calibration Error
    avg_confidence: float
    created: str


# =============================================================================
# DRIFT MONITOR
# =============================================================================

class ModelDriftMonitor:
    """Monitor for model drift detection."""
    
    def __init__(self, window_size: int = WINDOW_SIZE):
        self.window_size = window_size
        self.results: Deque[ScanResult] = deque(maxlen=window_size)
        self.baseline = self._load_baseline()
        self.auto_mode_enabled = True
    
    def _load_baseline(self) -> Optional[DriftBaseline]:
        """Load baseline from file."""
        if not BASELINE_FILE.exists():
            return None
        
        try:
            with open(BASELINE_FILE, "r") as f:
                data = json.load(f)
            return DriftBaseline(**data)
        except Exception:
            return None
    
    def record_scan(self, predicted: bool, actual: bool, confidence: float) -> None:
        """Record a scan result."""
        self.results.append(ScanResult(
            timestamp=datetime.now().isoformat(),
            predicted=predicted,
            actual=actual,
            confidence=confidence,
        ))
    
    def get_rolling_accuracy(self) -> float:
        """Calculate rolling accuracy."""
        if len(self.results) == 0:
            return 1.0
        
        correct = sum(1 for r in self.results if r.predicted == r.actual)
        return correct / len(self.results)
    
    def get_rolling_ece(self) -> float:
        """Calculate rolling Expected Calibration Error."""
        if len(self.results) == 0:
            return 0.0
        
        # Simplified ECE: avg(|confidence - accuracy|)
        total = 0.0
        for r in self.results:
            correct = 1.0 if r.predicted == r.actual else 0.0
            total += abs(r.confidence - correct)
        
        return total / len(self.results)
    
    def get_avg_confidence(self) -> float:
        """Calculate average confidence."""
        if len(self.results) == 0:
            return 0.5
        
        return sum(r.confidence for r in self.results) / len(self.results)
    
    def check_drift(self) -> List[DriftAlert]:
        """Check for drift against baseline."""
        if not self.baseline:
            return []
        
        alerts = []
        now = datetime.now().isoformat()
        
        # Check accuracy drop
        current_acc = self.get_rolling_accuracy()
        acc_delta = self.baseline.accuracy - current_acc
        if acc_delta > ACCURACY_THRESHOLD:
            alerts.append(DriftAlert(
                drift_type=DriftType.ACCURACY,
                baseline_value=self.baseline.accuracy,
                current_value=current_acc,
                delta=acc_delta,
                timestamp=now,
                action="DISABLE_AUTO_MODE",
            ))
        
        # Check ECE increase
        current_ece = self.get_rolling_ece()
        ece_delta = current_ece - self.baseline.ece
        if ece_delta > ECE_THRESHOLD:
            alerts.append(DriftAlert(
                drift_type=DriftType.CALIBRATION,
                baseline_value=self.baseline.ece,
                current_value=current_ece,
                delta=ece_delta,
                timestamp=now,
                action="DISABLE_AUTO_MODE",
            ))
        
        # Check confidence inflation
        current_conf = self.get_avg_confidence()
        conf_delta = current_conf - self.baseline.avg_confidence
        if conf_delta > CONFIDENCE_THRESHOLD:
            alerts.append(DriftAlert(
                drift_type=DriftType.CONFIDENCE,
                baseline_value=self.baseline.avg_confidence,
                current_value=current_conf,
                delta=conf_delta,
                timestamp=now,
                action="DISABLE_AUTO_MODE",
            ))
        
        return alerts
    
    def handle_drift(self, alerts: List[DriftAlert]) -> bool:
        """
        Handle detected drift.
        
        Returns True if auto_mode should remain enabled.
        """
        if not alerts:
            return True
        
        # Disable auto_mode
        self.auto_mode_enabled = False
        
        # Log to reports/drift/
        self._log_drift(alerts)
        
        return False
    
    def _log_drift(self, alerts: List[DriftAlert]) -> None:
        """Log drift alerts to file."""
        DRIFT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        log_file = DRIFT_LOG_DIR / f"drift_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "window_size": self.window_size,
            "sample_count": len(self.results),
            "alerts": [
                {
                    "type": a.drift_type.value,
                    "baseline": a.baseline_value,
                    "current": a.current_value,
                    "delta": a.delta,
                    "action": a.action,
                }
                for a in alerts
            ],
        }
        
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)


# =============================================================================
# BASELINE CREATION
# =============================================================================

def create_drift_baseline(
    accuracy: float,
    ece: float,
    avg_confidence: float,
) -> DriftBaseline:
    """Create and save drift baseline."""
    baseline = DriftBaseline(
        accuracy=accuracy,
        ece=ece,
        avg_confidence=avg_confidence,
        created=datetime.now().isoformat(),
    )
    
    # Save to file
    with open(BASELINE_FILE, "w") as f:
        json.dump({
            "accuracy": baseline.accuracy,
            "ece": baseline.ece,
            "avg_confidence": baseline.avg_confidence,
            "created": baseline.created,
        }, f, indent=2)
    
    return baseline
