"""
lab_hunt_separator.py — LAB/HUNT Strict Isolation

Enforces complete separation between training (LAB) and execution (HUNT):
- No training data access during HUNT
- No execution capabilities during LAB
- No weight updates during HUNT
- No target interaction during LAB
"""

class LabHuntSeparator:
    """Enforces strict LAB/HUNT isolation boundaries."""
    
    ALLOW_CROSS_MODE_ACCESS = False
    
    def __init__(self):
        self._violations = 0
    
    def check_lab_action(self, current_mode: str, action: str) -> dict:
        """Check if a LAB-only action is allowed."""
        lab_actions = {
            "train", "update_weights", "merge_weights",
            "run_regression", "calibrate", "tune_threshold",
            "run_stress_test", "export_snapshot"
        }
        
        if action not in lab_actions:
            return {"allowed": False, "reason": f"UNKNOWN_LAB_ACTION: {action}"}
        
        if current_mode != "LAB":
            self._violations += 1
            return {
                "allowed": False,
                "reason": f"LAB_ONLY_ACTION '{action}' BLOCKED in {current_mode} mode"
            }
        
        return {"allowed": True, "reason": f"LAB_ACTION_OK: {action}"}
    
    def check_hunt_action(self, current_mode: str, action: str) -> dict:
        """Check if a HUNT-only action is allowed."""
        hunt_actions = {
            "scan_target", "analyze_endpoint", "evaluate_finding",
            "generate_report", "queue_review"
        }
        
        if action not in hunt_actions:
            return {"allowed": False, "reason": f"UNKNOWN_HUNT_ACTION: {action}"}
        
        if current_mode != "HUNT":
            self._violations += 1
            return {
                "allowed": False,
                "reason": f"HUNT_ONLY_ACTION '{action}' BLOCKED in {current_mode} mode"
            }
        
        return {"allowed": True, "reason": f"HUNT_ACTION_OK: {action}"}
    
    def check_forbidden(self, action: str) -> dict:
        """Check for universally forbidden actions."""
        forbidden = {
            "auto_submit", "unlock_authority", "bypass_governance",
            "disable_review", "target_specific_company",
            "negotiate_bounty", "exploit_target"
        }
        
        if action in forbidden:
            self._violations += 1
            return {
                "allowed": False,
                "reason": f"FORBIDDEN_ACTION: '{action}' is permanently blocked"
            }
        
        return {"allowed": True, "reason": f"ACTION_NOT_FORBIDDEN: {action}"}
    
    @property
    def violations(self) -> int:
        return self._violations
