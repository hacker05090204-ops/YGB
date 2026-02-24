"""
C++ Safety Precondition — Training Start Gate
=============================================

Blocks training unless the C++ safety suite is fully green.
Runs run_cpp_tests.exe and checks exit code.

If any C++ test fails → training BLOCKED.
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CPP_TEST_EXE = _PROJECT_ROOT / "run_cpp_tests.exe"
_CPP_TEST_SH = _PROJECT_ROOT / "scripts" / "build_cpp_tests.sh"


class CppSafetyError(RuntimeError):
    """Raised when C++ safety suite fails."""
    pass


def check_cpp_safety(
    exe_path: str = None,
    *,
    skip_if_missing: bool = False,
) -> dict:
    """
    Run C++ safety tests and return results.

    Args:
        exe_path: Path to run_cpp_tests.exe (auto-detected if None)
        skip_if_missing: If True, skip (warn) if exe not found.
                        If False (default), raise error.

    Returns:
        dict with keys: passed, output, exit_code

    Raises:
        CppSafetyError if tests fail or exe missing (unless skip_if_missing)
    """
    exe = Path(exe_path) if exe_path else _CPP_TEST_EXE

    if not exe.exists():
        if skip_if_missing:
            logger.warning(f"[CPP_SAFETY] Executable not found: {exe} — SKIPPED")
            return {"passed": True, "output": "SKIPPED (exe not found)", "exit_code": -1}
        raise CppSafetyError(
            f"C++ safety executable not found: {exe}. "
            f"Build with: scripts/build_cpp_tests.sh"
        )

    try:
        result = subprocess.run(
            [str(exe)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(exe.parent),
        )
    except subprocess.TimeoutExpired:
        raise CppSafetyError("C++ safety tests timed out after 30s")
    except Exception as e:
        raise CppSafetyError(f"C++ safety test execution failed: {e}")

    output = result.stdout + result.stderr
    passed = result.returncode == 0

    if passed:
        logger.info("[CPP_SAFETY] All C++ safety tests PASSED")
    else:
        logger.error(f"[CPP_SAFETY] FAILED (exit code {result.returncode})")
        raise CppSafetyError(
            f"C++ safety suite FAILED (exit code {result.returncode}). "
            f"Training BLOCKED.\nOutput:\n{output[:500]}"
        )

    return {"passed": True, "output": output, "exit_code": result.returncode}
