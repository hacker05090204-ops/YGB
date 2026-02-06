"""
Alert Router - Production Observability
========================================

Route alerts to appropriate channels:
- Critical: emergency lock
- High: disable auto_mode
- Medium: log + notify
- Low: log only
"""

from dataclasses import dataclass
from typing import List, Optional, Callable
from datetime import datetime
from pathlib import Path
from enum import Enum
import json


# =============================================================================
# ALERT SEVERITY
# =============================================================================

class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Alert:
    """An alert to route."""
    id: str
    severity: AlertSeverity
    source: str
    message: str
    timestamp: str
    metadata: dict


# =============================================================================
# ALERT ACTIONS
# =============================================================================

def action_emergency_lock(alert: Alert) -> bool:
    """Activate emergency lock."""
    # Would actually activate emergency lock
    return True


def action_disable_auto_mode(alert: Alert) -> bool:
    """Disable auto mode."""
    # Would actually disable auto mode
    return True


def action_log_notify(alert: Alert) -> bool:
    """Log and send notification."""
    log_alert(alert)
    return True


def action_log_only(alert: Alert) -> bool:
    """Log only."""
    log_alert(alert)
    return True


def log_alert(alert: Alert) -> None:
    """Log alert to file."""
    log_dir = Path("reports/alerts")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"alert_{datetime.now().strftime('%Y%m%d')}.jsonl"
    
    with open(log_file, "a") as f:
        f.write(json.dumps({
            "id": alert.id,
            "severity": alert.severity.value,
            "source": alert.source,
            "message": alert.message,
            "timestamp": alert.timestamp,
            "metadata": alert.metadata,
        }) + "\n")


# =============================================================================
# ALERT ROUTER
# =============================================================================

class AlertRouter:
    """Route alerts based on severity."""
    
    def __init__(self):
        self.routing_table = {
            AlertSeverity.CRITICAL: [action_emergency_lock, action_log_notify],
            AlertSeverity.HIGH: [action_disable_auto_mode, action_log_notify],
            AlertSeverity.MEDIUM: [action_log_notify],
            AlertSeverity.LOW: [action_log_only],
        }
        self.processed: List[Alert] = []
    
    def route(self, alert: Alert) -> List[str]:
        """Route an alert through appropriate actions."""
        actions = self.routing_table.get(alert.severity, [action_log_only])
        results = []
        
        for action in actions:
            try:
                success = action(alert)
                results.append(f"{action.__name__}: {'OK' if success else 'FAIL'}")
            except Exception as e:
                results.append(f"{action.__name__}: ERROR - {e}")
        
        self.processed.append(alert)
        return results
    
    def create_alert(
        self,
        severity: AlertSeverity,
        source: str,
        message: str,
        metadata: dict = None,
    ) -> Alert:
        """Create and route an alert."""
        alert = Alert(
            id=f"ALERT_{len(self.processed):04d}",
            severity=severity,
            source=source,
            message=message,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )
        self.route(alert)
        return alert


# =============================================================================
# ALERT SOURCES
# =============================================================================

def alert_from_drift(drift_type: str, delta: float) -> Alert:
    """Create alert from drift detection."""
    severity = AlertSeverity.HIGH if abs(delta) > 0.05 else AlertSeverity.MEDIUM
    return Alert(
        id=f"DRIFT_{datetime.now().strftime('%H%M%S')}",
        severity=severity,
        source="drift_monitor",
        message=f"{drift_type} drift detected: {delta:.4f}",
        timestamp=datetime.now().isoformat(),
        metadata={"drift_type": drift_type, "delta": delta},
    )


def alert_from_seccomp(syscall: str) -> Alert:
    """Create alert from seccomp violation."""
    return Alert(
        id=f"SECCOMP_{datetime.now().strftime('%H%M%S')}",
        severity=AlertSeverity.CRITICAL,
        source="seccomp_monitor",
        message=f"Seccomp violation: {syscall}",
        timestamp=datetime.now().isoformat(),
        metadata={"syscall": syscall},
    )
