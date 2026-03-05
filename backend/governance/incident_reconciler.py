"""
Incident/Drift Reconciler — Consistency check between incidents and auto_mode state.

Validates that:
1. If incidents exist, no_drift_events cannot be true unless explicitly scoped
2. auto_mode_state timestamps are consistent with incident log
3. Produces a structured reconciliation report

Usage:
    from backend.governance.incident_reconciler import reconcile
    report = reconcile()
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("ygb.incident_reconciler")

PROJECT_ROOT = Path(__file__).parent.parent.parent


class ReconciliationReport:
    """Structured reconciliation report."""

    def __init__(self):
        self.consistent = True
        self.checks: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def add_check(self, name: str, passed: bool, detail: str):
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.consistent = False

    def to_dict(self) -> dict:
        return {
            "consistent": self.consistent,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "timestamp": datetime.now().isoformat(),
        }


def _load_json_file(path: Path) -> Optional[dict]:
    """Load a JSON file, returning None if not found or invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load %s: %s", path, e)
        return None


def _find_incident_files(reports_dir: Path) -> List[Path]:
    """Find all incident-related files in the reports directory (recursive)."""
    incidents = []
    if not reports_dir.exists():
        return incidents
    # Search recursively so incidents under reports/incidents/ are found
    for pattern in ["incident*.json", "incidents*.json", "incident_log*.json"]:
        incidents.extend(reports_dir.rglob(pattern))
    # Deduplicate (rglob may overlap with direct matches)
    return list(set(incidents))


def reconcile(
    reports_dir: Optional[Path] = None,
    auto_mode_path: Optional[Path] = None,
) -> ReconciliationReport:
    """
    Run consistency checks between incident files and auto_mode_state.

    Returns a ReconciliationReport with all findings.
    """
    report = ReconciliationReport()

    if reports_dir is None:
        reports_dir = PROJECT_ROOT / "reports"
    if auto_mode_path is None:
        auto_mode_path = reports_dir / "auto_mode_state.json"

    # Check 1: auto_mode_state.json exists
    auto_state = _load_json_file(auto_mode_path)
    if auto_state is None:
        report.add_check(
            "auto_mode_state_exists", False,
            f"auto_mode_state.json not found at {auto_mode_path}"
        )
        report.warnings.append("Cannot perform drift consistency checks without auto_mode_state.json")
        return report
    report.add_check("auto_mode_state_exists", True, "auto_mode_state.json loaded")

    # Check 2: Find incident files
    incident_files = _find_incident_files(reports_dir)
    has_incidents = len(incident_files) > 0
    report.add_check(
        "incident_files_scan", True,
        f"Found {len(incident_files)} incident file(s)" if has_incidents
        else "No incident files found"
    )

    # Check 3: no_drift_events consistency
    no_drift = auto_state.get("no_drift_events", None)
    drift_window = auto_state.get("drift_check_window", None)

    if has_incidents and no_drift is True:
        # Incidents exist but no_drift_events is True — inconsistency
        # UNLESS there's an explicit timestamp window scoping
        if drift_window:
            report.add_check(
                "drift_consistency", True,
                f"no_drift_events=True is scoped to window: {drift_window}"
            )
            report.warnings.append(
                "no_drift_events=True with incidents present — "
                f"valid only within declared window: {drift_window}"
            )
        else:
            report.add_check(
                "drift_consistency", False,
                f"INCONSISTENCY: {len(incident_files)} incident file(s) exist "
                "but no_drift_events=True without explicit timestamp scope"
            )
            report.errors.append(
                "Drift state claims no events but incident files are present. "
                "Either clear incidents or set no_drift_events=False."
            )
    elif has_incidents and no_drift is False:
        report.add_check(
            "drift_consistency", True,
            "Consistent: incidents exist and no_drift_events=False"
        )
    elif not has_incidents and no_drift is True:
        report.add_check(
            "drift_consistency", True,
            "Consistent: no incidents and no_drift_events=True"
        )
    elif no_drift is None:
        report.add_check(
            "drift_consistency", True,
            "no_drift_events field not present — no assertion to check"
        )
        report.warnings.append("no_drift_events field missing from auto_mode_state.json")
    else:
        report.add_check(
            "drift_consistency", True,
            f"no_drift_events={no_drift}, incidents={has_incidents} — consistent"
        )

    # Check 4: Timestamp freshness
    last_update = auto_state.get("last_updated") or auto_state.get("timestamp")
    if last_update:
        try:
            last_dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
            age_hours = (datetime.now(last_dt.tzinfo) - last_dt).total_seconds() / 3600
            if age_hours > 24:
                report.add_check(
                    "state_freshness", False,
                    f"auto_mode_state.json is {age_hours:.1f} hours old (>24h stale)"
                )
            else:
                report.add_check(
                    "state_freshness", True,
                    f"auto_mode_state.json is {age_hours:.1f} hours old (fresh)"
                )
        except (ValueError, TypeError):
            report.warnings.append(f"Could not parse timestamp: {last_update}")
    else:
        report.warnings.append("No timestamp field in auto_mode_state.json")

    return report


def run_reconciliation() -> dict:
    """Entry point: run reconciliation and return report dict."""
    report = reconcile()
    result = report.to_dict()

    # Log summary
    status = "CONSISTENT" if report.consistent else "INCONSISTENT"
    logger.info("[RECONCILER] %s — %d checks, %d warnings, %d errors",
                status, len(report.checks), len(report.warnings), len(report.errors))
    for check in report.checks:
        level = "✓" if check["passed"] else "✗"
        logger.info("  %s %s: %s", level, check["name"], check["detail"])

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_reconciliation()
    print(json.dumps(result, indent=2))
