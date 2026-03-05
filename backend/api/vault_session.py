"""
vault_session.py — Vault Unlock Endpoint

POST /admin/vault-unlock
  - Validates admin session first
  - Receives vault_password from request body
  - Derives key via PBKDF2
  - Stores key in server memory
  - Returns unlock status

Frontend NEVER receives the vault key.
"""

import os
import json
import time

# =========================================================================
# PATHS
# =========================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
AUDIT_LOG_PATH = os.path.join(PROJECT_ROOT, 'secure_data', 'audit_log.json')


# =========================================================================
# AUDIT LOGGING
# =========================================================================

def _audit_log(action: str, ip: str = '', details: str = ''):
    """Log vault action to audit trail."""
    entry = {
        'timestamp': int(time.time()),
        'action': action,
        'ip': ip,
        'details': details,
    }
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
        with open(AUDIT_LOG_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except OSError:
        pass


# =========================================================================
# VAULT UNLOCK/LOCK API
# =========================================================================

def vault_unlock(vault_password: str, session_token: str = '',
                 ip: str = '0.0.0.0') -> dict:
    """Unlock the vault with admin password.

    Args:
        vault_password: The admin vault password.
        session_token: Active admin session token (REQUIRED — ADMIN role enforced).
        ip: Client IP address for audit logging.

    Returns:
        Status dict with unlock result.
    """
    from backend.security.vault_kdf import unlock_vault, is_vault_unlocked

    # ── MANDATORY session validation ──────────────────────────
    # session_token MUST be present and valid with ADMIN role.
    if not session_token:
        _audit_log('VAULT_UNLOCK_DENIED', ip, 'No session token provided')
        return {
            'status': 'unauthorized',
            'message': 'Valid admin session required — session token is mandatory',
        }

    from backend.api.admin_auth import validate_session, ROLE_ADMIN
    session = validate_session(session_token)
    if not session:
        _audit_log('VAULT_UNLOCK_DENIED', ip, 'Invalid or expired session')
        return {
            'status': 'unauthorized',
            'message': 'Valid admin session required',
        }

    # ── Enforce ADMIN role ────────────────────────────────────
    if session.get('role', '') != ROLE_ADMIN:
        _audit_log('VAULT_UNLOCK_DENIED', ip,
                    f'Insufficient role: {session.get("role", "none")}')
        return {
            'status': 'forbidden',
            'message': 'Vault unlock requires ADMIN role',
        }

    # Don't re-unlock if already unlocked
    if is_vault_unlocked():
        return {
            'status': 'ok',
            'vault_unlocked': True,
            'message': 'Vault already unlocked',
        }

    # Derive key and unlock
    if not vault_password:
        return {
            'status': 'error',
            'message': 'Vault password required',
        }

    success = unlock_vault(vault_password)

    if success:
        _audit_log('VAULT_UNLOCKED', ip,
                    f'By user={session.get("user_id", "?")} role=ADMIN')
        return {
            'status': 'ok',
            'vault_unlocked': True,
            'message': 'Vault unlocked successfully',
        }
    else:
        _audit_log('VAULT_UNLOCK_FAILED', ip, 'Key derivation failed')
        return {
            'status': 'error',
            'message': 'Vault unlock failed — invalid password',
        }



def vault_lock(session_token: str = '', ip: str = '0.0.0.0') -> dict:
    """Lock the vault and clear key from memory.

    Args:
        session_token: Active admin session token.
        ip: Client IP address.

    Returns:
        Status dict.
    """
    from backend.security.vault_kdf import lock_vault

    lock_vault()
    _audit_log('VAULT_LOCKED', ip, 'Vault key cleared from memory')

    return {
        'status': 'ok',
        'vault_unlocked': False,
        'message': 'Vault locked — key cleared from memory',
    }


def vault_status() -> dict:
    """Get vault unlock status (no sensitive data exposed)."""
    from backend.security.vault_kdf import is_vault_unlocked

    return {
        'status': 'ok',
        'vault_unlocked': is_vault_unlocked(),
    }
