"""
Final Gate Controller
======================

AUTO_MODE_SAFE remains TRUE only if:
- All previous gates passed
- No rare-class collapse
- No entropy anomaly
- No P99 regression
- No shadow disagreement
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# GATE STATUS
# =============================================================================

@dataclass
class GateStatus:
    """Status of a single gate."""
    name: str
    passed: bool
    details: dict


# =============================================================================
# FINAL GATE CONTROLLER
# =============================================================================

class FinalGateController:
    """Controller for all safety gates."""
    
    STATE_FILE = Path("reports/final_gate_state.json")
    
    REQUIRED_GATES = [
        "calibration",
        "rare_class_stability",
        "representation_integrity",
        "adversarial_robustness",
        "p99_performance",
        "stress_test",
        "shadow_mode",
    ]
    
    def __init__(self):
        self.gates: Dict[str, GateStatus] = {}
        self._load_state()
    
    def _load_state(self) -> None:
        """Load gate state from file."""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, "r") as f:
                    data = json.load(f)
                for name, status in data.get("gates", {}).items():
                    self.gates[name] = GateStatus(
                        name=name,
                        passed=status["passed"],
                        details=status["details"],
                    )
            except Exception:
                pass
    
    def _save_state(self) -> None:
        """Save gate state to file."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.STATE_FILE, "w") as f:
            json.dump({
                "gates": {
                    name: {"passed": g.passed, "details": g.details}
                    for name, g in self.gates.items()
                },
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)
    
    def set_gate(self, name: str, passed: bool, details: dict = None) -> None:
        """Set a gate status."""
        self.gates[name] = GateStatus(
            name=name,
            passed=passed,
            details=details or {},
        )
        self._save_state()
    
    def check_all_gates(self) -> Tuple[bool, Dict[str, bool]]:
        """
        Check if all required gates are passed.
        
        Returns:
            Tuple of (all_passed, gate_status_dict)
        """
        status = {}
        
        for gate in self.REQUIRED_GATES:
            if gate in self.gates:
                status[gate] = self.gates[gate].passed
            else:
                status[gate] = False  # Missing = failed
        
        all_passed = all(status.values())
        return all_passed, status
    
    def get_auto_mode_safe(self) -> Tuple[bool, str]:
        """
        Determine if AUTO_MODE_SAFE = TRUE.
        
        Returns:
            Tuple of (is_safe, reason)
        """
        all_passed, gate_status = self.check_all_gates()
        
        if all_passed:
            return True, "ALL GATES PASSED - AUTO_MODE_SAFE = TRUE"
        
        failed = [g for g, passed in gate_status.items() if not passed]
        return False, f"GATES FAILED: {', '.join(failed)} - AUTO_MODE_SAFE = FALSE"
    
    def get_full_report(self) -> dict:
        """Get full gate report."""
        all_passed, gate_status = self.check_all_gates()
        is_safe, reason = self.get_auto_mode_safe()
        
        return {
            "auto_mode_safe": is_safe,
            "reason": reason,
            "gates_passed": sum(gate_status.values()),
            "gates_required": len(self.REQUIRED_GATES),
            "gate_status": gate_status,
            "gate_details": {
                name: g.details for name, g in self.gates.items()
            },
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# GATE INTEGRATION
# =============================================================================

def update_from_rare_class(monitor) -> GateStatus:
    """Update gate from RareClassStabilityMonitor."""
    stable, details = monitor.check_stability()
    return GateStatus("rare_class_stability", stable, details)


def update_from_representation(monitor) -> GateStatus:
    """Update gate from RepresentationIntegrityMonitor."""
    has_suspicious, count = monitor.has_suspicious_checkpoints()
    return GateStatus(
        "representation_integrity",
        not has_suspicious,
        {"suspicious_count": count},
    )


def update_from_adversarial(tester) -> GateStatus:
    """Update gate from AdversarialDriftTester."""
    should_disable, reason = tester.should_disable_auto_mode()
    return GateStatus(
        "adversarial_robustness",
        not should_disable,
        {"reason": reason},
    )


def update_from_performance(tracker) -> GateStatus:
    """Update gate from PerformanceTracker."""
    met, details = tracker.check_thresholds()
    return GateStatus("p99_performance", met, details)


def update_from_stress(tester) -> GateStatus:
    """Update gate from AutoModeStressTester."""
    passed, failed = tester.all_tests_passed()
    return GateStatus("stress_test", passed, {"failed_tests": failed})


def update_from_shadow(validator) -> GateStatus:
    """Update gate from ShadowModeValidator."""
    should_disable, reason = validator.should_disable_auto_mode()
    return GateStatus("shadow_mode", not should_disable, {"reason": reason})
