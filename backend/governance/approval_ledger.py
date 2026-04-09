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
import logging
import os
import stat
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrityReport:
    entries_checked: int
    hash_chain_valid: bool
    first_broken_entry_id: Optional[str]
    checked_at: str


last_integrity_report: Optional[IntegrityReport] = None


def _integrity_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _integrity_entry_id(entry: dict) -> Optional[str]:
    if entry.get("entry_id"):
        return str(entry["entry_id"])
    if "sequence" in entry:
        return str(entry["sequence"])
    token = entry.get("token", {})
    if token.get("nonce"):
        return str(token["nonce"])
    return None


class LedgerIntegrityCheck:
    @staticmethod
    def _payload_without_hash(entry: dict) -> str:
        return json.dumps(
            {k: v for k, v in entry.items() if k not in {"entry_hash", "prev_hash"}},
            sort_keys=True,
        )

    @staticmethod
    def _legacy_payload(entry: dict) -> str:
        return json.dumps(
            {k: v for k, v in entry.items() if k != "entry_hash"},
            sort_keys=True,
        )

    @staticmethod
    def verify(entries: list) -> IntegrityReport:
        prev_hash = "0" * 64
        checked_at = _integrity_timestamp()

        for index, entry in enumerate(entries, start=1):
            entry_id = _integrity_entry_id(entry)
            if entry.get("prev_hash") != prev_hash:
                logger.critical(
                    "APPROVAL_LEDGER_INTEGRITY_BROKEN entry_id=%s reason=prev_hash_mismatch",
                    entry_id or "unknown",
                )
                return IntegrityReport(index, False, entry_id, checked_at)

            payload = LedgerIntegrityCheck._payload_without_hash(entry)
            computed_hash = hashlib.sha256(f"{prev_hash}{payload}".encode()).hexdigest()
            legacy_payload = LedgerIntegrityCheck._legacy_payload(entry)
            legacy_hash = hashlib.sha256(legacy_payload.encode()).hexdigest()
            if entry.get("entry_hash") not in {computed_hash, legacy_hash}:
                logger.critical(
                    "APPROVAL_LEDGER_INTEGRITY_BROKEN entry_id=%s reason=hash_mismatch",
                    entry_id or "unknown",
                )
                return IntegrityReport(index, False, entry_id, checked_at)

            prev_hash = str(entry.get("entry_hash", ""))

        return IntegrityReport(len(entries), True, None, checked_at)


def run_integrity_check() -> IntegrityReport:
    global last_integrity_report
    ledger = ApprovalLedger()
    ledger.load()
    last_integrity_report = LedgerIntegrityCheck.verify(list(ledger._entries))
    return last_integrity_report


# ===========================================================
# KEY MANAGER — Hardened multi-key with rotation & revocation
# ===========================================================

class KeyManager:
    """Manages signing keys with rotation, revocation, and security hardening.

    Keys are loaded from:
      1. YGB_KEY_DIR env var (directory of key files) — PREFERRED
      2. YGB_APPROVAL_SECRET env var (fallback single key in non-strict mode)

    Security:
      - Key files must not be world-readable (mode 600 on POSIX)
      - Key fingerprints logged on load (never the raw secret)
      - Rotation events stored in audit log
    """

    DEFAULT_KEY_ID = "ygb-key-v1"
    DEFAULT_SECRET = b"ygb-approval-key-v1"

    def __init__(self, strict: bool = None):
        self._keys: dict[str, bytes] = {}
        self._revoked: set[str] = set()
        self._active_key_id: str = self.DEFAULT_KEY_ID
        self._audit_log: list[dict] = []
        self._source: str = "unconfigured"
        self._key_dir: str = ""
        # Default to strict=True in production environments
        if strict is None:
            env = os.environ.get("YGB_ENV", "").lower()
            prod_flag = os.environ.get("YGB_PRODUCTION", "0")
            strict = (env == "production" or prod_flag == "1")
        self._strict: bool = strict
        self._load_keys()

    @staticmethod
    def _key_fingerprint(secret: bytes) -> str:
        """SHA-256 fingerprint of key (first 16 hex chars). Never logs raw key."""
        return hashlib.sha256(secret).hexdigest()[:16]

    @staticmethod
    def _check_file_permissions(path: str) -> tuple[bool, str]:
        """Check file is not world-readable. Returns (ok, reason)."""
        if os.name == 'nt':
            # Windows: trust NTFS ACLs — no POSIX permission model
            return True, "WINDOWS_NTFS"
        try:
            mode = os.stat(path).st_mode
            # Reject if group-readable or other-readable
            if mode & stat.S_IRGRP or mode & stat.S_IROTH:
                return False, f"INSECURE_PERMISSIONS: mode={oct(mode)} (must be 0o600)"
            return True, f"OK: mode={oct(mode)}"
        except OSError as e:
            return False, f"STAT_FAILED: {e}"

    def _log_audit(self, event: str, key_id: str, detail: str = "") -> None:
        """Record key rotation/revocation event."""
        entry = {
            "timestamp": time.time(),
            "event": event,
            "key_id": key_id,
            "detail": detail,
        }
        self._audit_log.append(entry)
        logger.info(f"KEY_AUDIT: {event} key_id={key_id} {detail}")

    def _load_keys(self) -> None:
        """Load keys from filesystem or environment with security checks."""
        key_dir = os.environ.get("YGB_KEY_DIR", "")
        self._key_dir = key_dir

        if key_dir and os.path.isdir(key_dir):
            self._source = "key_dir"
            loaded = 0
            # Load all .key files with permission checks
            for fname in sorted(os.listdir(key_dir)):
                if fname.endswith(".key"):
                    key_id = fname[:-4]
                    path = os.path.join(key_dir, fname)

                    # Permission check
                    perm_ok, perm_reason = self._check_file_permissions(path)
                    if not perm_ok:
                        self._log_audit("KEY_REJECTED", key_id, perm_reason)
                        logger.warning(
                            f"KEY_REJECTED: {key_id} — {perm_reason}"
                        )
                        continue

                    with open(path, "rb") as f:
                        secret = f.read().strip()

                    self._keys[key_id] = secret
                    fingerprint = self._key_fingerprint(secret)
                    self._active_key_id = key_id
                    self._log_audit(
                        "KEY_LOADED", key_id,
                        f"fingerprint={fingerprint} source={path}"
                    )
                    loaded += 1

            # Load revocation list
            revoke_path = os.path.join(key_dir, "revoked_keys.json")
            if os.path.exists(revoke_path):
                with open(revoke_path, "r") as f:
                    revoked = json.load(f)
                    if isinstance(revoked, list):
                        self._revoked = set(revoked)
                        for kid in self._revoked:
                            self._log_audit("KEY_REVOKED_ON_LOAD", kid)

            if loaded == 0 and self._strict:
                raise ValueError(
                    "KEY_STORAGE_ERROR: no valid keys in YGB_KEY_DIR"
                )
        else:
            if self._strict:
                raise ValueError(
                    "KEY_STORAGE_ERROR: YGB_KEY_DIR not set or not a directory "
                    "(strict mode rejects fallback keys)"
                )
            # Fallback: env var (dev mode only — no hardcoded default)
            secret_str = os.environ.get("YGB_APPROVAL_SECRET", "")
            if not secret_str:
                raise ValueError(
                    "APPROVAL_SECRET_MISSING: YGB_APPROVAL_SECRET env var is required. "
                    "Set it to a strong random secret (e.g. python -c \"import secrets; print(secrets.token_hex(32))\"). "
                    "For production, use YGB_KEY_DIR with key files instead."
                )
            self._keys[self.DEFAULT_KEY_ID] = secret_str.encode()
            self._source = "env"
            self._log_audit("KEY_FALLBACK", self.DEFAULT_KEY_ID,
                            "using env var — NOT FOR PRODUCTION")

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    @property
    def audit_log(self) -> list[dict]:
        """Return the key rotation/revocation audit log."""
        return list(self._audit_log)

    @property
    def strict_mode(self) -> bool:
        return bool(self._strict)

    @property
    def source(self) -> str:
        return self._source

    @property
    def key_dir(self) -> str:
        return self._key_dir

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
        self._log_audit("KEY_REVOKED", key_id)

    def add_key(self, key_id: str, secret: bytes) -> None:
        """Register a new key for signing/verification."""
        self._keys[key_id] = secret
        fingerprint = self._key_fingerprint(secret)
        self._log_audit("KEY_ADDED", key_id, f"fingerprint={fingerprint}")

    @property
    def revoked_keys(self) -> set:
        return set(self._revoked)

    @property
    def available_key_ids(self) -> list:
        return list(self._keys.keys())


def get_key_manager_status(
    *,
    key_manager: Optional[KeyManager] = None,
    run_integrity: bool = False,
    strict: bool | None = None,
) -> dict:
    """Return non-secret governance key status for runtime inspection."""
    try:
        manager = key_manager or KeyManager(strict=strict)
    except Exception as exc:
        return {
            "available": False,
            "status": "ERROR",
            "strict_mode": None if strict is None else bool(strict),
            "source": "unavailable",
            "key_dir": os.environ.get("YGB_KEY_DIR", "") or None,
            "active_key_id": None,
            "available_key_ids": [],
            "revoked_keys": [],
            "using_env_fallback": False,
            "authority_key_configured": bool(os.environ.get("YGB_AUTHORITY_KEY", "").strip()),
            "integrity": asdict(last_integrity_report) if last_integrity_report is not None else None,
            "audit_events": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    active_key_id = manager.active_key_id or None
    available = False
    error = None
    try:
        active_key_id, _ = manager.get_signing_key()
        available = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    integrity_payload = asdict(last_integrity_report) if last_integrity_report is not None else None
    if run_integrity:
        try:
            integrity_payload = asdict(run_integrity_check())
        except Exception as exc:
            integrity_payload = {
                "entries_checked": 0,
                "hash_chain_valid": False,
                "first_broken_entry_id": None,
                "checked_at": _integrity_timestamp(),
                "error": f"{type(exc).__name__}: {exc}",
            }
            error = error or f"integrity_check_failed: {type(exc).__name__}: {exc}"

    using_env_fallback = manager.source == "env"
    revoked_keys = sorted(str(key_id) for key_id in manager.revoked_keys)
    status = "HEALTHY"
    if not available:
        status = "ERROR"
    elif using_env_fallback or revoked_keys:
        status = "DEGRADED"

    return {
        "available": available,
        "status": status,
        "strict_mode": manager.strict_mode,
        "source": manager.source,
        "key_dir": manager.key_dir or None,
        "active_key_id": active_key_id,
        "available_key_ids": sorted(str(key_id) for key_id in manager.available_key_ids),
        "revoked_keys": revoked_keys,
        "using_env_fallback": using_env_fallback,
        "authority_key_configured": bool(os.environ.get("YGB_AUTHORITY_KEY", "").strip()),
        "integrity": integrity_payload,
        "audit_events": manager.audit_log[-10:],
        "error": error,
    }


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
