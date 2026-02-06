"""
Reproducible Build Verification - Phase 49
============================================

Ensure builds are bit-for-bit reproducible:
1. SOURCE_DATE_EPOCH
2. Deterministic compiler flags
3. Strip timestamps
4. Dual build comparison
"""

import os
import hashlib
import subprocess
from pathlib import Path
from typing import Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


# =============================================================================
# REPRODUCIBLE BUILD CONFIG
# =============================================================================

# Fixed timestamp for reproducible builds
SOURCE_DATE_EPOCH = "1707264000"  # 2024-02-07 00:00:00 UTC

# Compiler flags for reproducible builds
REPRODUCIBLE_FLAGS = [
    "-fno-record-gcc-switches",  # Don't embed compiler flags
    "-frandom-seed=phase49",     # Deterministic random seed
    "-fdebug-prefix-map=/=",     # Strip build path
]

# Linker flags
REPRODUCIBLE_LDFLAGS = [
    "-Wl,--build-id=sha1",       # Deterministic build ID
]


# =============================================================================
# BUILD ENVIRONMENT
# =============================================================================

def get_reproducible_env() -> dict:
    """Get environment variables for reproducible builds."""
    env = os.environ.copy()
    
    # Set fixed timestamp
    env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    
    # Disable locale variations
    env["LC_ALL"] = "C"
    env["TZ"] = "UTC"
    
    # Disable parallelism variations
    env["MAKEFLAGS"] = "-j1"
    
    return env


# =============================================================================
# BUILD VERIFICATION
# =============================================================================

@dataclass
class BuildResult:
    """Result of a build."""
    success: bool
    binary_path: Path
    sha256: str
    size: int
    build_time: float


def compute_binary_hash(binary_path: Path) -> str:
    """Compute SHA256 of binary."""
    sha256 = hashlib.sha256()
    with open(binary_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_once(build_dir: Path, env: dict) -> BuildResult:
    """Perform one build and return result."""
    import time
    
    start = time.time()
    
    # Clean build
    subprocess.run(
        ["make", "clean"],
        cwd=build_dir,
        env=env,
        capture_output=True,
    )
    
    # Build
    result = subprocess.run(
        ["make"],
        cwd=build_dir,
        env=env,
        capture_output=True,
    )
    
    elapsed = time.time() - start
    
    # Find binary
    binary_path = build_dir / "lib" / "libnative_engines.so"
    if not binary_path.exists():
        binary_path = build_dir / "lib" / "libnative_engines.dylib"
    
    if binary_path.exists():
        return BuildResult(
            success=True,
            binary_path=binary_path,
            sha256=compute_binary_hash(binary_path),
            size=binary_path.stat().st_size,
            build_time=elapsed,
        )
    else:
        return BuildResult(
            success=False,
            binary_path=binary_path,
            sha256="",
            size=0,
            build_time=elapsed,
        )


def verify_reproducible_build(build_dir: Path) -> Tuple[bool, str]:
    """
    Build twice and compare hashes.
    
    Returns:
        Tuple of (reproducible, message)
    """
    env = get_reproducible_env()
    
    # First build
    result1 = build_once(build_dir, env)
    if not result1.success:
        return False, "First build failed"
    
    # Second build
    result2 = build_once(build_dir, env)
    if not result2.success:
        return False, "Second build failed"
    
    # Compare
    if result1.sha256 == result2.sha256:
        return True, f"Reproducible: {result1.sha256}"
    else:
        return False, f"Mismatch: {result1.sha256} vs {result2.sha256}"


# =============================================================================
# CI SCRIPT
# =============================================================================

CI_REPRODUCIBLE_BUILD = '''#!/bin/bash
# CI Reproducible Build Verification

set -e

echo "=== REPRODUCIBLE BUILD VERIFICATION ==="

NATIVE_DIR="impl_v1/phase49/native"

# Set reproducible environment
export SOURCE_DATE_EPOCH=1707264000
export LC_ALL=C
export TZ=UTC

# First build
echo "Building (attempt 1)..."
cd $NATIVE_DIR
make clean 2>/dev/null || true
make
HASH1=$(sha256sum lib/libnative_engines.* 2>/dev/null | cut -d' ' -f1 || echo "SKIP")

if [ "$HASH1" = "SKIP" ]; then
    echo "SKIP: No native library built (expected on Windows)"
    exit 0
fi

# Second build
echo "Building (attempt 2)..."
make clean
make
HASH2=$(sha256sum lib/libnative_engines.* | cut -d' ' -f1)

cd -

# Compare
if [ "$HASH1" = "$HASH2" ]; then
    echo "PASS: Builds are reproducible"
    echo "  SHA256: $HASH1"
else
    echo "FAIL: Builds differ"
    echo "  Build 1: $HASH1"
    echo "  Build 2: $HASH2"
    exit 1
fi

echo "=== REPRODUCIBLE BUILD PASSED ==="
'''


# =============================================================================
# TIMESTAMP STRIPPING
# =============================================================================

def strip_timestamps(binary_path: Path) -> None:
    """Strip timestamps from binary (Linux only)."""
    import platform
    
    if platform.system() != "Linux":
        return
    
    # Use objcopy to strip debug sections
    subprocess.run(
        ["objcopy", "--strip-debug", str(binary_path)],
        capture_output=True,
    )
