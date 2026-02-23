"""
build_bridge.py — Build script for ingestion_bridge.dll/.so

Compiles ingestion_bridge.cpp + ingestion_engine.cpp into a shared library
that Python can load via ctypes.

Usage:
    python build_bridge.py
"""

import os
import platform
import subprocess
import sys


NATIVE_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_SRC = os.path.join(NATIVE_DIR, "ingestion_bridge.cpp")
ENGINE_SRC = os.path.join(NATIVE_DIR, "ingestion_engine.cpp")


def build_windows():
    """Build with MSVC cl.exe on Windows."""
    output = os.path.join(NATIVE_DIR, "ingestion_bridge.dll")

    # Try cl.exe first (MSVC)
    cmd = [
        "cl", "/LD", "/EHsc", "/O2",
        BRIDGE_SRC, ENGINE_SRC,
        f"/Fe:{output}",
    ]

    print(f"[BUILD] Attempting MSVC build...")
    print(f"[BUILD] Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"[BUILD] ✓ Built: {output}")
            return output
        else:
            print(f"[BUILD] MSVC failed: {result.stderr[:500]}")
    except FileNotFoundError:
        print("[BUILD] cl.exe not found, trying g++...")

    # Fallback to g++ (MinGW)
    output = os.path.join(NATIVE_DIR, "ingestion_bridge.dll")
    cmd = [
        "g++", "-shared", "-O2",
        "-o", output,
        BRIDGE_SRC, ENGINE_SRC,
    ]

    print(f"[BUILD] Attempting MinGW build...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"[BUILD] ✓ Built: {output}")
            return output
        else:
            print(f"[BUILD] g++ failed: {result.stderr[:500]}")
    except FileNotFoundError:
        print("[BUILD] g++ not found either.")

    print("[BUILD] ✗ No C++ compiler available.")
    print("[BUILD]   Install Visual Studio Build Tools or MinGW-w64.")
    return None


def build_linux():
    """Build with g++ on Linux."""
    output = os.path.join(NATIVE_DIR, "libingestion_bridge.so")
    cmd = [
        "g++", "-shared", "-fPIC", "-O2",
        "-o", output,
        BRIDGE_SRC, ENGINE_SRC,
    ]

    print(f"[BUILD] Building with g++...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        print(f"[BUILD] ✓ Built: {output}")
        return output
    else:
        print(f"[BUILD] ✗ Build failed: {result.stderr[:500]}")
        return None


def main():
    """Build the ingestion bridge shared library."""
    print("=" * 60)
    print("  Ingestion Bridge — Build Script")
    print("=" * 60)

    if not os.path.exists(BRIDGE_SRC):
        print(f"[BUILD] ✗ Source not found: {BRIDGE_SRC}")
        sys.exit(1)
    if not os.path.exists(ENGINE_SRC):
        print(f"[BUILD] ✗ Source not found: {ENGINE_SRC}")
        sys.exit(1)

    system = platform.system()
    print(f"[BUILD] Platform: {system}")

    if system == "Windows":
        result = build_windows()
    elif system == "Linux":
        result = build_linux()
    else:
        print(f"[BUILD] Unsupported platform: {system}")
        sys.exit(1)

    if result:
        print(f"\n[BUILD] ✓ SUCCESS: {result}")
        print(f"[BUILD]   Python can load via: ctypes.CDLL('{result}')")
    else:
        print(f"\n[BUILD] ✗ FAILED — see errors above")
        sys.exit(1)


if __name__ == "__main__":
    main()
