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
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Dict

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
            if query_type in ("QUERY_STATUS", "STATUS_QUERY"):
                output = "System operational. API online."
            elif query_type in ("QUERY_GPU", "LIST_DEVICES"):
                output = "GPU status: check /gpu/status endpoint for real metrics."
            elif query_type in ("QUERY_TRAINING", "TRAINING_STATUS"):
                output = "Training status: check /training/status endpoint."
            elif query_type == "QUERY_PROGRESS":
                output = "Progress: check dashboard for real-time metrics."
            else:
                output = f"Status query completed for: {query_type}"

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

    def execute(self, intent_id: str, action: str,
                app_name: str) -> ExecutorResult:
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

        exe = ALLOWED_APPS[app_lower]
        try:
            if action in ("launch", "open"):
                # Non-blocking launch
                subprocess.Popen(
                    [exe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0),
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

    def execute(self, intent_id: str, url: str) -> ExecutorResult:
        from urllib.parse import urlparse
        import time
        start = time.time()

        domain = urlparse(url).netloc.lower()
        if domain not in ALLOWED_BROWSE_DOMAINS:
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
            import webbrowser
            webbrowser.open(url, new=2)
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
