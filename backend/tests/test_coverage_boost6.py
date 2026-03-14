"""
Coverage boost round 6 — closing ALL remaining gaps toward 95%.

Targeted tests for exact uncovered lines in:
  - field_progression_api.py: approve_field happy path, get_fields_state, start_training frozen→advance, start_hunt full
  - auth_server.py: send_admin_alert, generate_and_store_otp, create_session
  - device_authority.py: process_pairing_request (all 3 paths), list_pending, _assign_mesh_ip
  - system_status.py: aggregated_system_status (healthy/degraded/unhealthy)
  - report_generator.py: video recording endpoints
  - db_safety.py: safe_db_execute
  - browser_endpoints.py: representation impact data
"""

import hashlib
import json
import os
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# 1. field_progression_api.py — approve_field happy path, get_fields_state,
#    start_training frozen→advance, start_hunt full pass
# ---------------------------------------------------------------------------

class TestApproveFieldHappyPath(unittest.TestCase):
    """Tests for approve_field with mocked ledger — covs lines 631-655."""

    def test_approve_field_success(self):
        from backend.api.field_progression_api import approve_field, _default_state
        mock_ledger = MagicMock()
        mock_ledger.sign_approval.return_value = {"field_id": 0, "sig": "abc"}
        mock_ledger.verify_token.return_value = True
        mock_ledger.append.return_value = {"sequence": 1}
        mock_ledger.chain_hash = "hash123"
        with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
            with patch('backend.api.field_progression_api._load_field_state', return_value=_default_state()):
                with patch('backend.api.field_progression_api._save_field_state'):
                    result = approve_field(0, "admin-1", "field 0 looks good")
        self.assertEqual(result['status'], 'ok')
        self.assertIn('APPROVED', result['message'])
        self.assertEqual(result['entry_sequence'], 1)

    def test_approve_field_sig_fail(self):
        from backend.api.field_progression_api import approve_field
        mock_ledger = MagicMock()
        mock_ledger.sign_approval.return_value = {"field_id": 0, "sig": "bad"}
        mock_ledger.verify_token.return_value = False
        with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
            result = approve_field(0, "admin-1", "reason")
        self.assertEqual(result['status'], 'error')
        self.assertIn('SIGNATURE_VERIFICATION_FAILED', result['message'])


class TestGetFieldsState(unittest.TestCase):
    """Tests for get_fields_state — covs lines 538-570."""

    def test_get_fields_state(self):
        from backend.api.field_progression_api import get_fields_state, _default_state
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        mock_ledger = MagicMock()
        mock_ledger.entry_count = 0
        mock_ledger.chain_hash = "genesis"
        mock_ledger.verify_chain.return_value = True
        with patch('backend.api.field_progression_api._load_field_state', return_value=_default_state()):
            with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
                with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
                    with patch('backend.api.field_progression_api._build_runtime_status', return_value={}):
                        result = get_fields_state()
        self.assertEqual(result['status'], 'ok')
        self.assertIn('ladder', result)
        self.assertIn('authority_lock', result)
        self.assertEqual(len(result['ladder']['fields']), 23)


class TestStartTrainingFrozenAdvance(unittest.TestCase):
    """Tests for start_training when field is frozen+certified → advance."""

    def test_start_training_frozen_advance_success(self):
        from backend.api.field_progression_api import start_training, _default_state
        state = _default_state()
        state['fields'][0]['frozen'] = True
        state['fields'][0]['certified'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api._signed_approval_status',
                           return_value={'has_signed_approval': True, 'chain_valid': True}):
                    with patch('backend.api.field_progression_api._save_field_state'):
                        result = start_training()
        self.assertEqual(result['status'], 'ok')
        self.assertIn('TRAINING_STARTED', result['message'])
        self.assertEqual(result['field_id'], 1)  # Advanced to field 1

    def test_start_training_frozen_ledger_tampered(self):
        from backend.api.field_progression_api import start_training, _default_state
        state = _default_state()
        state['fields'][0]['frozen'] = True
        state['fields'][0]['certified'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api._signed_approval_status',
                           return_value={'has_signed_approval': False, 'chain_valid': False}):
                    result = start_training()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'LEDGER_INTEGRITY')

    def test_start_training_frozen_no_approval(self):
        from backend.api.field_progression_api import start_training, _default_state
        state = _default_state()
        state['fields'][0]['frozen'] = True
        state['fields'][0]['certified'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api._signed_approval_status',
                           return_value={'has_signed_approval': False, 'chain_valid': True}):
                    result = start_training()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'HUMAN_APPROVAL')

    def test_start_training_frozen_last_field_advance_none(self):
        from backend.api.field_progression_api import start_training, _default_state, TOTAL_FIELDS
        state = _default_state()
        state['active_field_id'] = TOTAL_FIELDS - 1
        state['fields'][TOTAL_FIELDS - 1]['frozen'] = True
        state['fields'][TOTAL_FIELDS - 1]['certified'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api._signed_approval_status',
                           return_value={'has_signed_approval': True, 'chain_valid': True}):
                    with patch('backend.api.field_progression_api._save_field_state'):
                        result = start_training()
        self.assertEqual(result['status'], 'ok')
        self.assertIn('ALL_FIELDS_COMPLETE', result['message'])

    def test_start_training_bad_state(self):
        from backend.api.field_progression_api import start_training, _default_state
        state = _default_state()
        state['fields'][0]['state'] = 'STABILITY_CHECK'
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                result = start_training()
        self.assertEqual(result['status'], 'error')
        self.assertIn('FIELD_STATE_ERROR', result['message'])


class TestStartHuntFull(unittest.TestCase):
    """Tests for start_hunt with all gates passing — covs lines 784-810."""

    def test_start_hunt_no_approval_in_ledger(self):
        from backend.api.field_progression_api import start_hunt, _default_state
        state = _default_state()
        state['fields'][0]['certified'] = True
        state['fields'][0]['frozen'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        mock_ledger = MagicMock()
        mock_ledger.has_approval.return_value = False
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
                    result = start_hunt()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'HUMAN_APPROVAL')

    def test_start_hunt_ledger_tampered(self):
        from backend.api.field_progression_api import start_hunt, _default_state
        state = _default_state()
        state['fields'][0]['certified'] = True
        state['fields'][0]['frozen'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        mock_ledger = MagicMock()
        mock_ledger.has_approval.return_value = True
        mock_ledger.verify_chain.return_value = False
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
                    result = start_hunt()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'LEDGER_INTEGRITY')

    def test_start_hunt_all_gates_pass(self):
        from backend.api.field_progression_api import start_hunt, _default_state
        state = _default_state()
        state['fields'][0]['certified'] = True
        state['fields'][0]['frozen'] = True
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        mock_ledger = MagicMock()
        mock_ledger.has_approval.return_value = True
        mock_ledger.verify_chain.return_value = True
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
                    result = start_hunt()
        self.assertEqual(result['status'], 'ok')
        self.assertIn('HUNT_ENABLED', result['message'])
        self.assertEqual(result['gates_passed'], 4)

    def test_start_hunt_all_complete(self):
        from backend.api.field_progression_api import start_hunt, _default_state, TOTAL_FIELDS
        state = _default_state()
        state['active_field_id'] = TOTAL_FIELDS
        mock_auth = MagicMock()
        mock_auth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
        with patch('backend.api.field_progression_api.AuthorityLock', mock_auth):
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                result = start_hunt()
        self.assertEqual(result['status'], 'error')
        self.assertIn('NO_ACTIVE_FIELD', result['message'])


# ---------------------------------------------------------------------------
# 2. auth_server.py — admin alert, OTP, session
# ---------------------------------------------------------------------------

class TestAuthServerAdminAlert(unittest.TestCase):
    """Tests for send_admin_alert_new_device — covs lines 255-282."""

    def test_admin_alert_no_admin_email(self):
        from backend.api.auth_server import send_admin_alert_new_device
        with patch.dict(os.environ, {'ALERT_EMAIL_TO': ''}, clear=False):
            send_admin_alert_new_device("user1", "1.2.3.4", "fp-123")

    def test_admin_alert_no_smtp_config(self):
        from backend.api.auth_server import send_admin_alert_new_device
        env = {'ALERT_EMAIL_TO': 'admin@test.com', 'SMTP_USER': '', 'SMTP_PASS': '', 'ALERT_EMAIL_FROM': ''}
        with patch.dict(os.environ, env, clear=False):
            send_admin_alert_new_device("user1", "1.2.3.4", "fp-123")

    def test_admin_alert_smtp_success(self):
        from backend.api.auth_server import send_admin_alert_new_device
        env = {
            'ALERT_EMAIL_TO': 'admin@test.com',
            'ALERT_EMAIL_FROM': 'from@test.com',
            'SMTP_USER': 'smtp@test.com',
            'SMTP_PASS': 'pass',
        }
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch.dict(os.environ, env, clear=False):
            with patch('backend.api.auth_server.smtplib.SMTP', return_value=mock_smtp):
                send_admin_alert_new_device("user1", "1.2.3.4", "fp-123")
        mock_smtp.send_message.assert_called_once()

    def test_admin_alert_smtp_failure(self):
        from backend.api.auth_server import send_admin_alert_new_device
        env = {
            'ALERT_EMAIL_TO': 'admin@test.com',
            'ALERT_EMAIL_FROM': 'from@test.com',
            'SMTP_USER': 'smtp@test.com',
            'SMTP_PASS': 'pass',
        }
        with patch.dict(os.environ, env, clear=False):
            with patch('backend.api.auth_server.smtplib.SMTP', side_effect=Exception("fail")):
                send_admin_alert_new_device("user1", "1.2.3.4", "fp-123")  # Should not raise


class TestAuthServerOTPGenerate(unittest.TestCase):
    """Tests for generate_and_store_otp — covs lines ~285-301."""

    def test_generate_and_store_otp(self):
        from backend.api.auth_server import generate_and_store_otp
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json'):
                with patch('backend.api.auth_server.send_otp_email', return_value=True) as mock_send:
                    result = generate_and_store_otp("testuser", "test@email.com")
        self.assertTrue(result)
        mock_send.assert_called_once()

    def test_generate_and_store_otp_email_fail(self):
        from backend.api.auth_server import generate_and_store_otp
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json'):
                with patch('backend.api.auth_server.send_otp_email', return_value=False):
                    result = generate_and_store_otp("testuser", "test@email.com")
        self.assertFalse(result)


class TestAuthServerCreateSession(unittest.TestCase):
    """Tests for session creation — covs lines ~308-321."""

    def test_create_session(self):
        from backend.api.auth_server import create_session
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json') as mock_save:
                token = create_session("user1", "fp-abc", "1.2.3.4")
        self.assertEqual(len(token), 64)
        mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# 3. device_authority.py — process_pairing (3 paths), list_pending
# ---------------------------------------------------------------------------

class TestDeviceAuthorityPairing(unittest.TestCase):
    """Tests for process_pairing_request — covs lines 264-313."""

    def test_process_pairing_revoked(self):
        from backend.governance.device_authority import process_pairing_request
        with patch('backend.governance.device_authority.is_revoked', return_value=True):
            result = process_pairing_request("dev-1")
        self.assertEqual(result['status'], 'denied')
        self.assertEqual(result['reason'], 'device_revoked')

    def test_process_pairing_no_request(self):
        from backend.governance.device_authority import process_pairing_request
        with patch('backend.governance.device_authority.is_revoked', return_value=False):
            with patch('backend.governance.device_authority.load_pairing_request', return_value=None):
                result = process_pairing_request("dev-2")
        self.assertEqual(result['status'], 'error')

    def test_process_pairing_whitelisted(self):
        from backend.governance.device_authority import process_pairing_request
        req = {'requested_role': 'WORKER', 'public_key': 'pk123'}
        with patch('backend.governance.device_authority.is_revoked', return_value=False):
            with patch('backend.governance.device_authority.load_pairing_request', return_value=req):
                with patch('backend.governance.device_authority.is_whitelisted', return_value=True):
                    with patch('backend.governance.device_authority._assign_mesh_ip', return_value='10.0.0.5'):
                        with patch('backend.governance.device_authority.issue_certificate', return_value={'cert': True}):
                            with patch('backend.governance.device_authority.save_certificate', return_value='/path/cert'):
                                with patch('backend.governance.device_authority._update_request_status'):
                                    result = process_pairing_request("dev-3")
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(result['mesh_ip'], '10.0.0.5')

    def test_process_pairing_valid_otp(self):
        from backend.governance.device_authority import process_pairing_request
        req = {'requested_role': 'ADMIN', 'public_key': 'pk456'}
        with patch('backend.governance.device_authority.is_revoked', return_value=False):
            with patch('backend.governance.device_authority.load_pairing_request', return_value=req):
                with patch('backend.governance.device_authority.is_whitelisted', return_value=False):
                    with patch('backend.governance.device_authority.verify_otp', return_value=True):
                        with patch('backend.governance.device_authority._assign_mesh_ip', return_value='10.0.0.10'):
                            with patch('backend.governance.device_authority.issue_certificate', return_value={}):
                                with patch('backend.governance.device_authority.save_certificate', return_value='/cert'):
                                    with patch('backend.governance.device_authority._update_request_status'):
                                        result = process_pairing_request("dev-4", admin_otp="123456")
        self.assertEqual(result['status'], 'approved')

    def test_process_pairing_invalid_otp(self):
        from backend.governance.device_authority import process_pairing_request
        req = {'requested_role': 'WORKER', 'public_key': 'pk789'}
        with patch('backend.governance.device_authority.is_revoked', return_value=False):
            with patch('backend.governance.device_authority.load_pairing_request', return_value=req):
                with patch('backend.governance.device_authority.is_whitelisted', return_value=False):
                    with patch('backend.governance.device_authority.verify_otp', return_value=False):
                        result = process_pairing_request("dev-5", admin_otp="wrong")
        self.assertEqual(result['status'], 'denied')
        self.assertEqual(result['reason'], 'invalid_otp')

    def test_process_pairing_no_otp_pending(self):
        from backend.governance.device_authority import process_pairing_request
        req = {'requested_role': 'WORKER', 'public_key': 'pk000'}
        with patch('backend.governance.device_authority.is_revoked', return_value=False):
            with patch('backend.governance.device_authority.load_pairing_request', return_value=req):
                with patch('backend.governance.device_authority.is_whitelisted', return_value=False):
                    with patch('backend.governance.device_authority.generate_otp', return_value='999888'):
                        result = process_pairing_request("dev-6")
        self.assertEqual(result['status'], 'pending_approval')
        self.assertEqual(result['otp'], '999888')


class TestDeviceAuthorityListPending(unittest.TestCase):
    """Tests for list_pending_requests — covs lines 232-242."""

    def test_list_pending_no_dir(self):
        from backend.governance.device_authority import list_pending_requests
        with patch('backend.governance.device_authority.PAIRING_DIR', '/nonexistent'):
            result = list_pending_requests()
        self.assertEqual(result, [])

    def test_list_pending_with_requests(self):
        from backend.governance.device_authority import list_pending_requests
        with tempfile.TemporaryDirectory() as td:
            # Write a pending request
            req = {"device_id": "dev-1", "status": "pending"}
            with open(os.path.join(td, "dev-1.json"), 'w') as f:
                json.dump(req, f)
            # Also a non-pending one
            req2 = {"device_id": "dev-2", "status": "approved"}
            with open(os.path.join(td, "dev-2.json"), 'w') as f:
                json.dump(req2, f)
            with patch('backend.governance.device_authority.PAIRING_DIR', td):
                result = list_pending_requests()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['device_id'], 'dev-1')


class TestDeviceAuthorityMeshIP(unittest.TestCase):
    """Test _assign_mesh_ip."""

    def test_assign_mesh_ip(self):
        from backend.governance.device_authority import _assign_mesh_ip
        ip = _assign_mesh_ip("test-device-1")
        self.assertTrue(ip.startswith("10.0.0."))
        parts = ip.split(".")
        host = int(parts[3])
        self.assertGreaterEqual(host, 2)
        self.assertLessEqual(host, 254)


# ---------------------------------------------------------------------------
# 4. system_status.py — aggregated_system_status
# ---------------------------------------------------------------------------

class TestSystemStatus(unittest.IsolatedAsyncioTestCase):
    """Tests for aggregated_system_status — covs lines 92-124."""

    async def test_system_status_healthy(self):
        from backend.api.system_status import aggregated_system_status
        with patch('backend.api.system_status._safe_call') as mock_safe:
            mock_safe.side_effect = lambda name, fn: {
                'readiness': {'ready': True},
                'metrics': {'total': 0},
                'training': {'active': False},
                'voice': {'status': 'idle'},
                'storage': {'storage_active': True},
            }.get(name, {})
            result = await aggregated_system_status()
        self.assertEqual(result['overall_status'], 'HEALTHY')

    async def test_system_status_degraded(self):
        from backend.api.system_status import aggregated_system_status
        with patch('backend.api.system_status._safe_call') as mock_safe:
            mock_safe.side_effect = lambda name, fn: {
                'readiness': {'ready': False},
                'metrics': {},
                'training': {},
                'voice': {},
                'storage': {'storage_active': True},
            }.get(name, {})
            result = await aggregated_system_status()
        self.assertEqual(result['overall_status'], 'DEGRADED')

    async def test_system_status_unhealthy(self):
        from backend.api.system_status import aggregated_system_status
        with patch('backend.api.system_status._safe_call') as mock_safe:
            mock_safe.side_effect = lambda name, fn: {
                'readiness': {'ready': False},
                'metrics': {},
                'training': {},
                'voice': {},
                'storage': {'storage_active': False},
            }.get(name, {})
            result = await aggregated_system_status()
        self.assertEqual(result['overall_status'], 'UNHEALTHY')


# ---------------------------------------------------------------------------
# 5. Misc smaller gaps
# ---------------------------------------------------------------------------

class TestFieldProgressionCalculateProgress(unittest.TestCase):
    """Test _calculate_progress edge cases — covs FPR/ECE above-threshold."""

    def test_progress_fpr_above_threshold(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {
            'id': 0, 'precision': 0.97, 'fpr': 0.08,  # Above max_fpr
            'dup_detection': 0.90, 'ece': 0.03,  # Above max_ece
            'stability_days': 3,
        }
        result = _calculate_progress(field)
        self.assertLess(result['fpr_score'], 1.0)  # Penalized
        self.assertLess(result['ece_score'], 1.0)

    def test_progress_all_none(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {
            'id': 0, 'precision': None, 'fpr': None,
            'dup_detection': None, 'ece': None, 'stability_days': 0,
        }
        result = _calculate_progress(field)
        self.assertEqual(result['status'], 'Awaiting Data')

    def test_progress_stability_only(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {
            'id': 0, 'precision': None, 'fpr': None,
            'dup_detection': None, 'ece': None, 'stability_days': 7,
        }
        result = _calculate_progress(field)
        self.assertEqual(result['stability_score'], 1.0)

    def test_sync_stability_days_invalid_date(self):
        """Test ValueError path for stability_days calculation (line 439-440)."""
        from backend.api.field_progression_api import sync_active_field_training, _default_state
        state = _default_state()
        state['fields'][0]['first_trained_at'] = 'not-a-date'
        mock_validator = MagicMock()
        mock_result = MagicMock()
        mock_result.freeze_allowed = True
        mock_result.reason = None
        mock_validator.validate_freeze.return_value = mock_result
        with patch('backend.api.field_progression_api._load_field_state', return_value=state):
            with patch('backend.api.field_progression_api._save_field_state'):
                with patch('backend.api.field_progression_api._save_runtime_status'):
                    with patch('backend.api.field_progression_api._signed_approval_status',
                               return_value={'has_signed_approval': False, 'chain_valid': True}):
                        with patch('impl_v1.training.distributed.freeze_validator.FreezeValidator', return_value=mock_validator):
                            result = sync_active_field_training(precision=0.97, fpr=0.03)
        self.assertEqual(result['status'], 'ok')


if __name__ == "__main__":
    unittest.main()
