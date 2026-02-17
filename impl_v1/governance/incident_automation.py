"""
Incident Runbook Automation
============================

When drift triggers:
- Auto-generate incident report
- Last 1000 scan metrics
- Model diff summary
- Performance diff
- Dependency diff
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# INCIDENT TYPES
# =============================================================================

class IncidentType:
    """Incident type constants."""
    DRIFT = "drift"
    PERFORMANCE = "performance"
    CALIBRATION = "calibration"
    SECURITY = "security"
    DEPENDENCY = "dependency"


# =============================================================================
# INCIDENT REPORT
# =============================================================================

@dataclass
class IncidentReport:
    """Generated incident report."""
    incident_id: str
    incident_type: str
    timestamp: str
    severity: str
    summary: str
    scan_metrics: dict
    model_diff: dict
    performance_diff: dict
    dependency_diff: dict
    recommended_actions: List[str]


# =============================================================================
# INCIDENT GENERATOR
# =============================================================================

class IncidentReportGenerator:
    """Generate incident reports automatically."""
    
    REPORTS_DIR = Path("reports/incidents")
    
    def __init__(self):
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    def generate_incident_report(
        self,
        incident_type: str,
        severity: str,
        summary: str,
        scan_metrics: dict = None,
        model_diff: dict = None,
        performance_diff: dict = None,
        dependency_diff: dict = None,
    ) -> IncidentReport:
        """Generate a complete incident report."""
        incident_id = f"INC_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        report = IncidentReport(
            incident_id=incident_id,
            incident_type=incident_type,
            timestamp=datetime.now().isoformat(),
            severity=severity,
            summary=summary,
            scan_metrics=scan_metrics or self._get_default_scan_metrics(),
            model_diff=model_diff or {},
            performance_diff=performance_diff or {},
            dependency_diff=dependency_diff or {},
            recommended_actions=self._generate_recommendations(incident_type),
        )
        
        self._save_report(report)
        
        return report
    
    def _get_default_scan_metrics(self) -> dict:
        """Load real scan metrics from latest metrics file.

        Returns empty dict if no metrics file exists — never fabricates data.
        """
        metrics_file = Path("reports/last_1000_scan_metrics.json")
        if metrics_file.exists():
            try:
                return json.loads(metrics_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    
    def _generate_recommendations(self, incident_type: str) -> List[str]:
        """Generate recommended actions based on incident type."""
        recommendations = {
            IncidentType.DRIFT: [
                "Review last 100 predictions for pattern changes",
                "Compare current model metrics to baseline",
                "Consider rolling back to previous checkpoint",
                "Schedule calibration rerun",
            ],
            IncidentType.PERFORMANCE: [
                "Check system resource usage",
                "Review recent infrastructure changes",
                "Analyze slow query patterns",
                "Consider scaling compute resources",
            ],
            IncidentType.CALIBRATION: [
                "Run full calibration suite",
                "Review confidence distribution",
                "Check for data distribution shift",
                "Disable auto-mode until resolved",
            ],
            IncidentType.SECURITY: [
                "Audit recent access logs",
                "Check for unauthorized changes",
                "Verify all signatures",
                "Enable emergency lock if needed",
            ],
            IncidentType.DEPENDENCY: [
                "Review dependency changelog",
                "Test with pinned versions",
                "Run determinism validation",
                "Update baseline if approved",
            ],
        }
        
        return recommendations.get(incident_type, ["Investigate and document findings"])
    
    def _save_report(self, report: IncidentReport) -> Path:
        """Save incident report to file."""
        filename = f"{report.incident_id}.json"
        filepath = self.REPORTS_DIR / filename
        
        with open(filepath, "w") as f:
            json.dump({
                "incident_id": report.incident_id,
                "incident_type": report.incident_type,
                "timestamp": report.timestamp,
                "severity": report.severity,
                "summary": report.summary,
                "scan_metrics": report.scan_metrics,
                "model_diff": report.model_diff,
                "performance_diff": report.performance_diff,
                "dependency_diff": report.dependency_diff,
                "recommended_actions": report.recommended_actions,
            }, f, indent=2)
        
        return filepath
    
    def on_drift_detected(
        self,
        drift_type: str,
        delta: float,
        model_metrics: dict,
    ) -> IncidentReport:
        """Auto-generate report when drift is detected."""
        return self.generate_incident_report(
            incident_type=IncidentType.DRIFT,
            severity="high" if abs(delta) > 0.05 else "medium",
            summary=f"{drift_type} drift detected: {delta:.4f}",
            model_diff={"drift_type": drift_type, "delta": delta},
            scan_metrics=model_metrics,
        )


# =============================================================================
# ANNUAL REVALIDATION
# =============================================================================

class AnnualRevalidationLock:
    """Hard gate for model age > 365 days."""
    
    MAX_AGE_DAYS = 365
    
    def __init__(self):
        self.last_validation: Optional[datetime] = None
    
    def check_model_age(self, deployment_date: str) -> tuple:
        """Check if model requires revalidation."""
        deployment = datetime.fromisoformat(deployment_date)
        age = datetime.now() - deployment
        
        if age.days > self.MAX_AGE_DAYS:
            return False, f"Model expired: {age.days} days old (max {self.MAX_AGE_DAYS})"
        
        days_remaining = self.MAX_AGE_DAYS - age.days
        return True, f"Model valid for {days_remaining} more days"
    
    def record_revalidation(self) -> None:
        """Record successful revalidation."""
        self.last_validation = datetime.now()
    
    def should_disable_auto_mode(self, deployment_date: str) -> tuple:
        """Check if auto-mode should be disabled due to age."""
        valid, msg = self.check_model_age(deployment_date)
        return not valid, msg
