"""
Voice Executors — Safe action execution tied to intent_id + audit trail.

Executors:
  - StatusQueryExecutor: read-only queries (GPU, training, CVE)
  - AppRunnerExecutor: launch/focus/close allowlisted apps
  - DownloadExecutor: trusted domains + SHA-256 verification
  - BrowserExecutor: controlled URL navigation (allowlisted domains only)

Rules:
  - Every execution tied to intent_id
  - Every execution produces audit hash
  - No arbitrary execution/download without allowlist pass
"""

import hashlib
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Dict

from impl_v1.phase49.runtime.secure_subprocess import safe_popen

logger = logging.getLogger(__name__)


# =============================================================================
# EXECUTION RESULT
# =============================================================================

class ExecStatus(Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ExecutorResult:
    """Result of an executor action."""
    result_id: str
    intent_id: str
    executor: str
    status: ExecStatus
    output: str
    audit_hash: str
    timestamp: str
    execution_ms: float = 0.0


def _make_audit_hash(intent_id: str, executor: str, output: str) -> str:
    raw = f"{intent_id}:{executor}:{output}:{datetime.now(UTC).isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# =============================================================================
# STATUS QUERY EXECUTOR
# =============================================================================

class StatusQueryExecutor:
    """Read-only status queries — always safe."""

    def execute(self, intent_id: str, query_type: str) -> ExecutorResult:
        import time
        start = time.time()
        output = ""

        try:
            from backend.assistant.voice_runtime import collect_status_snapshot

            payload = collect_status_snapshot(query_type)
            output = json.dumps(payload, indent=2, sort_keys=True, default=str)

            elapsed = (time.time() - start) * 1000
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="StatusQueryExecutor",
                status=ExecStatus.SUCCESS,
                output=output,
                audit_hash=_make_audit_hash(intent_id, "StatusQuery", output),
                timestamp=datetime.now(UTC).isoformat(),
                execution_ms=elapsed,
            )
        except Exception as e:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="StatusQueryExecutor",
                status=ExecStatus.FAILED,
                output=f"Error: {str(e)}",
                audit_hash=_make_audit_hash(intent_id, "StatusQuery", str(e)),
                timestamp=datetime.now(UTC).isoformat(),
            )


# =============================================================================
# APP RUNNER EXECUTOR
# =============================================================================

# Only these apps can be launched
ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "notepad.exe": "notepad.exe",
    "code": "code",
    "code.exe": "code",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "msedge.exe": "msedge.exe",
    "chrome": "chrome",
    "chrome.exe": "chrome",
    "firefox": "firefox",
    "firefox.exe": "firefox",
    "calc": "calc.exe",
    "calc.exe": "calc.exe",
    "explorer": "explorer.exe",
    "explorer.exe": "explorer.exe",
    "terminal": "wt.exe",
    "wt": "wt.exe",
    "wt.exe": "wt.exe",
    "powershell": "powershell.exe",
    "pwsh": "pwsh.exe",
    "cmd": "cmd.exe",
}


class AppRunnerExecutor:
    """Launch, focus, or close allowlisted applications only."""

    def execute(
        self,
        intent_id: str,
        action: str,
        app_name: str,
        *,
        launch_command: Optional[list[str]] = None,
    ) -> ExecutorResult:
        import time
        start = time.time()
        app_lower = app_name.lower().strip()

        if app_lower not in ALLOWED_APPS:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="AppRunnerExecutor",
                status=ExecStatus.BLOCKED,
                output=f"BLOCKED: '{app_name}' not in allowlist",
                audit_hash=_make_audit_hash(intent_id, "AppRunner", "BLOCKED"),
                timestamp=datetime.now(UTC).isoformat(),
            )

        command = list(launch_command or [])
        if not command:
            try:
                from backend.governance.host_action_governor import HostActionGovernor

                resolved = HostActionGovernor.resolve_app_command(app_lower)
            except Exception:
                resolved = None
            if not resolved:
                return ExecutorResult(
                    result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                    intent_id=intent_id,
                    executor="AppRunnerExecutor",
                    status=ExecStatus.BLOCKED,
                    output=f"BLOCKED: no trusted launch command for '{app_name}'",
                    audit_hash=_make_audit_hash(intent_id, "AppRunner", "BLOCKED"),
                    timestamp=datetime.now(UTC).isoformat(),
                )
            command = resolved
        exe = Path(command[0]).name
        try:
            if action in ("launch", "open"):
                safe_popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                output = f"Launched {exe}"
            elif action == "close":
                # Graceful close via taskkill
                subprocess.run(
                    ["taskkill", "/IM", exe, "/F"],
                    capture_output=True, timeout=5,
                )
                output = f"Closed {exe}"
            else:
                output = f"Unknown action: {action}"

            elapsed = (time.time() - start) * 1000
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="AppRunnerExecutor",
                status=ExecStatus.SUCCESS,
                output=output,
                audit_hash=_make_audit_hash(intent_id, "AppRunner", output),
                timestamp=datetime.now(UTC).isoformat(),
                execution_ms=elapsed,
            )
        except Exception as e:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="AppRunnerExecutor",
                status=ExecStatus.FAILED,
                output=f"FAILED: {str(e)}",
                audit_hash=_make_audit_hash(intent_id, "AppRunner", str(e)),
                timestamp=datetime.now(UTC).isoformat(),
            )


# =============================================================================
# APPROVED TASK EXECUTOR
# =============================================================================

class ApprovedTaskExecutor:
    """Launch allowlisted project tasks through the hardened subprocess wrapper."""

    def execute(
        self,
        intent_id: str,
        task_name: str,
        *,
        command: Optional[list[str]] = None,
        workdir: Optional[str] = None,
    ) -> ExecutorResult:
        import time
        start = time.time()

        task_lower = task_name.lower().strip()
        if not task_lower:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="ApprovedTaskExecutor",
                status=ExecStatus.BLOCKED,
                output="BLOCKED: task name required",
                audit_hash=_make_audit_hash(intent_id, "ApprovedTask", "BLOCKED"),
                timestamp=datetime.now(UTC).isoformat(),
            )

        task_command = list(command or [])
        task_workdir = workdir
        if not task_command:
            try:
                from backend.governance.host_action_governor import HostActionGovernor

                task_meta = HostActionGovernor.resolve_task_command(task_lower)
            except Exception:
                task_meta = None
            if not task_meta:
                return ExecutorResult(
                    result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                    intent_id=intent_id,
                    executor="ApprovedTaskExecutor",
                    status=ExecStatus.BLOCKED,
                    output=f"BLOCKED: task '{task_name}' not approved",
                    audit_hash=_make_audit_hash(intent_id, "ApprovedTask", "BLOCKED"),
                    timestamp=datetime.now(UTC).isoformat(),
                )
            task_command = list(task_meta["command"])
            task_workdir = str(task_meta.get("cwd") or "")

        try:
            safe_popen(
                task_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=task_workdir or None,
            )
            output = f"Launched task {task_lower}"
            elapsed = (time.time() - start) * 1000
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="ApprovedTaskExecutor",
                status=ExecStatus.SUCCESS,
                output=output,
                audit_hash=_make_audit_hash(intent_id, "ApprovedTask", output),
                timestamp=datetime.now(UTC).isoformat(),
                execution_ms=elapsed,
            )
        except Exception as e:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="ApprovedTaskExecutor",
                status=ExecStatus.FAILED,
                output=f"FAILED: {str(e)}",
                audit_hash=_make_audit_hash(intent_id, "ApprovedTask", str(e)),
                timestamp=datetime.now(UTC).isoformat(),
            )


# =============================================================================
# DOWNLOAD EXECUTOR
# =============================================================================

ALLOWED_DOWNLOAD_DOMAINS = {
    "github.com", "raw.githubusercontent.com",
    "pypi.org", "files.pythonhosted.org",
    "npmjs.com", "registry.npmjs.org",
    "crates.io", "static.crates.io",
    "dl.google.com", "releases.hashicorp.com",
}


class DownloadExecutor:
    """Download from trusted domains only, with SHA-256 verification."""

    def execute(self, intent_id: str, url: str,
                expected_hash: Optional[str] = None) -> ExecutorResult:
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.lower()
        if domain not in ALLOWED_DOWNLOAD_DOMAINS:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="DownloadExecutor",
                status=ExecStatus.BLOCKED,
                output=f"BLOCKED: Domain '{domain}' not in allowlist",
                audit_hash=_make_audit_hash(intent_id, "Download", "BLOCKED"),
                timestamp=datetime.now(UTC).isoformat(),
            )

        # PRODUCTION: Perform download with requests + hash verification
        # For now, mark as BLOCKED until download pipeline wired
        return ExecutorResult(
            result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
            intent_id=intent_id,
            executor="DownloadExecutor",
            status=ExecStatus.BLOCKED,
            output=f"BLOCKED: Download pipeline not yet wired for {url}",
            audit_hash=_make_audit_hash(intent_id, "Download", "NOT_WIRED"),
            timestamp=datetime.now(UTC).isoformat(),
        )


# =============================================================================
# BROWSER EXECUTOR
# =============================================================================

ALLOWED_BROWSE_DOMAINS = {
    "github.com", "stackoverflow.com", "docs.python.org",
    "developer.mozilla.org", "www.google.com", "cve.mitre.org",
    "nvd.nist.gov", "exploit-db.com", "www.exploit-db.com",
}


class BrowserExecutor:
    """Controlled URL navigation — allowlisted domains only."""

    def execute(
        self,
        intent_id: str,
        url: str,
        *,
        launch_command: Optional[list[str]] = None,
    ) -> ExecutorResult:
        from urllib.parse import urlparse
        import time
        start = time.time()

        domain = urlparse(url).netloc.lower()
        if launch_command is None and domain not in ALLOWED_BROWSE_DOMAINS:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="BrowserExecutor",
                status=ExecStatus.BLOCKED,
                output=f"BLOCKED: Domain '{domain}' not in browse allowlist",
                audit_hash=_make_audit_hash(intent_id, "Browser", "BLOCKED"),
                timestamp=datetime.now(UTC).isoformat(),
            )

        try:
            command = list(launch_command or [])
            if not command:
                try:
                    from backend.governance.host_action_governor import HostActionGovernor

                    resolved = HostActionGovernor.resolve_app_command("msedge")
                except Exception:
                    resolved = None
                if not resolved:
                    raise ValueError("Trusted browser command not available")
                command = resolved + [url]
            safe_popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            elapsed = (time.time() - start) * 1000
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="BrowserExecutor",
                status=ExecStatus.SUCCESS,
                output=f"Opened {url}",
                audit_hash=_make_audit_hash(intent_id, "Browser", url),
                timestamp=datetime.now(UTC).isoformat(),
                execution_ms=elapsed,
            )
        except Exception as e:
            return ExecutorResult(
                result_id=f"EXR-{uuid.uuid4().hex[:12].upper()}",
                intent_id=intent_id,
                executor="BrowserExecutor",
                status=ExecStatus.FAILED,
                output=f"FAILED: {str(e)}",
                audit_hash=_make_audit_hash(intent_id, "Browser", str(e)),
                timestamp=datetime.now(UTC).isoformat(),
            )
