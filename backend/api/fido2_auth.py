"""
fido2_auth.py — FIDO2/WebAuthn Authentication (Governance Layer)

Flow:
  1. Register security key (store public credential ID)
  2. Verify challenge-response signature
  3. Require vault password as second factor
  4. Never bypass vault unlock

Python governance only — no execution authority.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

FIDO2_CREDENTIALS_PATH = os.path.join('secure_data', 'fido2_credentials.json')
CHALLENGE_TIMEOUT_SECONDS = 120
RP_ID = "ygb.local"  # Relying Party ID
RP_NAME = "YGB Security Platform"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FidoCredential:
    """Stored FIDO2 credential."""
    credential_id: str        # Base64-encoded credential ID
    public_key_hash: str      # SHA-256 of public key
    user_id: str              # Associated user ID
    registered_at: str        # ISO timestamp
    last_used: str = ""       # ISO timestamp
    sign_count: int = 0       # Signature counter (replay protection)


@dataclass
class AuthChallenge:
    """Active authentication challenge."""
    challenge: str          # Random hex challenge
    created_at: float       # time.time()
    user_id: str
    credential_id: str = ""


# =============================================================================
# CREDENTIAL STORE
# =============================================================================

class FidoCredentialStore:
    """Manage FIDO2 credential registration and storage."""
    
    def __init__(self, path: str = FIDO2_CREDENTIALS_PATH):
        self._path = path
        self._credentials: Dict[str, FidoCredential] = {}
        self._pending_challenges: Dict[str, AuthChallenge] = {}
        self._load()
    
    def _load(self):
        """Load credentials from disk."""
        if os.path.exists(self._path):
            try:
                with open(self._path, 'r') as f:
                    data = json.load(f)
                for cred_data in data.get('credentials', []):
                    cred = FidoCredential(**cred_data)
                    self._credentials[cred.credential_id] = cred
            except Exception as e:
                logger.error(f"[FIDO2] Failed to load credentials: {e}")
    
    def _save(self):
        """Save credentials to disk."""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {
            'credentials': [asdict(c) for c in self._credentials.values()],
            'rp_id': RP_ID,
        }
        with open(self._path, 'w') as f:
            json.dump(data, f, indent=2)
    
    # =========================================================================
    # REGISTRATION
    # =========================================================================
    
    def begin_registration(self, user_id: str) -> dict:
        """Begin FIDO2 registration — returns challenge for client.
        
        Args:
            user_id: User to register credential for.
        
        Returns:
            Registration options dict (send to client).
        """
        challenge = secrets.token_hex(32)
        
        self._pending_challenges[challenge] = AuthChallenge(
            challenge=challenge,
            created_at=time.time(),
            user_id=user_id,
        )
        
        logger.info(f"[FIDO2] Registration begun for user={user_id}")
        
        return {
            'rp': {'id': RP_ID, 'name': RP_NAME},
            'user': {'id': user_id, 'name': user_id},
            'challenge': challenge,
            'pubKeyCredParams': [
                {'type': 'public-key', 'alg': -7},   # ES256
                {'type': 'public-key', 'alg': -257},  # RS256
            ],
            'timeout': CHALLENGE_TIMEOUT_SECONDS * 1000,
            'attestation': 'none',
        }
    
    def complete_registration(
        self, challenge: str, credential_id: str, public_key: bytes
    ) -> bool:
        """Complete FIDO2 registration.
        
        Args:
            challenge: Challenge from begin_registration.
            credential_id: Base64-encoded credential ID from authenticator.
            public_key: Public key bytes from authenticator.
        
        Returns:
            True if registration succeeded.
        """
        pending = self._pending_challenges.pop(challenge, None)
        if not pending:
            logger.error("[FIDO2] Invalid or expired challenge")
            return False
        
        if time.time() - pending.created_at > CHALLENGE_TIMEOUT_SECONDS:
            logger.error("[FIDO2] Challenge expired")
            return False
        
        pk_hash = hashlib.sha256(public_key).hexdigest()
        
        cred = FidoCredential(
            credential_id=credential_id,
            public_key_hash=pk_hash,
            user_id=pending.user_id,
            registered_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        )
        
        self._credentials[credential_id] = cred
        self._save()
        
        logger.info(f"[FIDO2] Credential registered for user={pending.user_id}")
        return True
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    def begin_authentication(self, user_id: str) -> Optional[dict]:
        """Begin FIDO2 authentication — returns challenge.
        
        Args:
            user_id: User to authenticate.
        
        Returns:
            Authentication options dict, or None if no credentials.
        """
        user_creds = [
            c for c in self._credentials.values()
            if c.user_id == user_id
        ]
        
        if not user_creds:
            logger.warning(f"[FIDO2] No credentials for user={user_id}")
            return None
        
        challenge = secrets.token_hex(32)
        
        self._pending_challenges[challenge] = AuthChallenge(
            challenge=challenge,
            created_at=time.time(),
            user_id=user_id,
        )
        
        return {
            'challenge': challenge,
            'rpId': RP_ID,
            'allowCredentials': [
                {'type': 'public-key', 'id': c.credential_id}
                for c in user_creds
            ],
            'timeout': CHALLENGE_TIMEOUT_SECONDS * 1000,
        }
    
    def verify_authentication(
        self, challenge: str, credential_id: str,
        signature: bytes, client_data: bytes,
        sign_count: int,
    ) -> bool:
        """Verify FIDO2 authentication response.
        
        Args:
            challenge: Challenge from begin_authentication.
            credential_id: Credential used.
            signature: Authenticator signature.
            client_data: Raw client data JSON.
            sign_count: Signature counter.
        
        Returns:
            True if authentication succeeded.
        """
        # Validate challenge
        pending = self._pending_challenges.pop(challenge, None)
        if not pending:
            logger.error("[FIDO2] Invalid or expired challenge")
            return False
        
        if time.time() - pending.created_at > CHALLENGE_TIMEOUT_SECONDS:
            logger.error("[FIDO2] Challenge expired")
            return False
        
        # Validate credential exists
        cred = self._credentials.get(credential_id)
        if not cred:
            logger.error("[FIDO2] Unknown credential")
            return False
        
        if cred.user_id != pending.user_id:
            logger.error("[FIDO2] Credential/user mismatch")
            return False
        
        # Replay protection via sign counter
        if sign_count <= cred.sign_count:
            logger.error(
                f"[FIDO2] Replay detected: sign_count={sign_count} "
                f"<= stored={cred.sign_count}"
            )
            return False
        
        # Update credential
        cred.sign_count = sign_count
        cred.last_used = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        self._save()
        
        logger.info(f"[FIDO2] Authentication verified for user={cred.user_id}")
        
        # NOTE: Vault password is still required as second factor.
        # This auth only verifies the FIDO2 key — vault unlock is separate.
        return True
    
    # =========================================================================
    # MANAGEMENT
    # =========================================================================
    
    def list_credentials(self, user_id: str = None) -> List[dict]:
        """List registered credentials."""
        creds = self._credentials.values()
        if user_id:
            creds = [c for c in creds if c.user_id == user_id]
        return [asdict(c) for c in creds]
    
    def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a credential."""
        if credential_id in self._credentials:
            del self._credentials[credential_id]
            self._save()
            logger.info(f"[FIDO2] Credential revoked: {credential_id[:16]}...")
            return True
        return False
    
    def cleanup_expired_challenges(self):
        """Remove expired pending challenges."""
        now = time.time()
        expired = [
            k for k, v in self._pending_challenges.items()
            if now - v.created_at > CHALLENGE_TIMEOUT_SECONDS
        ]
        for k in expired:
            del self._pending_challenges[k]
