"""
Operational Governance Tests
=============================

Tests for operational governance.
"""

import unittest
from pathlib import Path
import sys
import json
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.governance.human_factor_safety import (
    ConfidenceExplainer,
    RiskBand,
    ForcedAcknowledgmentManager,
    AlertFatigueCounter,
    NotificationRateLimiter,
)

from impl_v1.governance.model_registry import (
    ModelRegistry,
    ModelEntry,
)

from impl_v1.governance.incident_automation import (
    IncidentReportGenerator,
    IncidentType,
    AnnualRevalidationLock,
)

from impl_v1.governance.evolution_test import (
    EvolutionTestGenerator,
    EvolutionTestHarness,
)

from impl_v1.governance.human_override import (
    EmergencyOverrideManager,
)
from impl_v1.governance.governance_controller import (
    OperationalGovernanceController,
)


class TestHumanFactorSafety(unittest.TestCase):
    """Test human factor safety."""
    
    def test_confidence_explainer(self):
        """Explain confidence levels."""
        explainer = ConfidenceExplainer()
        result = explainer.explain(0.9)
        self.assertEqual(result.risk_band, RiskBand.HIGH)
    
    def test_forced_acknowledgment(self):
        """Forced acknowledgment flow."""
        manager = ForcedAcknowledgmentManager()
        request = manager.require_acknowledgment("critical", "Test report")
        self.assertTrue(manager.has_pending())
        
        manager.acknowledge(request.request_id, "operator1")
        self.assertFalse(manager.has_pending())
    
    def test_alert_fatigue(self):
        """Alert fatigue tracking."""
        counter = AlertFatigueCounter()
        for _ in range(5):
            counter.record_alert()
        metrics = counter.get_metrics()
        self.assertEqual(metrics.alerts_last_hour, 5)


class TestModelRegistry(unittest.TestCase):
    """Test model registry."""
    
    def test_is_registered(self):
        """Check registration status."""
        registry = ModelRegistry()
        registered, _ = registry.is_registered("ygb_vuln_detector_v1")
        self.assertTrue(registered)
    
    def test_unregistered_abort(self):
        """Unregistered model aborts."""
        registry = ModelRegistry()
        valid, msg = registry.validate_for_execution("fake_model")
        self.assertFalse(valid)
        self.assertIn("ABORT", msg)


class TestIncidentAutomation(unittest.TestCase):
    """Test incident automation."""
    
    def test_generate_report(self):
        """Generate incident report."""
        generator = IncidentReportGenerator()
        report = generator.generate_incident_report(
            IncidentType.DRIFT,
            "high",
            "Test drift",
        )
        self.assertIn("INC_", report.incident_id)


class TestEvolutionTest(unittest.TestCase):
    """Test evolution harness."""
    
    def test_generate_scenarios(self):
        """Generate evolution scenarios."""
        generator = EvolutionTestGenerator()
        scenarios = generator.generate_all_scenarios()
        self.assertEqual(len(scenarios), 4)


class TestHumanOverride(unittest.TestCase):
    """Test human override."""
    
    def test_dual_approval(self):
        """Dual approval required."""
        manager = EmergencyOverrideManager()
        manager.create_request("Test", "user1")
        
        # First approval
        success, msg = manager.approve("user2")
        self.assertTrue(success)
        self.assertIn("Awaiting second", msg)

        # Second approval
        success, msg = manager.approve("user3", gpg_signature="signed-approval")
        self.assertTrue(success)
        self.assertIn("APPROVED", msg)

    def test_second_approval_requires_signature(self):
        """Unsigned second approvals must be rejected."""
        manager = EmergencyOverrideManager()
        manager.create_request("Test", "user1")

        success, _ = manager.approve("user2")
        self.assertTrue(success)

        success, msg = manager.approve("user3")
        self.assertFalse(success)
        self.assertIn("GPG signature", msg)
    
    def test_self_approval_blocked(self):
        """Cannot approve own request."""
        manager = EmergencyOverrideManager()
        manager.create_request("Test", "user1")
        
        success, msg = manager.approve("user1")
        self.assertFalse(success)

    def test_misuse_ignores_old_override_history(self):
        """Old approvals outside the misuse window should not block governance."""
        with TemporaryDirectory() as tmp:
            override_file = Path(tmp) / "override.json"
            audit_log = Path(tmp) / "override_audit.jsonl"
            stale_ts = (
                datetime.now() - EmergencyOverrideManager.MISUSE_WINDOW - timedelta(minutes=1)
            ).isoformat()
            with open(audit_log, "w") as f:
                for _ in range(EmergencyOverrideManager.MISUSE_THRESHOLD + 2):
                    f.write(json.dumps({
                        "timestamp": stale_ts,
                        "action": "override_approved",
                        "details": {},
                    }) + "\n")

            with patch.object(EmergencyOverrideManager, "OVERRIDE_FILE", override_file), \
                 patch.object(EmergencyOverrideManager, "AUDIT_LOG", audit_log):
                manager = EmergencyOverrideManager()
                misuse, issues = manager.check_for_misuse()

            self.assertFalse(misuse)
            self.assertEqual(issues, [])

    def test_misuse_blocks_recent_override_spike(self):
        """Recent approvals above threshold should still trigger misuse detection."""
        with TemporaryDirectory() as tmp:
            override_file = Path(tmp) / "override.json"
            audit_log = Path(tmp) / "override_audit.jsonl"
            fresh_ts = datetime.now().isoformat()
            with open(audit_log, "w") as f:
                for _ in range(EmergencyOverrideManager.MISUSE_THRESHOLD + 1):
                    f.write(json.dumps({
                        "timestamp": fresh_ts,
                        "action": "override_approved",
                        "details": {},
                    }) + "\n")

            with patch.object(EmergencyOverrideManager, "OVERRIDE_FILE", override_file), \
                 patch.object(EmergencyOverrideManager, "AUDIT_LOG", audit_log):
                manager = EmergencyOverrideManager()
                misuse, issues = manager.check_for_misuse()

            self.assertTrue(misuse)
            self.assertTrue(issues)

    def test_governance_blocks_pending_override_lane(self):
        """Governance must not report auto-mode safe with a pending override."""
        with TemporaryDirectory() as tmp:
            override_file = Path(tmp) / "override.json"
            audit_log = Path(tmp) / "override_audit.jsonl"
            state_file = Path(tmp) / "governance_state.json"

            with patch.object(EmergencyOverrideManager, "OVERRIDE_FILE", override_file), \
                 patch.object(EmergencyOverrideManager, "AUDIT_LOG", audit_log), \
                 patch.object(OperationalGovernanceController, "STATE_FILE", state_file):
                controller = OperationalGovernanceController()
                controller.override_manager.create_request("Test", "user1")
                status = controller.check_governance()

            self.assertFalse(status.auto_mode_safe)
            self.assertFalse(status.checks["override_lane_clear"])


if __name__ == "__main__":
    unittest.main()
