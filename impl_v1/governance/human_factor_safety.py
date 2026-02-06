"""
Human Factor Safety Layer
==========================

Prevent operator misuse:
- Confidence explanation panel
- Risk band visualization
- Forced acknowledgment
- Alert fatigue counter
- Rate-limit notifications
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from enum import Enum
import json


# =============================================================================
# RISK BANDS
# =============================================================================

class RiskBand(Enum):
    """Risk band classifications."""
    LOW = "low"       # < 30% confidence
    MEDIUM = "medium" # 30-70% confidence
    HIGH = "high"     # > 70% confidence


@dataclass
class ConfidenceExplanation:
    """Explanation of model confidence (non-authoritative)."""
    confidence: float
    risk_band: RiskBand
    factors: List[str]
    disclaimer: str = "This is a model prediction. Human review required."


# =============================================================================
# CONFIDENCE EXPLAINER
# =============================================================================

class ConfidenceExplainer:
    """Generate confidence explanations for operators."""
    
    def explain(self, confidence: float, features: dict = None) -> ConfidenceExplanation:
        """Generate confidence explanation."""
        # Determine risk band
        if confidence < 0.3:
            risk_band = RiskBand.LOW
        elif confidence < 0.7:
            risk_band = RiskBand.MEDIUM
        else:
            risk_band = RiskBand.HIGH
        
        # Generate factors
        factors = self._extract_factors(confidence, features or {})
        
        return ConfidenceExplanation(
            confidence=round(confidence, 4),
            risk_band=risk_band,
            factors=factors,
        )
    
    def _extract_factors(self, confidence: float, features: dict) -> List[str]:
        """Extract contributing factors."""
        factors = []
        
        if confidence > 0.9:
            factors.append("Strong pattern match to known vulnerabilities")
        elif confidence > 0.7:
            factors.append("Moderate similarity to vulnerability signatures")
        elif confidence > 0.4:
            factors.append("Partial pattern match detected")
        else:
            factors.append("Low similarity to known patterns")
        
        if features.get("has_payload", False):
            factors.append("Suspicious payload detected")
        
        if features.get("obfuscated", False):
            factors.append("Obfuscation techniques detected")
        
        return factors


# =============================================================================
# FORCED ACKNOWLEDGMENT
# =============================================================================

@dataclass
class AcknowledgmentRequest:
    """Request for operator acknowledgment."""
    request_id: str
    report_type: str
    summary: str
    requires_ack: bool
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[str] = None


class ForcedAcknowledgmentManager:
    """Manage forced acknowledgments for critical reports."""
    
    def __init__(self):
        self.pending: Dict[str, AcknowledgmentRequest] = {}
        self.completed: List[AcknowledgmentRequest] = []
    
    def require_acknowledgment(
        self,
        report_type: str,
        summary: str,
    ) -> AcknowledgmentRequest:
        """Create acknowledgment request."""
        request_id = f"ACK_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        request = AcknowledgmentRequest(
            request_id=request_id,
            report_type=report_type,
            summary=summary,
            requires_ack=True,
        )
        
        self.pending[request_id] = request
        return request
    
    def acknowledge(self, request_id: str, operator: str) -> bool:
        """Acknowledge a request."""
        if request_id not in self.pending:
            return False
        
        request = self.pending.pop(request_id)
        request.acknowledged = True
        request.acknowledged_by = operator
        request.acknowledged_at = datetime.now().isoformat()
        
        self.completed.append(request)
        return True
    
    def has_pending(self) -> bool:
        """Check if there are pending acknowledgments."""
        return len(self.pending) > 0


# =============================================================================
# ALERT FATIGUE MANAGEMENT
# =============================================================================

@dataclass
class AlertFatigueMetrics:
    """Alert fatigue tracking."""
    alerts_last_hour: int
    alerts_last_day: int
    dismissal_rate: float
    fatigue_score: float  # 0-1, higher = more fatigued


class AlertFatigueCounter:
    """Track and manage alert fatigue."""
    
    MAX_ALERTS_PER_HOUR = 20
    MAX_ALERTS_PER_DAY = 100
    
    def __init__(self):
        self.alerts: List[datetime] = []
        self.dismissals: int = 0
        self.total_shown: int = 0
    
    def record_alert(self) -> None:
        """Record an alert shown."""
        self.alerts.append(datetime.now())
        self.total_shown += 1
        self._cleanup_old_alerts()
    
    def record_dismissal(self) -> None:
        """Record an alert dismissed without action."""
        self.dismissals += 1
    
    def _cleanup_old_alerts(self) -> None:
        """Remove alerts older than 24 hours."""
        cutoff = datetime.now() - timedelta(hours=24)
        self.alerts = [a for a in self.alerts if a > cutoff]
    
    def get_metrics(self) -> AlertFatigueMetrics:
        """Get fatigue metrics."""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        last_hour = sum(1 for a in self.alerts if a > hour_ago)
        last_day = len(self.alerts)
        
        dismissal_rate = self.dismissals / self.total_shown if self.total_shown > 0 else 0
        
        # Fatigue score
        hour_factor = min(last_hour / self.MAX_ALERTS_PER_HOUR, 1.0)
        day_factor = min(last_day / self.MAX_ALERTS_PER_DAY, 1.0)
        fatigue = (hour_factor + day_factor + dismissal_rate) / 3
        
        return AlertFatigueMetrics(
            alerts_last_hour=last_hour,
            alerts_last_day=last_day,
            dismissal_rate=round(dismissal_rate, 4),
            fatigue_score=round(fatigue, 4),
        )
    
    def should_rate_limit(self) -> Tuple[bool, str]:
        """Check if alerts should be rate-limited."""
        metrics = self.get_metrics()
        
        if metrics.alerts_last_hour >= self.MAX_ALERTS_PER_HOUR:
            return True, f"Rate limit: {metrics.alerts_last_hour} alerts in last hour"
        
        if metrics.fatigue_score > 0.7:
            return True, f"Alert fatigue high: {metrics.fatigue_score:.2f}"
        
        return False, "OK"


# =============================================================================
# NOTIFICATION RATE LIMITER
# =============================================================================

class NotificationRateLimiter:
    """Rate-limit high-severity notifications."""
    
    LIMITS = {
        "critical": {"per_minute": 2, "per_hour": 10},
        "high": {"per_minute": 5, "per_hour": 30},
        "medium": {"per_minute": 10, "per_hour": 60},
        "low": {"per_minute": 20, "per_hour": 100},
    }
    
    def __init__(self):
        self.history: Dict[str, List[datetime]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
        }
    
    def can_send(self, severity: str) -> Tuple[bool, str]:
        """Check if notification can be sent."""
        if severity not in self.LIMITS:
            severity = "medium"
        
        limits = self.LIMITS[severity]
        now = datetime.now()
        
        # Get recent notifications
        recent = self.history.get(severity, [])
        
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        per_minute = sum(1 for t in recent if t > minute_ago)
        per_hour = sum(1 for t in recent if t > hour_ago)
        
        if per_minute >= limits["per_minute"]:
            return False, f"Rate limited: {per_minute}/{limits['per_minute']} per minute"
        
        if per_hour >= limits["per_hour"]:
            return False, f"Rate limited: {per_hour}/{limits['per_hour']} per hour"
        
        return True, "OK"
    
    def record_sent(self, severity: str) -> None:
        """Record a sent notification."""
        if severity not in self.history:
            self.history[severity] = []
        
        self.history[severity].append(datetime.now())
        
        # Cleanup old entries
        hour_ago = datetime.now() - timedelta(hours=1)
        self.history[severity] = [
            t for t in self.history[severity] if t > hour_ago
        ]
