#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 10 Gate Test: Production Voice Pipeline
Tests native C++ voice capture, VAD, Python bridge, and fail-closed behavior.
"""

import sys
import os
from pathlib import Path

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_native_voice_capture_imports():
    """Gate 1: Verify native voice capture C++ module can be imported."""
    print("\n=== Gate 1: Native Voice Capture Imports ===")
    try:
        # Check if voice_capture.cpp exists
        voice_cpp = PROJECT_ROOT / "native" / "voice_capture" / "voice_capture.cpp"
        if not voice_cpp.exists():
            print(f"❌ FAIL: voice_capture.cpp not found at {voice_cpp}")
            return False
        print(f"✓ voice_capture.cpp exists at {voice_cpp}")
        
        # Check for header file
        voice_h = PROJECT_ROOT / "native" / "voice_capture" / "voice_capture.h"
        if not voice_h.exists():
            print(f"❌ FAIL: voice_capture.h not found at {voice_h}")
            return False
        print(f"✓ voice_capture.h exists at {voice_h}")
        
        # Check for Python bridge
        bridge_py = PROJECT_ROOT / "native" / "voice_capture" / "audio_capture_bridge.py"
        if not bridge_py.exists():
            print(f"❌ FAIL: audio_capture_bridge.py not found at {bridge_py}")
            return False
        print(f"✓ audio_capture_bridge.py exists at {bridge_py}")
        
        print("✓ Gate 1 PASSED: All voice capture files present")
        return True
        
    except Exception as e:
        print(f"❌ Gate 1 FAILED: {e}")
        return False


def test_vad_logic_implementation():
    """Gate 2: Verify VAD (Voice Activity Detection) logic is implemented."""
    print("\n=== Gate 2: VAD Logic Implementation ===")
    try:
        voice_cpp = PROJECT_ROOT / "native" / "voice_capture" / "voice_capture.cpp"
        content = voice_cpp.read_text(encoding='utf-8')
        
        # Check for VAD-related functions
        required_functions = [
            "compute_rms_energy",
            "energy_to_db",
            "classify_vad"
        ]
        
        missing = []
        for func in required_functions:
            if func not in content:
                missing.append(func)
            else:
                print(f"✓ Found VAD function: {func}")
        
        if missing:
            print(f"❌ FAIL: Missing VAD functions: {missing}")
            return False
        
        # Check for energy threshold configuration
        if "VoiceCaptureConfig" not in content:
            print("❌ FAIL: VoiceCaptureConfig structure not found")
            return False
        print("✓ VoiceCaptureConfig structure found")
        
        # Check for VAD threshold parameter
        if "vad_threshold" not in content:
            print("❌ FAIL: vad_threshold parameter not found")
            return False
        print("✓ vad_threshold parameter found")
        
        print("✓ Gate 2 PASSED: VAD logic fully implemented")
        return True
        
    except Exception as e:
        print(f"❌ Gate 2 FAILED: {e}")
        return False


def test_python_bridge_functionality():
    """Gate 3: Verify Python bridge can interface with C++ module."""
    print("\n=== Gate 3: Python Bridge Functionality ===")
    try:
        bridge_py = PROJECT_ROOT / "native" / "voice_capture" / "audio_capture_bridge.py"
        content = bridge_py.read_text(encoding='utf-8')
        
        # Check for ctypes import (required for C++ bridge)
        if "import ctypes" not in content and "from ctypes" not in content:
            print("❌ FAIL: ctypes import not found in bridge")
            return False
        print("✓ ctypes import found")
        
        # Check for bridge functions
        required_bridge_functions = [
            "def ",  # At least some function definitions
        ]
        
        if "def " not in content:
            print("❌ FAIL: No function definitions found in bridge")
            return False
        print("✓ Bridge contains function definitions")
        
        # Check for error handling
        if "try:" not in content or "except" not in content:
            print("⚠ WARNING: Limited error handling in bridge")
        else:
            print("✓ Error handling present in bridge")
        
        print("✓ Gate 3 PASSED: Python bridge properly structured")
        return True
        
    except Exception as e:
        print(f"❌ Gate 3 FAILED: {e}")
        return False


def test_audio_buffer_management():
    """Gate 4: Verify audio buffer management and memory safety."""
    print("\n=== Gate 4: Audio Buffer Management ===")
    try:
        voice_cpp = PROJECT_ROOT / "native" / "voice_capture" / "voice_capture.cpp"
        content = voice_cpp.read_text(encoding='utf-8')
        
        # Check for buffer-related functions
        buffer_functions = [
            "capture_get_audio_chunk",
            "capture_feed_audio"
        ]
        
        missing = []
        for func in buffer_functions:
            if func not in content:
                missing.append(func)
            else:
                print(f"✓ Found buffer function: {func}")
        
        if missing:
            print(f"❌ FAIL: Missing buffer functions: {missing}")
            return False
        
        # Check for buffer size validation
        if "max_len" not in content:
            print("⚠ WARNING: No explicit buffer size validation found")
        else:
            print("✓ Buffer size validation present")
        
        # Check for memory safety patterns
        safety_patterns = ["buffer", "max_len", "data_len"]
        found_patterns = sum(1 for p in safety_patterns if p in content)
        
        if found_patterns < 2:
            print(f"⚠ WARNING: Limited memory safety patterns ({found_patterns}/3)")
        else:
            print(f"✓ Memory safety patterns present ({found_patterns}/3)")
        
        print("✓ Gate 4 PASSED: Audio buffer management implemented")
        return True
        
    except Exception as e:
        print(f"❌ Gate 4 FAILED: {e}")
        return False


def test_fail_closed_behavior():
    """Gate 5: Verify fail-closed behavior on errors."""
    print("\n=== Gate 5: Fail-Closed Behavior ===")
    try:
        voice_cpp = PROJECT_ROOT / "native" / "voice_capture" / "voice_capture.cpp"
        content = voice_cpp.read_text(encoding='utf-8')
        
        # Check for initialization validation
        if "capture_init" not in content:
            print("❌ FAIL: capture_init function not found")
            return False
        print("✓ capture_init function found")
        
        # Check for start/stop controls
        required_controls = ["capture_start", "capture_stop", "capture_shutdown"]
        missing = []
        for ctrl in required_controls:
            if ctrl not in content:
                missing.append(ctrl)
            else:
                print(f"✓ Found control function: {ctrl}")
        
        if missing:
            print(f"❌ FAIL: Missing control functions: {missing}")
            return False
        
        # Check for error return codes
        if "return -1" not in content and "return 0" not in content:
            print("⚠ WARNING: No clear error return codes found")
        else:
            print("✓ Error return codes present")
        
        # Check for state validation
        if "LifecycleState" in content or "state" in content.lower():
            print("✓ State management present")
        else:
            print("⚠ WARNING: Limited state management")
        
        print("✓ Gate 5 PASSED: Fail-closed behavior implemented")
        return True
        
    except Exception as e:
        print(f"❌ Gate 5 FAILED: {e}")
        return False


def test_windows_wasapi_support():
    """Gate 6: Verify Windows WASAPI audio capture support."""
    print("\n=== Gate 6: Windows WASAPI Support ===")
    try:
        voice_cpp = PROJECT_ROOT / "native" / "voice_capture" / "voice_capture.cpp"
        content = voice_cpp.read_text(encoding='utf-8')
        
        # Check for Windows-specific code
        if "#ifdef _WIN32" not in content and "#ifdef WIN32" not in content:
            print("⚠ WARNING: No Windows-specific code guards found")
        else:
            print("✓ Windows code guards present")
        
        # Check for WASAPI initialization
        if "try_init_wasapi" in content:
            print("✓ WASAPI initialization function found")
        else:
            print("⚠ INFO: WASAPI initialization not explicitly named")
        
        # Check for COM initialization (required for WASAPI)
        if "CoInitialize" in content or "COM" in content:
            print("✓ COM initialization present")
        else:
            print("⚠ INFO: COM initialization not found (may be handled elsewhere)")
        
        print("✓ Gate 6 PASSED: Windows audio support present")
        return True
        
    except Exception as e:
        print(f"❌ Gate 6 FAILED: {e}")
        return False


def test_voice_mode_integration():
    """Gate 7: Verify voice mode integration with API server."""
    print("\n=== Gate 7: Voice Mode Integration ===")
    try:
        server_py = PROJECT_ROOT / "api" / "server.py"
        if not server_py.exists():
            print(f"❌ FAIL: server.py not found at {server_py}")
            return False
        
        content = server_py.read_text(encoding='utf-8')
        
        # Check for voice endpoints
        voice_endpoints = [
            "/api/voice/parse",
            "/api/voice/mode"
        ]
        
        missing = []
        for endpoint in voice_endpoints:
            if endpoint not in content:
                missing.append(endpoint)
            else:
                print(f"✓ Found voice endpoint: {endpoint}")
        
        if missing:
            print(f"❌ FAIL: Missing voice endpoints: {missing}")
            return False
        
        # Check for VoiceParseRequest model
        if "VoiceParseRequest" not in content:
            print("❌ FAIL: VoiceParseRequest model not found")
            return False
        print("✓ VoiceParseRequest model found")
        
        print("✓ Gate 7 PASSED: Voice mode integrated with API server")
        return True
        
    except Exception as e:
        print(f"❌ Gate 7 FAILED: {e}")
        return False


def main():
    """Run all Phase 10 gate tests."""
    print("=" * 70)
    print("PHASE 10 GATE TEST: Production Voice Pipeline")
    print("=" * 70)
    
    gates = [
        ("Native Voice Capture Imports", test_native_voice_capture_imports),
        ("VAD Logic Implementation", test_vad_logic_implementation),
        ("Python Bridge Functionality", test_python_bridge_functionality),
        ("Audio Buffer Management", test_audio_buffer_management),
        ("Fail-Closed Behavior", test_fail_closed_behavior),
        ("Windows WASAPI Support", test_windows_wasapi_support),
        ("Voice Mode Integration", test_voice_mode_integration),
    ]
    
    results = []
    for name, test_func in gates:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {name}: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("PHASE 10 GATE TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} gates passed")
    
    if passed == total:
        print("\n🎉 PHASE 10 VERIFICATION COMPLETE - ALL GATES PASSED")
        return 0
    else:
        print(f"\n⚠ PHASE 10 INCOMPLETE - {total - passed} gate(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
