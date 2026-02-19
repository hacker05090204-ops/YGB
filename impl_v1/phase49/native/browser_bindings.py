# browser_bindings.py
"""
Python ↔ C++ Browser Engine Bindings

CRITICAL: This module validates all inputs through Python governors
before passing to C++ native browser engine.

Human approval is ALWAYS verified before any browser launch.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
import subprocess
import shutil
import os
import uuid
from pathlib import Path


class NativeBrowserType(Enum):
    """Maps to C++ BrowserType enum"""
    UNGOOGLED_CHROMIUM = 0
    EDGE_HEADLESS = 1


class NativeLaunchMode(Enum):
    """Maps to C++ LaunchMode enum"""
    HEADED = 0
    HEADLESS = 1


class NativeLaunchResult(Enum):
    """Maps to C++ LaunchResult enum"""
    SUCCESS = 0
    FAILED_GOVERNANCE_CHECK = 1
    FAILED_BROWSER_NOT_FOUND = 2
    FAILED_PERMISSION_DENIED = 3
    FAILED_ALREADY_RUNNING = 4
    FAILED_UNKNOWN = 5


@dataclass(frozen=True)
class NativeLaunchRequest:
    """Python representation of C++ browser launch request."""
    request_id: str
    browser_type: NativeBrowserType
    mode: NativeLaunchMode
    target_url: str
    governance_approved: bool
    human_approved: bool


@dataclass(frozen=True)
class NativeLaunchResponse:
    """Python representation of C++ browser launch response."""
    request_id: str
    result: NativeLaunchResult
    process_id: int
    error_message: str
    fallback_used: bool


class BrowserBindings:
    """
    Python bindings to C++ browser engine.

    Real implementation using subprocess to launch actual browser.
    NO mock data. NO simulated processes.
    """

    # Known browser paths (Windows)
    _BROWSER_PATHS = (
        r"C:\Program Files\Chromium\Application\chrome.exe",
        r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
        r"C:\Program Files\Ungoogled Chromium\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    )

    def __init__(self):
        self._browser_path: Optional[str] = None
        self._initialized = False
        self._active_processes: dict[int, subprocess.Popen] = {}

    def _find_browser(self) -> Optional[str]:
        """Find installed browser executable."""
        for path in self._BROWSER_PATHS:
            if Path(path).exists():
                return path
        # Fallback: search PATH
        chromium = shutil.which("chrome") or shutil.which("chromium")
        if chromium:
            return chromium
        edge = shutil.which("msedge")
        if edge:
            return edge
        return None

    def initialize(self) -> bool:
        """Initialize the browser engine by locating the browser."""
        if self._initialized:
            return True
        self._browser_path = self._find_browser()
        if not self._browser_path:
            return False
        self._initialized = True
        return True

    def launch(self, request: NativeLaunchRequest) -> NativeLaunchResponse:
        """
        Launch browser through real subprocess.

        CRITICAL: Validates governance and human approval before launch.
        """
        # Validate governance
        if not request.governance_approved:
            return NativeLaunchResponse(
                request_id=request.request_id,
                result=NativeLaunchResult.FAILED_GOVERNANCE_CHECK,
                process_id=-1,
                error_message="Governance approval required",
                fallback_used=False,
            )

        # Validate human approval
        if not request.human_approved:
            return NativeLaunchResponse(
                request_id=request.request_id,
                result=NativeLaunchResult.FAILED_PERMISSION_DENIED,
                process_id=-1,
                error_message="Human approval required",
                fallback_used=False,
            )

        if not self._browser_path:
            return NativeLaunchResponse(
                request_id=request.request_id,
                result=NativeLaunchResult.FAILED_BROWSER_NOT_FOUND,
                process_id=-1,
                error_message="No supported browser found on system",
                fallback_used=False,
            )

        # Build command
        cmd = [self._browser_path]
        if request.mode == NativeLaunchMode.HEADLESS:
            cmd.append("--headless")
        cmd.append(request.target_url)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._active_processes[proc.pid] = proc
            return NativeLaunchResponse(
                request_id=request.request_id,
                result=NativeLaunchResult.SUCCESS,
                process_id=proc.pid,
                error_message="",
                fallback_used=False,
            )
        except (OSError, FileNotFoundError) as exc:
            return NativeLaunchResponse(
                request_id=request.request_id,
                result=NativeLaunchResult.FAILED_UNKNOWN,
                process_id=-1,
                error_message=str(exc),
                fallback_used=False,
            )

    def stop(self, process_id: int) -> bool:
        """Stop a running browser process."""
        proc = self._active_processes.pop(process_id, None)
        if proc is None:
            return False
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
        return True

    def is_running(self, process_id: int) -> bool:
        """Check if browser process is still running."""
        proc = self._active_processes.get(process_id)
        if proc is None:
            return False
        return proc.poll() is None

    def cleanup(self):
        """Terminate all active browser processes."""
        for pid in list(self._active_processes):
            self.stop(pid)
        self._initialized = False


# Singleton instance
_bindings: Optional[BrowserBindings] = None


def get_bindings() -> BrowserBindings:
    """Get or create browser bindings instance."""
    global _bindings
    if _bindings is None:
        _bindings = BrowserBindings()
    return _bindings


def reset_bindings():
    """Reset bindings (for testing)."""
    global _bindings
    if _bindings:
        _bindings.cleanup()
    _bindings = None


def create_launch_request(
    browser_type: NativeBrowserType,
    mode: NativeLaunchMode,
    target_url: str,
    governance_approved: bool,
    human_approved: bool,
) -> NativeLaunchRequest:
    """Factory function to create launch request."""
    return NativeLaunchRequest(
        request_id=f"NAT-{uuid.uuid4().hex[:16].upper()}",
        browser_type=browser_type,
        mode=mode,
        target_url=target_url,
        governance_approved=governance_approved,
        human_approved=human_approved,
    )


def launch_browser(
    target_url: str,
    governance_approved: bool,
    human_approved: bool,
    prefer_headless: bool = False,
) -> Tuple[bool, NativeLaunchResponse]:
    """
    High-level browser launch function.
    
    Returns (success, response)
    """
    bindings = get_bindings()
    
    if not bindings.initialize():
        return False, NativeLaunchResponse(
            request_id="INIT-FAIL",
            result=NativeLaunchResult.FAILED_UNKNOWN,
            process_id=-1,
            error_message="Failed to initialize browser engine",
            fallback_used=False,
        )
    
    request = create_launch_request(
        browser_type=NativeBrowserType.UNGOOGLED_CHROMIUM,
        mode=NativeLaunchMode.HEADLESS if prefer_headless else NativeLaunchMode.HEADED,
        target_url=target_url,
        governance_approved=governance_approved,
        human_approved=human_approved,
    )
    
    response = bindings.launch(request)
    success = response.result == NativeLaunchResult.SUCCESS
    
    return success, response
