"""
Coverage Enforcement - Phase 49
================================

CI enforcement for code coverage:
- Python: ≥ 95% branch coverage
- C++: ≥ 85% branch coverage

Blocks merge if below thresholds.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum
import json
from pathlib import Path


# =============================================================================
# THRESHOLDS
# =============================================================================

PYTHON_COVERAGE_THRESHOLD = 95.0  # Minimum Python coverage %
CPP_COVERAGE_THRESHOLD = 85.0     # Minimum C++ coverage %

# Files to exclude from coverage
COVERAGE_EXCLUDE = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/migrations/*",
    "setup.py",
]


# =============================================================================
# COVERAGE RESULT
# =============================================================================

class CoverageStatus(Enum):
    """Coverage check status."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"  # Below target but above minimum


@dataclass
class CoverageResult:
    """Coverage check result."""
    language: str
    measured: float
    threshold: float
    status: CoverageStatus
    details: Dict[str, float]


# =============================================================================
# PYTHON COVERAGE
# =============================================================================

def get_pytest_coverage_command() -> str:
    """Get pytest command with coverage."""
    return (
        "python -m pytest impl_v1/phase49/tests/ "
        "--cov=impl_v1/phase49 "
        "--cov-branch "
        "--cov-report=json:coverage.json "
        "--cov-report=term-missing "
        "--cov-fail-under=95"
    )


def parse_python_coverage(coverage_json: Path) -> CoverageResult:
    """Parse coverage.json from pytest-cov."""
    try:
        with open(coverage_json, "r") as f:
            data = json.load(f)
        
        total = data.get("totals", {})
        percent = total.get("percent_covered", 0.0)
        
        # Get per-file details
        details = {}
        for file_path, file_data in data.get("files", {}).items():
            details[file_path] = file_data.get("summary", {}).get("percent_covered", 0.0)
        
        status = CoverageStatus.PASS if percent >= PYTHON_COVERAGE_THRESHOLD else CoverageStatus.FAIL
        
        return CoverageResult(
            language="Python",
            measured=percent,
            threshold=PYTHON_COVERAGE_THRESHOLD,
            status=status,
            details=details,
        )
    except Exception as e:
        return CoverageResult(
            language="Python",
            measured=0.0,
            threshold=PYTHON_COVERAGE_THRESHOLD,
            status=CoverageStatus.FAIL,
            details={"error": str(e)},
        )


# =============================================================================
# C++ COVERAGE
# =============================================================================

def get_gcov_commands() -> list:
    """Get commands for C++ coverage with gcov."""
    return [
        "# Compile with coverage",
        "g++ -fprofile-arcs -ftest-coverage -O0 -o test_engine test_engine.cpp",
        "",
        "# Run tests",
        "./test_engine",
        "",
        "# Generate coverage report",
        "gcov test_engine.cpp",
        "lcov --capture --directory . --output-file coverage.info",
        "genhtml coverage.info --output-directory coverage_html",
    ]


def get_llvm_cov_commands() -> list:
    """Get commands for C++ coverage with llvm-cov."""
    return [
        "# Compile with coverage (clang)",
        "clang++ -fprofile-instr-generate -fcoverage-mapping -o test_engine test_engine.cpp",
        "",
        "# Run and generate raw profile",
        "LLVM_PROFILE_FILE=test.profraw ./test_engine",
        "",
        "# Merge profile data",
        "llvm-profdata merge -sparse test.profraw -o test.profdata",
        "",
        "# Generate report",
        "llvm-cov report ./test_engine -instr-profile=test.profdata",
        "llvm-cov show ./test_engine -instr-profile=test.profdata --format=html > coverage.html",
    ]


# =============================================================================
# CI ENFORCEMENT
# =============================================================================

CI_COVERAGE_SCRIPT = '''#!/bin/bash
# CI Coverage Enforcement Script

set -e

echo "=== COVERAGE ENFORCEMENT ==="

# Python coverage
echo "Checking Python coverage..."
python -m pytest impl_v1/phase49/tests/ \
    --cov=impl_v1/phase49 \
    --cov-branch \
    --cov-report=json:coverage.json \
    --cov-fail-under=95

if [ $? -eq 0 ]; then
    echo "PASS: Python coverage >= 95%"
else
    echo "FAIL: Python coverage < 95%"
    exit 1
fi

# C++ coverage (if applicable)
if [ -f impl_v1/phase49/native/Makefile ]; then
    echo "Checking C++ coverage..."
    cd impl_v1/phase49/native
    make clean
    CXXFLAGS="$CXXFLAGS -fprofile-arcs -ftest-coverage" make test
    
    # Check line coverage
    gcov *.cpp 2>/dev/null | grep -E "Lines executed" | while read line; do
        percent=$(echo $line | grep -oP "\\d+\\.\\d+" | head -1)
        if (( $(echo "$percent < 85" | bc -l) )); then
            echo "FAIL: C++ coverage $percent% < 85%"
            exit 1
        fi
    done
    echo "PASS: C++ coverage >= 85%"
    cd -
fi

echo "=== COVERAGE ENFORCEMENT PASSED ==="
'''


def check_coverage_enforcement(
    python_percent: float,
    cpp_percent: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Check if coverage meets enforcement thresholds.
    
    Returns:
        Tuple of (passes, reason)
    """
    if python_percent < PYTHON_COVERAGE_THRESHOLD:
        return False, f"Python coverage {python_percent:.1f}% < {PYTHON_COVERAGE_THRESHOLD}%"
    
    if cpp_percent is not None and cpp_percent < CPP_COVERAGE_THRESHOLD:
        return False, f"C++ coverage {cpp_percent:.1f}% < {CPP_COVERAGE_THRESHOLD}%"
    
    return True, "All coverage thresholds met"
