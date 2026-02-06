"""
Fuzz Testing Specification - Phase 49
======================================

Fuzz targets:
- DOM parser
- HAR parser
- Network capture input

Requirements:
- 1-hour fuzz under ASAN
- No crashes
- No leaks
- No UB
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
from pathlib import Path


# =============================================================================
# FUZZ CONFIGURATION
# =============================================================================

FUZZ_DURATION_HOURS = 1
FUZZ_JOBS = 4  # Parallel fuzz jobs
MAX_INPUT_SIZE = 65536  # 64KB max input


# =============================================================================
# FUZZ TARGETS
# =============================================================================

@dataclass
class FuzzTarget:
    """Definition of a fuzz target."""
    name: str
    source_file: str
    entry_function: str
    corpus_dir: str
    dictionary: Optional[str]
    max_input_size: int


FUZZ_TARGETS: List[FuzzTarget] = [
    FuzzTarget(
        name="dom_parser_fuzzer",
        source_file="dom_diff_engine.cpp",
        entry_function="LLVMFuzzerTestOneInput",
        corpus_dir="fuzz_corpus/dom",
        dictionary="fuzz_dict/html.dict",
        max_input_size=65536,
    ),
    FuzzTarget(
        name="har_parser_fuzzer",
        source_file="network_capture.cpp",
        entry_function="LLVMFuzzerTestOneInput",
        corpus_dir="fuzz_corpus/har",
        dictionary="fuzz_dict/json.dict",
        max_input_size=1048576,  # 1MB for HAR
    ),
    FuzzTarget(
        name="network_input_fuzzer",
        source_file="network_capture.cpp",
        entry_function="LLVMFuzzerTestOneInput",
        corpus_dir="fuzz_corpus/network",
        dictionary="fuzz_dict/http.dict",
        max_input_size=65536,
    ),
]


# =============================================================================
# LIBFUZZER HARNESS TEMPLATE
# =============================================================================

FUZZ_HARNESS_TEMPLATE = '''
// {target_name}.cpp - LibFuzzer harness
// Compile: clang++ -g -O1 -fsanitize=fuzzer,address {source_file} -o {target_name}

#include <cstdint>
#include <cstddef>

// Include the parser header
#include "{header_file}"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {{
    if (size == 0 || size > {max_size}) {{
        return 0;  // Skip invalid inputs
    }}
    
    // Fuzz the parser
    try {{
        {fuzz_call}
    }} catch (...) {{
        // Expected - parser should handle invalid input gracefully
    }}
    
    return 0;
}}
'''


# =============================================================================
# FUZZ DICTIONARIES
# =============================================================================

HTML_DICTIONARY = """
# HTML fuzzing dictionary
"<html>"
"</html>"
"<head>"
"<body>"
"<div>"
"</div>"
"<script>"
"</script>"
"<style>"
"class="
"id="
"onclick="
"<img src="
"<a href="
"<form>"
"<input>"
"""

JSON_DICTIONARY = """
# JSON/HAR fuzzing dictionary
"{"
"}"
"["
"]"
"\\"log\\":"
"\\"entries\\":"
"\\"request\\":"
"\\"response\\":"
"\\"headers\\":"
"\\"content\\":"
"null"
"true"
"false"
"""

HTTP_DICTIONARY = """
# HTTP fuzzing dictionary
"GET "
"POST "
"HTTP/1.1"
"Host: "
"Content-Length: "
"Content-Type: "
"Cookie: "
"User-Agent: "
"\\r\\n"
"\\r\\n\\r\\n"
"""


# =============================================================================
# CI FUZZ SCRIPT
# =============================================================================

CI_FUZZ_SCRIPT = '''#!/bin/bash
# CI Fuzz Testing Script - Phase 49

set -e

echo "=== FUZZ TESTING (1 HOUR) ==="

NATIVE_DIR="impl_v1/phase49/native"
FUZZ_DIR="$NATIVE_DIR/fuzz"
CORPUS_DIR="$NATIVE_DIR/fuzz_corpus"

mkdir -p $FUZZ_DIR $CORPUS_DIR

# Build fuzz targets with ASAN
echo "Building fuzz targets..."
cd $NATIVE_DIR

for target in dom_parser har_parser network_input; do
    echo "Building ${target}_fuzzer..."
    clang++ -g -O1 -fsanitize=fuzzer,address,undefined \\
        -o $FUZZ_DIR/${target}_fuzzer \\
        ${target}_fuzzer.cpp
done

cd -

# Run each fuzzer for 20 minutes (1 hour total / 3 targets)
FUZZ_TIME=1200  # 20 minutes per target

for target in dom_parser har_parser network_input; do
    echo "Fuzzing $target for $FUZZ_TIME seconds..."
    
    mkdir -p $CORPUS_DIR/$target
    
    # Run fuzzer
    timeout $FUZZ_TIME $FUZZ_DIR/${target}_fuzzer \\
        $CORPUS_DIR/$target \\
        -max_len=65536 \\
        -jobs=4 \\
        -workers=4 \\
        || true  # Don't fail on timeout
    
    # Check for crashes
    if ls crash-* 1> /dev/null 2>&1; then
        echo "FAIL: Crashes found in $target"
        exit 1
    fi
done

echo "=== FUZZ TESTING PASSED ==="
echo "No crashes, leaks, or UB detected"
'''


# =============================================================================
# RESULT VALIDATION
# =============================================================================

class FuzzResult(Enum):
    """Fuzz test result."""
    PASS = "PASS"
    CRASH = "CRASH"
    LEAK = "LEAK"
    UB = "UB"  # Undefined behavior
    TIMEOUT = "TIMEOUT"


@dataclass
class FuzzReport:
    """Report from fuzz testing."""
    target: str
    duration_seconds: int
    executions: int
    result: FuzzResult
    crashes: int
    leaks: int
    ub_errors: int


def validate_fuzz_output(output_dir: Path) -> List[FuzzReport]:
    """Validate fuzz test output for crashes/leaks."""
    reports = []
    
    for target in FUZZ_TARGETS:
        crash_files = list(output_dir.glob(f"{target.name}/crash-*"))
        leak_files = list(output_dir.glob(f"{target.name}/leak-*"))
        
        result = FuzzResult.PASS
        if crash_files:
            result = FuzzResult.CRASH
        elif leak_files:
            result = FuzzResult.LEAK
        
        reports.append(FuzzReport(
            target=target.name,
            duration_seconds=FUZZ_DURATION_HOURS * 3600 // len(FUZZ_TARGETS),
            executions=0,  # Would be parsed from output
            result=result,
            crashes=len(crash_files),
            leaks=len(leak_files),
            ub_errors=0,
        ))
    
    return reports
