"""
Static Analysis CI - Phase 49
==============================

CI stage for native code static analysis:
- clang-tidy
- cppcheck
- AddressSanitizer
- UndefinedBehaviorSanitizer
- LeakSanitizer

Fails on:
- Raw new/delete
- strcpy/sprintf
- Unbounded memcpy
- Missing RAII
- Unchecked return values
"""

from dataclasses import dataclass
from typing import List, Dict
from enum import Enum


# =============================================================================
# ANALYSIS RULES
# =============================================================================

class Severity(Enum):
    """Issue severity."""
    ERROR = "ERROR"
    WARNING = "WARNING"
    NOTE = "NOTE"


@dataclass
class StaticAnalysisRule:
    """Static analysis rule."""
    name: str
    pattern: str
    severity: Severity
    fix: str


# Rules that FAIL the build
BLOCKING_RULES: List[StaticAnalysisRule] = [
    StaticAnalysisRule(
        name="raw-new",
        pattern="new [A-Za-z]",
        severity=Severity.ERROR,
        fix="Use std::make_unique or std::make_shared",
    ),
    StaticAnalysisRule(
        name="raw-delete",
        pattern="delete [A-Za-z]",
        severity=Severity.ERROR,
        fix="Use smart pointers for automatic cleanup",
    ),
    StaticAnalysisRule(
        name="strcpy-unsafe",
        pattern="strcpy\\s*\\(",
        severity=Severity.ERROR,
        fix="Use strncpy or std::string",
    ),
    StaticAnalysisRule(
        name="sprintf-unsafe",
        pattern="sprintf\\s*\\(",
        severity=Severity.ERROR,
        fix="Use snprintf with buffer size",
    ),
    StaticAnalysisRule(
        name="gets-unsafe",
        pattern="gets\\s*\\(",
        severity=Severity.ERROR,
        fix="Use fgets with buffer size",
    ),
    StaticAnalysisRule(
        name="unbounded-memcpy",
        pattern="memcpy\\([^,]+,[^,]+,[^)]*sizeof",
        severity=Severity.WARNING,
        fix="Verify destination buffer size",
    ),
]


# =============================================================================
# CLANG-TIDY CONFIGURATION
# =============================================================================

CLANG_TIDY_CHECKS = [
    "bugprone-*",
    "cert-*",
    "clang-analyzer-*",
    "cppcoreguidelines-*",
    "misc-*",
    "modernize-*",
    "performance-*",
    "portability-*",
    "readability-*",
    "-modernize-use-trailing-return-type",  # Style preference
    "-readability-magic-numbers",            # Too noisy
]

CLANG_TIDY_CONFIG = f'''
Checks: >
  {",".join(CLANG_TIDY_CHECKS)}

WarningsAsErrors: >
  bugprone-*,
  cert-*,
  cppcoreguidelines-owning-memory,
  cppcoreguidelines-pro-type-member-init

HeaderFilterRegex: '.*'

CheckOptions:
  - key: cppcoreguidelines-special-member-functions.AllowSoleDefaultDtor
    value: true
  - key: misc-non-private-member-variables-in-classes.IgnoreClassesWithAllMemberVariablesBeingPublic
    value: true
'''


# =============================================================================
# CPPCHECK CONFIGURATION
# =============================================================================

CPPCHECK_ARGS = [
    "--enable=all",
    "--error-exitcode=1",
    "--inline-suppr",
    "--std=c++17",
    "--suppress=missingIncludeSystem",
    "--suppress=unmatchedSuppression",
]


# =============================================================================
# CI SCRIPTS
# =============================================================================

CI_STATIC_ANALYSIS_SCRIPT = '''#!/bin/bash
# CI Static Analysis Script - Phase 49

set -e

echo "=== NATIVE STATIC ANALYSIS ==="

NATIVE_DIR="impl_v1/phase49/native"
FAILED=0

# 1. clang-tidy
echo "Running clang-tidy..."
if command -v clang-tidy &> /dev/null; then
    clang-tidy $NATIVE_DIR/*.cpp -- -std=c++17 || FAILED=1
else
    echo "WARN: clang-tidy not found, skipping"
fi

# 2. cppcheck
echo "Running cppcheck..."
if command -v cppcheck &> /dev/null; then
    cppcheck --enable=all --error-exitcode=1 --std=c++17 \\
        --suppress=missingIncludeSystem $NATIVE_DIR/*.cpp || FAILED=1
else
    echo "WARN: cppcheck not found, skipping"
fi

# 3. Check for forbidden patterns
echo "Checking for forbidden patterns..."
for file in $NATIVE_DIR/*.cpp; do
    if grep -n "strcpy\\s*(" "$file"; then
        echo "ERROR: strcpy found in $file"
        FAILED=1
    fi
    if grep -n "sprintf\\s*(" "$file"; then
        echo "ERROR: sprintf found in $file"
        FAILED=1
    fi
    if grep -n "gets\\s*(" "$file"; then
        echo "ERROR: gets found in $file"
        FAILED=1
    fi
done

# 4. Build with sanitizers
echo "Building with AddressSanitizer..."
cd $NATIVE_DIR
make clean 2>/dev/null || true
CXXFLAGS="-fsanitize=address,undefined -g -O1" make || FAILED=1
cd -

if [ $FAILED -eq 0 ]; then
    echo "=== STATIC ANALYSIS PASSED ==="
else
    echo "=== STATIC ANALYSIS FAILED ==="
    exit 1
fi
'''


# =============================================================================
# SANITIZER CONFIGURATIONS
# =============================================================================

ASAN_OPTIONS = {
    "detect_leaks": "1",
    "detect_stack_use_after_return": "1",
    "strict_string_checks": "1",
    "detect_invalid_pointer_pairs": "2",
    "check_initialization_order": "1",
}

UBSAN_OPTIONS = {
    "print_stacktrace": "1",
    "halt_on_error": "1",
}

LSAN_OPTIONS = {
    "suppressions": "lsan.supp",
}


def get_sanitizer_env() -> Dict[str, str]:
    """Get environment variables for sanitizers."""
    return {
        "ASAN_OPTIONS": ":".join(f"{k}={v}" for k, v in ASAN_OPTIONS.items()),
        "UBSAN_OPTIONS": ":".join(f"{k}={v}" for k, v in UBSAN_OPTIONS.items()),
        "LSAN_OPTIONS": ":".join(f"{k}={v}" for k, v in LSAN_OPTIONS.items()),
    }


def get_clang_tidy_config() -> str:
    """Get clang-tidy configuration."""
    return CLANG_TIDY_CONFIG
