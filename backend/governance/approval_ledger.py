"""
APPROVAL LEDGER — Append-Only Immutable Certification Log
=========================================================
Rules:
  - Certification requires signed approval token (not boolean)
  - Token stored in append-only ledger
  - Ledger hash verified before field freeze
  - All approval events logged immutably
  - No boolean flags allowed for human approval
  - Anti-replay: nonce, expiration, model_hash
  - Reject: duplicate nonce, expired tokens, field mismatch, reuse
  - Key rotation: key_id, multi-key support, revocation list
  - Private keys loaded from YGB_KEY_DIR (outside source tree)
=========================================================
"""

import hmac
import hashlib
import json
import os
import time
import uuid
from typing import Optional


# ===========================================================
# KEY MANAGER — Multi-key support with rotation & revocation
# ===========================================================

class KeyManager:
    """Manages signing keys with rotation and revocation.

    Keys are loaded from:
      1. YGB_KEY_DIR env var (directory of key files)
      2. YGB_APPROVAL_SECRET env var (fallback single key)
      3. Hardcoded default (dev only)

    Key files: <key_id>.key (raw secret bytes)
    Revocation: revoked_keys.json (list of revoked key_ids)
    """

    DEFAULT_KEY_ID = "ygb-key-v1"
    DEFAULT_SECRET = b"ygb-approval-key-v1"

    def __init__(self):
        self._keys: dict[str, bytes] = {}
        self._revoked: set[str] = set()
        self._active_key_id: str = self.DEFAULT_KEY_ID
        self._load_keys()

    def _load_keys(self) -> None:
        """Load keys from filesystem or environment."""
        key_dir = os.environ.get("YGB_KEY_DIR", "")

        if key_dir and os.path.isdir(key_dir):
            # Load all .key files
            for fname in os.listdir(key_dir):
                if fname.endswith(".key"):
                    key_id = fname[:-4]
                    path = os.path.join(key_dir, fname)
                    with open(path, "rb") as f:
                        self._keys[key_id] = f.read().strip()
                    # Most recently loaded becomes active
                    self._active_key_id = key_id

            # Load revocation list
            revoke_path = os.path.join(key_dir, "revoked_keys.json")
            if os.path.exists(revoke_path):
                with open(revoke_path, "r") as f:
                    revoked = json.load(f)
                    if isinstance(revoked, list):
                        self._revoked = set(revoked)
        else:
            # Fallback: env var or default
            secret = os.environ.get("YGB_APPROVAL_SECRET", "").encode()
            if secret:
                self._keys[self.DEFAULT_KEY_ID] = secret
            else:
                self._keys[self.DEFAULT_KEY_ID] = self.DEFAULT_SECRET

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def get_signing_key(self) -> tuple[str, bytes]:
        """Get the active signing key. Returns (key_id, secret)."""
        if self._active_key_id in self._revoked:
            raise ValueError(f"ACTIVE_KEY_REVOKED: {self._active_key_id}")
        key = self._keys.get(self._active_key_id)
        if not key:
            raise ValueError(f"ACTIVE_KEY_MISSING: {self._active_key_id}")
        return self._active_key_id, key

    def get_verification_key(self, key_id: str) -> Optional[bytes]:
        """Get key for verification by key_id. Returns None if unknown."""
        return self._keys.get(key_id)

    def is_revoked(self, key_id: str) -> bool:
        """Check if a key_id has been revoked."""
        return key_id in self._revoked

    def revoke_key(self, key_id: str) -> None:
        """Revoke a key_id. Tokens signed with this key will be rejected."""
        self._revoked.add(key_id)

    def add_key(self, key_id: str, secret: bytes) -> None:
        """Register a new key for signing/verification."""
        self._keys[key_id] = secret

    @property
    def revoked_keys(self) -> set:
        return set(self._revoked)

    @property
    def available_key_ids(self) -> list:
        return list(self._keys.keys())


# ===========================================================
# APPROVAL TOKEN
# ===========================================================

class ApprovalToken:
    """Signed, non-boolean approval token with anti-replay fields."""

    def __init__(self, field_id: int, approver_id: str, reason: str,
                 timestamp: float, signature: str,
                 nonce: str = "", model_hash: str = "",
                 expiration_window: float = 3600.0,
                 key_id: str = ""):
        self.field_id = field_id
        self.approver_id = approver_id
        self.reason = reason
        self.timestamp = timestamp
        self.signature = signature
        self.nonce = nonce
        self.model_hash = model_hash
        self.expiration_window = expiration_window
        self.key_id = key_id

    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "approver_id": self.approver_id,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "nonce": self.nonce,
            "model_hash": self.model_hash,
            "expiration_window": self.expiration_window,
            "key_id": self.key_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ApprovalToken":
        return cls(
            field_id=d["field_id"],
            approver_id=d["approver_id"],
            reason=d["reason"],
            timestamp=d["timestamp"],
            signature=d["signature"],
            nonce=d.get("nonce", ""),
            model_hash=d.get("model_hash", ""),
            expiration_window=d.get("expiration_window", 3600.0),
            key_id=d.get("key_id", ""),
        )


class ApprovalLedger:
    """Append-only, hash-chained approval ledger with anti-replay + key rotation."""

    # Default token expiration window (seconds)
    DEFAULT_EXPIRATION = 3600.0  # 1 hour

    def __init__(self, ledger_path: str = "data/approval_ledger.jsonl",
                 key_manager: Optional[KeyManager] = None):
        self._path = ledger_path
        self._entries: list[dict] = []
        self._chain_hash = "0" * 64  # genesis hash
        self._used_nonces: set[str] = set()
        self._used_signatures: set[str] = set()
        self._key_mgr = key_manager or KeyManager()

    @property
    def key_manager(self) -> KeyManager:
        return self._key_mgr

    # ---------------------------------------------------------
    # SIGN — create HMAC signature for approval
    # ---------------------------------------------------------
    def sign_approval(self, field_id: int, approver_id: str,
                      reason: str, model_hash: str = "",
                      expiration_window: float = 0.0) -> ApprovalToken:
        """Create a signed approval token. NOT a boolean flag."""
        if not approver_id:
            raise ValueError("APPROVAL_REJECTED: approver_id required")
        if not reason:
            raise ValueError("APPROVAL_REJECTED: reason required")

        key_id, secret = self._key_mgr.get_signing_key()

        timestamp = time.time()
        nonce = uuid.uuid4().hex
        exp = expiration_window if expiration_window > 0 else self.DEFAULT_EXPIRATION

        payload = (f"{field_id}:{approver_id}:{reason}:{timestamp}"
                   f":{nonce}:{model_hash}:{exp}:{key_id}")
        signature = hmac.new(
            secret, payload.encode(), hashlib.sha256
        ).hexdigest()

        return ApprovalToken(
            field_id, approver_id, reason, timestamp, signature,
            nonce=nonce, model_hash=model_hash, expiration_window=exp,
            key_id=key_id,
        )

    # ---------------------------------------------------------
    # VERIFY — check token signature using key_id
    # ---------------------------------------------------------
    def verify_token(self, token: ApprovalToken) -> bool:
        """Verify HMAC signature on approval token using its key_id."""
        key_id = token.key_id or KeyManager.DEFAULT_KEY_ID
        secret = self._key_mgr.get_verification_key(key_id)
        if secret is None:
            return False  # unknown key_id

        payload = (f"{token.field_id}:{token.approver_id}:{token.reason}:{token.timestamp}"
                   f":{token.nonce}:{token.model_hash}:{token.expiration_window}:{key_id}")
        expected = hmac.new(
            secret, payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, token.signature)

    # ---------------------------------------------------------
    # ANTI-REPLAY VALIDATION
    # ---------------------------------------------------------
    def validate_anti_replay(self, token: ApprovalToken,
                              expected_field_id: int = -1) -> dict:
        """Full anti-replay validation with key revocation check."""
        # 0. Check key revocation
        key_id = token.key_id or KeyManager.DEFAULT_KEY_ID
        if self._key_mgr.is_revoked(key_id):
            return {"valid": False, "reason": f"KEY_REVOKED: {key_id}"}

        # 1. Verify signature
        if not self.verify_token(token):
            return {"valid": False, "reason": "INVALID_SIGNATURE"}

        # 2. Reject duplicate nonce
        if token.nonce in self._used_nonces:
            return {"valid": False, "reason": "DUPLICATE_NONCE"}

        # 3. Reject reused signature
        if token.signature in self._used_signatures:
            return {"valid": False, "reason": "REUSED_TOKEN"}

        # 4. Reject expired tokens
        now = time.time()
        age = now - token.timestamp
        if age > token.expiration_window:
            return {"valid": False, "reason": f"TOKEN_EXPIRED: {age:.0f}s > {token.expiration_window:.0f}s"}

        # 5. Reject negative timestamp (future attack)
        if age < -60:  # 60s clock skew tolerance
            return {"valid": False, "reason": "FUTURE_TIMESTAMP"}

        # 6. Reject field mismatch (if specified)
        if expected_field_id >= 0 and token.field_id != expected_field_id:
            return {"valid": False,
                    "reason": f"FIELD_MISMATCH: token={token.field_id} expected={expected_field_id}"}

        return {"valid": True, "reason": "OK"}

    # ---------------------------------------------------------
    # APPEND — add entry to ledger (append-only)
    # ---------------------------------------------------------
    def append(self, token: ApprovalToken,
               expected_field_id: int = -1) -> dict:
        """Append approval to ledger. Immutable — entries never modified."""
        validation = self.validate_anti_replay(token, expected_field_id)
        if not validation["valid"]:
            raise ValueError(f"REPLAY_REJECTED: {validation['reason']}")

        self._used_nonces.add(token.nonce)
        self._used_signatures.add(token.signature)

        entry = {
            "sequence": len(self._entries),
            "token": token.to_dict(),
            "prev_hash": self._chain_hash,
            "entry_hash": "",
            "appended_at": time.time()
        }

        entry_data = json.dumps(
            {k: v for k, v in entry.items() if k != "entry_hash"},
            sort_keys=True
        )
        entry["entry_hash"] = hashlib.sha256(entry_data.encode()).hexdigest()
        self._chain_hash = entry["entry_hash"]

        self._entries.append(entry)
        self._persist(entry)

        return entry

    # ---------------------------------------------------------
    # VERIFY CHAIN — validate entire ledger integrity
    # ---------------------------------------------------------
    def verify_chain(self) -> bool:
        """Verify hash chain integrity. Returns False if tampered."""
        prev_hash = "0" * 64

        for entry in self._entries:
            if entry["prev_hash"] != prev_hash:
                return False

            entry_data = json.dumps(
                {k: v for k, v in entry.items() if k != "entry_hash"},
                sort_keys=True
            )
            computed = hashlib.sha256(entry_data.encode()).hexdigest()
            if computed != entry["entry_hash"]:
                return False

            prev_hash = entry["entry_hash"]

        return True

    # ---------------------------------------------------------
    # QUERY — find approval for field
    # ---------------------------------------------------------
    def get_approval(self, field_id: int) -> Optional[dict]:
        """Get latest approval entry for field."""
        for entry in reversed(self._entries):
            if entry["token"]["field_id"] == field_id:
                return entry
        return None

    def has_approval(self, field_id: int) -> bool:
        """Check if field has been approved."""
        return self.get_approval(field_id) is not None

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def chain_hash(self) -> str:
        return self._chain_hash

    # ---------------------------------------------------------
    # PERSISTENCE — append-only file
    # ---------------------------------------------------------
    def _persist(self, entry: dict) -> None:
        """Append entry to file. Creates directory if needed."""
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def load(self) -> None:
        """Load existing ledger from file."""
        self._entries = []
        self._chain_hash = "0" * 64
        self._used_nonces = set()
        self._used_signatures = set()

        if not os.path.exists(self._path):
            return

        with open(self._path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    self._entries.append(entry)
                    self._chain_hash = entry["entry_hash"]
                    # Rebuild anti-replay sets
                    token_data = entry.get("token", {})
                    nonce = token_data.get("nonce", "")
                    sig = token_data.get("signature", "")
                    if nonce:
                        self._used_nonces.add(nonce)
                    if sig:
                        self._used_signatures.add(sig)
