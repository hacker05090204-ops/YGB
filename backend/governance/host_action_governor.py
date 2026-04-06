"""
host_action_governor.py - Signed governance for bounded host actions.

This module creates a separate approval lane for host automation without
weakening the permanent authority locks used by the security runtime.

Rules:
  - Every host action requires an expiring signed session.
  - Sessions are append-only and hash-chained on disk.
  - Only allowlisted apps/tasks can execute.
  - Host actions never accept arbitrary shell text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import shutil
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import urlparse

from backend.governance.approval_ledger import KeyManager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOST_ACTION_LEDGER_PATH = PROJECT_ROOT / "data" / "host_action_ledger.jsonl"
DEFAULT_SESSION_SECONDS = 3600
MAX_SESSION_SECONDS = 8 * 3600
logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {
    "LAUNCH_APP",
    "OPEN_APP",
    "OPEN_URL",
    "RUN_APPROVED_TASK",
}

APP_REGISTRY: Dict[str, Dict[str, object]] = {
    "notepad": {
        "aliases": ("notepad", "notepad.exe"),
        "candidates": (r"C:\Windows\System32\notepad.exe",),
    },
    "code": {
        "aliases": ("code", "code.exe", "vscode", "visual studio code"),
        "candidates": (
            shutil.which("code") or "",
            r"C:\Users\Unkno\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        ),
    },
    "msedge": {
        "aliases": ("edge", "msedge", "msedge.exe", "browser"),
        "candidates": (
            shutil.which("msedge") or "",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ),
    },
    "explorer": {
        "aliases": ("explorer", "explorer.exe", "file explorer"),
        "candidates": (r"C:\Windows\explorer.exe",),
    },
    "terminal": {
        "aliases": ("terminal", "wt", "wt.exe", "windows terminal"),
        "candidates": (
            shutil.which("wt") or "",
            shutil.which("wt.exe") or "",
        ),
    },
    "powershell": {
        "aliases": ("powershell", "powershell.exe", "pwsh"),
        "candidates": (
            shutil.which("pwsh") or "",
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        ),
    },
    "cmd": {
        "aliases": ("cmd", "cmd.exe", "command prompt"),
        "candidates": (r"C:\Windows\System32\cmd.exe",),
    },
    "calc": {
        "aliases": ("calc", "calc.exe", "calculator"),
        "candidates": (r"C:\Windows\System32\calc.exe",),
    },
}

TASK_REGISTRY: Dict[str, Dict[str, object]] = {
    "antigravity_harness": {
        "aliases": ("antigravity", "antigravity harness", "run antigravity"),
        "command": (
            os.path.abspath(sys.executable),
            str(PROJECT_ROOT / "scripts" / "antigravity_harness.py"),
        ),
        "cwd": str(PROJECT_ROOT),
        "description": "Run the project antigravity harness",
    },
}


@dataclass
class QuotaStatus:
    action_type: str
    used: int
    limit: int
    window_seconds: int
    resets_at: float


class ActionQuotaTracker:
    WINDOW_SECONDS = 24 * 60 * 60
    DEFAULT_LIMITS: dict[str, int] = {
        "LAUNCH_APP": 100,
        "OPEN_APP": 100,
        "OPEN_URL": 250,
        "RUN_APPROVED_TASK": 50,
    }

    def __init__(
        self,
        default_limits: Optional[dict[str, int]] = None,
        *,
        window_seconds: int = WINDOW_SECONDS,
        time_func=None,
    ):
        self.default_limits = dict(self.DEFAULT_LIMITS)
        if default_limits:
            self.default_limits.update({str(k).strip().upper(): int(v) for k, v in default_limits.items()})
        self.window_seconds = int(window_seconds)
        self._time_func = time_func or time.time
        self._windows: dict[str, deque[float]] = {}

    def _normalize_action_type(self, action_type: str) -> str:
        return str(action_type).strip().upper()

    def _limit_for(self, action_type: str) -> int:
        return int(self.default_limits.get(action_type, 100))

    def _bucket(self, action_type: str) -> tuple[deque[float], float]:
        normalized = self._normalize_action_type(action_type)
        now = float(self._time_func())
        bucket = self._windows.setdefault(normalized, deque())
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return bucket, now

    def track(self, action_type: str) -> bool:
        normalized = self._normalize_action_type(action_type)
        bucket, now = self._bucket(normalized)
        del now
        if len(bucket) >= self._limit_for(normalized):
            return False
        bucket.append(float(self._time_func()))
        return True

    def get_quota_status(self, action_type: str) -> QuotaStatus:
        normalized = self._normalize_action_type(action_type)
        bucket, now = self._bucket(normalized)
        resets_at = bucket[0] + self.window_seconds if bucket else now + self.window_seconds
        return QuotaStatus(
            action_type=normalized,
            used=len(bucket),
            limit=self._limit_for(normalized),
            window_seconds=self.window_seconds,
            resets_at=resets_at,
        )

    def get_all(self) -> dict:
        action_types = sorted(set(self.default_limits) | set(self._windows))
        return {action_type: self.get_quota_status(action_type) for action_type in action_types}


_quota_tracker = ActionQuotaTracker()


def _apply_quota_decision(action_type: str, decision: dict) -> dict:
    if not decision.get("allowed"):
        return decision

    normalized = str(action_type).strip().upper()
    if _quota_tracker.track(normalized):
        return decision

    logger.warning("Host action quota exceeded for action_type=%s", normalized)
    return {
        "allowed": False,
        "reason": "HOST_ACTION_QUOTA_EXCEEDED",
        "action_type": normalized,
        "quota": _quota_tracker.get_quota_status(normalized),
    }


def get_quota_statuses() -> dict:
    return _quota_tracker.get_all()


def _canonical_join(values: Iterable[str]) -> str:
    return "|".join(sorted({str(v).strip() for v in values if str(v).strip()}))


def _normalize_root(path_value: str) -> str:
    return os.path.abspath(os.path.normpath(path_value.strip()))


def _is_path_in_root(path_value: str, root_value: str) -> bool:
    try:
        return os.path.commonpath([_normalize_root(path_value), root_value]) == root_value
    except ValueError:
        return False


@dataclass(frozen=True)
class HostActionSession:
    session_id: str
    requested_by: str
    approver_id: str
    reason: str
    allowed_actions: tuple[str, ...]
    allowed_apps: tuple[str, ...]
    allowed_tasks: tuple[str, ...]
    allowed_roots: tuple[str, ...]
    created_at: float
    expires_at: float
    nonce: str
    key_id: str
    signature: str

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "requested_by": self.requested_by,
            "approver_id": self.approver_id,
            "reason": self.reason,
            "allowed_actions": list(self.allowed_actions),
            "allowed_apps": list(self.allowed_apps),
            "allowed_tasks": list(self.allowed_tasks),
            "allowed_roots": list(self.allowed_roots),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "key_id": self.key_id,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HostActionSession":
        return cls(
            session_id=data["session_id"],
            requested_by=data["requested_by"],
            approver_id=data["approver_id"],
            reason=data["reason"],
            allowed_actions=tuple(data.get("allowed_actions", [])),
            allowed_apps=tuple(data.get("allowed_apps", [])),
            allowed_tasks=tuple(data.get("allowed_tasks", [])),
            allowed_roots=tuple(data.get("allowed_roots", [])),
            created_at=float(data["created_at"]),
            expires_at=float(data["expires_at"]),
            nonce=data["nonce"],
            key_id=data["key_id"],
            signature=data["signature"],
        )


class HostActionGovernor:
    """Signed, append-only governance for bounded host actions."""

    def __init__(
        self,
        ledger_path: str | os.PathLike[str] | None = None,
        key_manager: Optional[KeyManager] = None,
    ):
        self._path = str(ledger_path or HOST_ACTION_LEDGER_PATH)
        self._entries: list[dict] = []
        self._chain_hash = "0" * 64
        if key_manager is not None:
            self._key_mgr = key_manager
        else:
            use_env_secret_fallback = (
                bool(os.environ.get("YGB_APPROVAL_SECRET"))
                and not os.environ.get("YGB_KEY_DIR")
            )
            self._key_mgr = KeyManager(strict=False) if use_env_secret_fallback else KeyManager()

    @property
    def chain_hash(self) -> str:
        return self._chain_hash

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @classmethod
    def canonicalize_app_name(cls, app_name: str) -> Optional[str]:
        raw = app_name.strip().lower()
        if not raw:
            return None
        for canonical, meta in APP_REGISTRY.items():
            aliases = meta.get("aliases", ())
            if raw == canonical or raw in aliases:
                return canonical
        return None

    @classmethod
    def canonicalize_task_name(cls, task_name: str) -> Optional[str]:
        raw = task_name.strip().lower()
        if not raw:
            return None
        for canonical, meta in TASK_REGISTRY.items():
            aliases = meta.get("aliases", ())
            if raw == canonical or raw in aliases:
                return canonical
        return None

    @classmethod
    def resolve_app_command(cls, app_name: str) -> Optional[list[str]]:
        canonical = cls.canonicalize_app_name(app_name)
        if canonical is None:
            return None
        candidates = APP_REGISTRY[canonical].get("candidates", ())
        for candidate in candidates:
            resolved = str(candidate).strip()
            if resolved and os.path.isabs(resolved) and os.path.exists(resolved):
                return [resolved]
        return None

    @classmethod
    def resolve_task_command(cls, task_name: str) -> Optional[dict]:
        canonical = cls.canonicalize_task_name(task_name)
        if canonical is None:
            return None
        meta = TASK_REGISTRY[canonical]
        command = [str(part) for part in meta.get("command", ()) if str(part).strip()]
        if len(command) < 2:
            return None
        if not os.path.isabs(command[0]) or not os.path.exists(command[0]):
            return None
        if not os.path.exists(command[1]):
            return None
        return {
            "task": canonical,
            "command": command,
            "cwd": str(meta.get("cwd") or PROJECT_ROOT),
        }

    def _sign_payload(self, session: HostActionSession | dict, secret: bytes) -> str:
        data = session.to_dict() if isinstance(session, HostActionSession) else dict(session)
        payload = (
            f"{data['session_id']}:{data['requested_by']}:{data['approver_id']}:"
            f"{data['reason']}:{data['created_at']}:{data['expires_at']}:"
            f"{data['nonce']}:{data['key_id']}:"
            f"{_canonical_join(data.get('allowed_actions', []))}:"
            f"{_canonical_join(data.get('allowed_apps', []))}:"
            f"{_canonical_join(data.get('allowed_tasks', []))}:"
            f"{_canonical_join(data.get('allowed_roots', []))}"
        )
        return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()

    def issue_session(
        self,
        *,
        requested_by: str,
        approver_id: str,
        reason: str,
        allowed_actions: Iterable[str],
        allowed_apps: Optional[Iterable[str]] = None,
        allowed_tasks: Optional[Iterable[str]] = None,
        allowed_roots: Optional[Iterable[str]] = None,
        expiration_window_s: int = DEFAULT_SESSION_SECONDS,
    ) -> HostActionSession:
        if not requested_by.strip():
            raise ValueError("HOST_ACTION_REJECTED: requested_by required")
        if not approver_id.strip():
            raise ValueError("HOST_ACTION_REJECTED: approver_id required")
        if not reason.strip():
            raise ValueError("HOST_ACTION_REJECTED: reason required")

        actions = tuple(
            sorted({
                str(action).strip().upper()
                for action in allowed_actions
                if str(action).strip()
            })
        )
        if not actions:
            raise ValueError("HOST_ACTION_REJECTED: at least one action is required")
        unsupported = [action for action in actions if action not in SUPPORTED_ACTIONS]
        if unsupported:
            raise ValueError(
                f"HOST_ACTION_REJECTED: unsupported actions {unsupported}"
            )

        apps = tuple(
            sorted({
                canonical
                for raw in (allowed_apps or ())
                for canonical in [self.canonicalize_app_name(str(raw))]
                if canonical
            })
        )
        tasks = tuple(
            sorted({
                canonical
                for raw in (allowed_tasks or ())
                for canonical in [self.canonicalize_task_name(str(raw))]
                if canonical
            })
        )
        roots = tuple(
            sorted({
                _normalize_root(str(root))
                for root in (allowed_roots or ())
                if str(root).strip()
            })
        )

        if any(action in {"LAUNCH_APP", "OPEN_APP", "OPEN_URL"} for action in actions) and not apps:
            raise ValueError(
                "HOST_ACTION_REJECTED: app actions require allowed_apps"
            )
        if "RUN_APPROVED_TASK" in actions and not tasks:
            raise ValueError(
                "HOST_ACTION_REJECTED: task actions require allowed_tasks"
            )

        expires_in = max(60, min(int(expiration_window_s), MAX_SESSION_SECONDS))
        created_at = time.time()
        expires_at = created_at + expires_in
        session_id = f"HAG-{uuid.uuid4().hex[:16].upper()}"
        nonce = uuid.uuid4().hex
        key_id, secret = self._key_mgr.get_signing_key()

        unsigned = {
            "session_id": session_id,
            "requested_by": requested_by.strip(),
            "approver_id": approver_id.strip(),
            "reason": reason.strip(),
            "allowed_actions": list(actions),
            "allowed_apps": list(apps),
            "allowed_tasks": list(tasks),
            "allowed_roots": list(roots),
            "created_at": created_at,
            "expires_at": expires_at,
            "nonce": nonce,
            "key_id": key_id,
        }
        signature = self._sign_payload(unsigned, secret)

        session = HostActionSession(
            session_id=session_id,
            requested_by=unsigned["requested_by"],
            approver_id=unsigned["approver_id"],
            reason=unsigned["reason"],
            allowed_actions=actions,
            allowed_apps=apps,
            allowed_tasks=tasks,
            allowed_roots=roots,
            created_at=created_at,
            expires_at=expires_at,
            nonce=nonce,
            key_id=key_id,
            signature=signature,
        )
        self.append(session)
        return session

    def verify_session(self, session: HostActionSession) -> bool:
        if self._key_mgr.is_revoked(session.key_id):
            return False
        secret = self._key_mgr.get_verification_key(session.key_id)
        if secret is None:
            return False
        expected = self._sign_payload(session, secret)
        return hmac.compare_digest(expected, session.signature)

    def append(self, session: HostActionSession) -> dict:
        if not self.verify_session(session):
            raise ValueError("HOST_ACTION_REJECTED: invalid signature")
        self.load()
        if self.get_session(session.session_id) is not None:
            raise ValueError("HOST_ACTION_REJECTED: duplicate session id")

        entry = {
            "sequence": len(self._entries),
            "session": session.to_dict(),
            "prev_hash": self._chain_hash,
            "entry_hash": "",
            "appended_at": time.time(),
        }
        entry_data = json.dumps(
            {k: v for k, v in entry.items() if k != "entry_hash"},
            sort_keys=True,
        )
        entry["entry_hash"] = hashlib.sha256(entry_data.encode()).hexdigest()
        self._entries.append(entry)
        self._chain_hash = entry["entry_hash"]
        self._persist(entry)
        return entry

    def _persist(self, entry: dict) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def load(self) -> None:
        self._entries = []
        self._chain_hash = "0" * 64
        if not os.path.exists(self._path):
            return

        with open(self._path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                self._entries.append(entry)
                self._chain_hash = entry["entry_hash"]

    def verify_chain(self) -> bool:
        prev_hash = "0" * 64
        for entry in self._entries:
            if entry["prev_hash"] != prev_hash:
                return False
            entry_data = json.dumps(
                {k: v for k, v in entry.items() if k != "entry_hash"},
                sort_keys=True,
            )
            if hashlib.sha256(entry_data.encode()).hexdigest() != entry["entry_hash"]:
                return False
            prev_hash = entry["entry_hash"]
        return True

    def get_session(self, session_id: str) -> Optional[HostActionSession]:
        for entry in reversed(self._entries):
            session_data = entry.get("session", {})
            if session_data.get("session_id") == session_id:
                return HostActionSession.from_dict(session_data)
        return None

    def describe_session(self, session_id: str) -> dict:
        self.load()
        chain_valid = self.verify_chain()
        session = self.get_session(session_id)
        if session is None:
            return {
                "status": "missing",
                "session_id": session_id,
                "chain_valid": chain_valid,
            }
        now = time.time()
        expires_in = max(0, int(session.expires_at - now))
        return {
            "status": "active" if expires_in > 0 and chain_valid else "expired",
            "session_id": session.session_id,
            "requested_by": session.requested_by,
            "approver_id": session.approver_id,
            "reason": session.reason,
            "allowed_actions": list(session.allowed_actions),
            "allowed_apps": list(session.allowed_apps),
            "allowed_tasks": list(session.allowed_tasks),
            "allowed_roots": list(session.allowed_roots),
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "expires_in_s": expires_in,
            "chain_valid": chain_valid,
            "signature_valid": self.verify_session(session),
        }

    def status_snapshot(self, active_session_id: Optional[str] = None) -> dict:
        self.load()
        snapshot = {
            "ledger_entries": self.entry_count,
            "chain_valid": self.verify_chain(),
            "active_session_id": active_session_id,
        }
        if active_session_id:
            snapshot["active_session"] = self.describe_session(active_session_id)
        return snapshot

    def validate_request(self, session_id: str, action: str, args: dict) -> dict:
        self.load()
        if not session_id:
            return {
                "allowed": False,
                "reason": "HOST_ACTION_SESSION_REQUIRED",
            }
        if not self.verify_chain():
            return {
                "allowed": False,
                "reason": "HOST_ACTION_LEDGER_TAMPERED",
            }

        session = self.get_session(session_id)
        if session is None:
            return {
                "allowed": False,
                "reason": "HOST_ACTION_SESSION_NOT_FOUND",
            }
        if not self.verify_session(session):
            return {
                "allowed": False,
                "reason": "HOST_ACTION_SIGNATURE_INVALID",
            }
        if time.time() > session.expires_at:
            return {
                "allowed": False,
                "reason": "HOST_ACTION_SESSION_EXPIRED",
            }

        action_name = action.strip().upper()
        if action_name not in session.allowed_actions:
            return {
                "allowed": False,
                "reason": f"HOST_ACTION_NOT_APPROVED: {action_name}",
            }

        if action_name in {"LAUNCH_APP", "OPEN_APP"}:
            app = self.canonicalize_app_name(args.get("app", ""))
            if app is None:
                return {
                    "allowed": False,
                    "reason": "HOST_ACTION_APP_UNKNOWN",
                }
            if app not in session.allowed_apps:
                return {
                    "allowed": False,
                    "reason": f"HOST_ACTION_APP_NOT_ALLOWED: {app}",
                }
            command = self.resolve_app_command(app)
            if not command:
                return {
                    "allowed": False,
                    "reason": f"HOST_ACTION_APP_NOT_FOUND: {app}",
                }
            return _apply_quota_decision(
                action_name,
                {
                    "allowed": True,
                    "reason": "OK",
                    "session": session,
                    "canonical_app": app,
                    "command": command,
                },
            )

        if action_name == "OPEN_URL":
            raw_url = str(args.get("url", "")).strip()
            parsed = urlparse(raw_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return {
                    "allowed": False,
                    "reason": "HOST_ACTION_URL_INVALID",
                }
            app = self.canonicalize_app_name(args.get("app", "msedge") or "msedge")
            if app is None:
                return {
                    "allowed": False,
                    "reason": "HOST_ACTION_APP_UNKNOWN",
                }
            if app not in session.allowed_apps:
                return {
                    "allowed": False,
                    "reason": f"HOST_ACTION_APP_NOT_ALLOWED: {app}",
                }
            command = self.resolve_app_command(app)
            if not command:
                return {
                    "allowed": False,
                    "reason": f"HOST_ACTION_APP_NOT_FOUND: {app}",
                }
            return _apply_quota_decision(
                action_name,
                {
                    "allowed": True,
                    "reason": "OK",
                    "session": session,
                    "canonical_app": app,
                    "command": command + [raw_url],
                },
            )

        if action_name == "RUN_APPROVED_TASK":
            task = self.canonicalize_task_name(args.get("task", ""))
            if task is None:
                return {
                    "allowed": False,
                    "reason": "HOST_ACTION_TASK_UNKNOWN",
                }
            if task not in session.allowed_tasks:
                return {
                    "allowed": False,
                    "reason": f"HOST_ACTION_TASK_NOT_ALLOWED: {task}",
                }
            task_meta = self.resolve_task_command(task)
            if not task_meta:
                return {
                    "allowed": False,
                    "reason": f"HOST_ACTION_TASK_NOT_FOUND: {task}",
                }
            path_arg = str(args.get("path", "")).strip()
            if path_arg and session.allowed_roots:
                allowed_path = any(
                    _is_path_in_root(path_arg, root) for root in session.allowed_roots
                )
                if not allowed_path:
                    return {
                        "allowed": False,
                        "reason": "HOST_ACTION_PATH_OUT_OF_SCOPE",
                    }
            return _apply_quota_decision(
                action_name,
                {
                    "allowed": True,
                    "reason": "OK",
                    "session": session,
                    "canonical_task": task,
                    "command": task_meta["command"],
                    "cwd": task_meta["cwd"],
                },
            )

        return {
            "allowed": False,
            "reason": f"HOST_ACTION_UNSUPPORTED: {action_name}",
        }
