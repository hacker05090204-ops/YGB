"""
Coverage boost round 12 — final push to 95%.
Only verified-working tests included.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. mode_controller.py — _load_state JSON decode error (lines 98-99)
# ---------------------------------------------------------------------------

class TestModeControllerLoadState(unittest.TestCase):
    def test_load_state_corrupted_json(self):
        from backend.governance.mode_controller import ModeController
        tmp = tempfile.mkdtemp()
        try:
            state_path = os.path.join(tmp, "mode_state.json")
            with open(state_path, "w") as f:
                f.write("{bad json!!")
            ctrl = ModeController(state_path=state_path)
            # Should fall back to IDLE mode
            self.assertEqual(ctrl.mode.value, "IDLE")
        finally:
            shutil.rmtree(tmp)

    def test_load_state_invalid_mode_value(self):
        from backend.governance.mode_controller import ModeController
        tmp = tempfile.mkdtemp()
        try:
            state_path = os.path.join(tmp, "mode_state.json")
            with open(state_path, "w") as f:
                json.dump({"mode": "NONEXISTENT_MODE"}, f)
            ctrl = ModeController(state_path=state_path)
            self.assertEqual(ctrl.mode.value, "IDLE")
        finally:
            shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# 2. report_similarity.py — log_potential_duplicate JSONDecodeError (126-127)
# ---------------------------------------------------------------------------

class TestReportSimilarityLogCorrupted(unittest.TestCase):
    def test_log_potential_duplicate_corrupted_log(self):
        from backend.governance import report_similarity as rs
        tmp = tempfile.mkdtemp()
        corrupted_log = os.path.join(tmp, "similarity.json")
        with open(corrupted_log, "w") as f:
            f.write("{bad json!!")
        try:
            with patch.object(rs, 'SIMILARITY_LOG', corrupted_log):
                rs.log_potential_duplicate("RPT-NEW", "RPT-OLD", 0.92)
            with open(corrupted_log) as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
        finally:
            shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# 3. integrity_bridge.py — GovernanceIntegrityReader.read_state exception (422-423)
# ---------------------------------------------------------------------------

class TestIntegrityBridgeReadState(unittest.TestCase):
    def test_read_state_corrupted_file(self):
        from backend.integrity.integrity_bridge import GovernanceIntegrityReader
        tmp = tempfile.mkdtemp()
        try:
            state_path = Path(tmp) / "governance_state.json"
            with open(state_path, "w") as f:
                f.write("{corrupted!")
            reader = GovernanceIntegrityReader(state_path=state_path)
            result = reader.read_state()
            self.assertFalse(result["auto_mode_safe"])
        finally:
            shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# 4. vault_session.py — remaining edge cases (lines 43-44)
# ---------------------------------------------------------------------------

class TestVaultSessionEdge(unittest.TestCase):
    def test_vault_unlock_session_expired(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session', return_value=None):
            result = vault_unlock("expired-token", "any-pass")
        self.assertFalse(result.get("success", False))


# ---------------------------------------------------------------------------
# 5. report_draft_assistant.py — remaining (line 51)
# ---------------------------------------------------------------------------

class TestReportDraftAssistant(unittest.TestCase):
    def test_run_tests(self):
        try:
            from backend.governance.report_draft_assistant import run_tests
        except ImportError as exc:
            self.skipTest(f"report_draft_assistant.run_tests unavailable: {exc}")
        result = run_tests()
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
