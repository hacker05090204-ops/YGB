# G38 Runtime - Secure Subprocess Wrapper
"""
HARDENED SUBPROCESS EXECUTION FOR G38.

SECURITY FEATURES:
1. Absolute paths ONLY (no PATH-based lookups)
2. shell=False ALWAYS
3. Clean environment (env={} or minimal)
4. Strict timeout enforcement
5. Return code validation

USAGE:
    result = secure_run(["/usr/bin/xprintidle"])
    if result.success:
        print(result.stdout)
"""

import subprocess
import os
import platform
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum allowed timeout for any subprocess
MAX_TIMEOUT_SECONDS = 30

# Default timeout for idle detection commands
DEFAULT_TIMEOUT_SECONDS = 5

# Approved commands and their absolute paths per platform
APPROVED_COMMANDS: Dict[str, Dict[str, str]] = {
    "linux": {
        "xprintidle": "/usr/bin/xprintidle",
        "loginctl": "/usr/bin/loginctl",
    },
    "windows": {
        # Windows uses ctypes, not subprocess for idle detection
    },
}


# =============================================================================
# RESULT TYPES
# =============================================================================

class ExecStatus(Enum):
    """Execution status codes."""
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    BLOCKED = "BLOCKED"


@dataclass
class SecureResult:
    """Result of secure subprocess execution."""
    status: ExecStatus
    returncode: int
    stdout: str
    stderr: str
    command: List[str]
    
    @property
    def success(self) -> bool:
        """True if command succeeded."""
        return self.status == ExecStatus.SUCCESS and self.returncode == 0


# =============================================================================
# SECURITY VALIDATION
# =============================================================================

def _get_platform() -> str:
    """Get current platform name."""
    return platform.system().lower()


def _validate_command(command: str) -> Optional[str]:
    """
    Validate and return absolute path for approved command.
    
    Returns:
        Absolute path if approved, None if blocked.
    """
    plat = _get_platform()
    approved = APPROVED_COMMANDS.get(plat, {})
    
    # Check if command is in approved list
    cmd_name = Path(command).name
    
    if cmd_name in approved:
        abs_path = approved[cmd_name]
        if Path(abs_path).exists():
            return abs_path
        # Binary not found at expected path
        return None
    
    # Not an approved command
    return None


def _get_clean_environment() -> Dict[str, str]:
    """
    Get minimal clean environment for subprocess.
    
    Only includes necessary variables, no PATH.
    """
    clean_env = {}
    
    # Only include essential variables
    if _get_platform() == "linux":
        # Required for xprintidle (X11)
        if "DISPLAY" in os.environ:
            clean_env["DISPLAY"] = os.environ["DISPLAY"]
        if "XAUTHORITY" in os.environ:
            clean_env["XAUTHORITY"] = os.environ["XAUTHORITY"]
        # Required for loginctl
        if "XDG_RUNTIME_DIR" in os.environ:
            clean_env["XDG_RUNTIME_DIR"] = os.environ["XDG_RUNTIME_DIR"]
    
    return clean_env


# =============================================================================
# SECURE EXECUTION
# =============================================================================

def secure_run(
    args: List[str],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    check_approved: bool = True,
) -> SecureResult:
    """
    Execute command with security hardening.
    
    Args:
        args: Command and arguments (first element is command)
        timeout: Maximum execution time in seconds
        check_approved: If True, only allow approved commands
    
    Returns:
        SecureResult with execution details
    
    Security:
        - shell=False (always)
        - Clean environment
        - Strict timeout
        - Return code validation
    """
    if not args:
        return SecureResult(
            status=ExecStatus.BLOCKED,
            returncode=-1,
            stdout="",
            stderr="Empty command",
            command=args,
        )
    
    # Get command
    original_cmd = args[0]
    
    # Validate and get absolute path
    if check_approved:
        abs_path = _validate_command(original_cmd)
        if abs_path is None:
            return SecureResult(
                status=ExecStatus.BLOCKED,
                returncode=-1,
                stdout="",
                stderr=f"Command not approved: {original_cmd}",
                command=args,
            )
        # Replace with absolute path
        args = [abs_path] + args[1:]
    
    # Enforce timeout limit
    if timeout > MAX_TIMEOUT_SECONDS:
        timeout = MAX_TIMEOUT_SECONDS
    
    # Get clean environment
    clean_env = _get_clean_environment()
    
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # NEVER use shell=True
            env=clean_env,
        )
        
        return SecureResult(
            status=ExecStatus.SUCCESS,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=args,
        )
    
    except subprocess.TimeoutExpired:
        return SecureResult(
            status=ExecStatus.TIMEOUT,
            returncode=-1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            command=args,
        )
    
    except FileNotFoundError:
        return SecureResult(
            status=ExecStatus.NOT_FOUND,
            returncode=-1,
            stdout="",
            stderr=f"Command not found: {args[0]}",
            command=args,
        )
    
    except PermissionError:
        return SecureResult(
            status=ExecStatus.PERMISSION_DENIED,
            returncode=-1,
            stdout="",
            stderr=f"Permission denied: {args[0]}",
            command=args,
        )
    
    except subprocess.SubprocessError as e:
        return SecureResult(
            status=ExecStatus.EXECUTION_ERROR,
            returncode=-1,
            stdout="",
            stderr=str(e),
            command=args,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def is_command_approved(command: str) -> bool:
    """Check if command is in approved list."""
    return _validate_command(command) is not None


def get_approved_commands() -> List[str]:
    """Get list of approved commands for current platform."""
    plat = _get_platform()
    return list(APPROVED_COMMANDS.get(plat, {}).keys())


# =============================================================================
# LONG-RUNNING PROCESS MANAGEMENT
# =============================================================================

def safe_popen(
    args: List[str],
    *,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
) -> subprocess.Popen:
    """
    Launch a long-running process securely.

    Unlike secure_run, this returns a Popen handle for processes that
    need to run asynchronously (e.g. browser windows).

    Security:
        - shell=False always
        - Clean environment
        - Returns Popen handle for lifecycle management
    """
    if not args:
        raise ValueError("Empty command list")

    clean_env = _get_clean_environment()
    # Inherit PATH for browser discovery on Windows
    if "PATH" in os.environ:
        clean_env["PATH"] = os.environ["PATH"]
    if "SYSTEMROOT" in os.environ:
        clean_env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    return subprocess.Popen(
        args,
        stdout=stdout,
        stderr=stderr,
        shell=False,
        env=clean_env,
    )


def safe_terminate(proc: subprocess.Popen, timeout: int = 5) -> bool:
    """
    Safely terminate a long-running process.

    Tries graceful terminate first, then force-kills if needed.
    """
    if proc is None:
        return False
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass
    return True

