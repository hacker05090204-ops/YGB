"""
C++ Memory Hardening Specification - Phase 49
==============================================

COMPILE FLAGS REQUIRED:
-fstack-protector-strong
-D_FORTIFY_SOURCE=2
-fPIE -pie
-Werror -Wall -Wextra -Wshadow
-fsanitize=address (test builds only)

MEMORY SAFETY RULES:
1. No raw new/delete - use smart pointers
2. No unchecked buffer writes
3. No strcpy/sprintf - use safe alternatives
4. All file IO bounded with size limits
"""

from dataclasses import dataclass
from typing import List, Set
from enum import Enum


# =============================================================================
# COMPILE FLAGS
# =============================================================================

REQUIRED_COMPILE_FLAGS: List[str] = [
    "-fstack-protector-strong",  # Stack buffer overflow protection
    "-D_FORTIFY_SOURCE=2",       # Runtime buffer overflow checks
    "-fPIE",                     # Position Independent Executable
    "-pie",                      # PIE linking
    "-Werror",                   # Treat warnings as errors
    "-Wall",                     # Enable all warnings
    "-Wextra",                   # Extra warnings
    "-Wshadow",                  # Warn on variable shadowing
]

DEBUG_COMPILE_FLAGS: List[str] = [
    "-fsanitize=address",        # AddressSanitizer
    "-fsanitize=undefined",      # UndefinedBehaviorSanitizer
    "-g",                        # Debug symbols
]

LINK_FLAGS: List[str] = [
    "-Wl,-z,relro",              # Relocation Read-Only
    "-Wl,-z,now",                # Immediate binding
    "-Wl,-z,noexecstack",        # Non-executable stack
]


# =============================================================================
# FORBIDDEN PATTERNS
# =============================================================================

class CppRiskLevel(Enum):
    """Risk level for C++ patterns."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class ForbiddenPattern:
    """Forbidden C++ pattern."""
    pattern: str
    replacement: str
    risk: CppRiskLevel
    reason: str


FORBIDDEN_CPP_PATTERNS: List[ForbiddenPattern] = [
    ForbiddenPattern(
        pattern="new [A-Za-z]",
        replacement="std::make_unique<T>() or std::make_shared<T>()",
        risk=CppRiskLevel.HIGH,
        reason="Raw new without RAII can leak memory",
    ),
    ForbiddenPattern(
        pattern="delete [A-Za-z]",
        replacement="Smart pointer auto-deletion",
        risk=CppRiskLevel.HIGH,
        reason="Manual delete is error-prone",
    ),
    ForbiddenPattern(
        pattern="strcpy",
        replacement="strncpy or std::string",
        risk=CppRiskLevel.CRITICAL,
        reason="Buffer overflow vulnerability",
    ),
    ForbiddenPattern(
        pattern="sprintf",
        replacement="snprintf or std::format",
        risk=CppRiskLevel.CRITICAL,
        reason="Buffer overflow vulnerability",
    ),
    ForbiddenPattern(
        pattern="gets",
        replacement="fgets with buffer size",
        risk=CppRiskLevel.CRITICAL,
        reason="Always buffer overflow",
    ),
    ForbiddenPattern(
        pattern="scanf\\s*\\(",
        replacement="fgets + sscanf with bounds",
        risk=CppRiskLevel.HIGH,
        reason="Buffer overflow risk",
    ),
    ForbiddenPattern(
        pattern="malloc\\s*\\(",
        replacement="std::vector or smart pointer",
        risk=CppRiskLevel.MEDIUM,
        reason="Manual memory management",
    ),
    ForbiddenPattern(
        pattern="free\\s*\\(",
        replacement="Smart pointer auto-deletion",
        risk=CppRiskLevel.MEDIUM,
        reason="Manual memory management",
    ),
    ForbiddenPattern(
        pattern="realloc\\s*\\(",
        replacement="std::vector::resize()",
        risk=CppRiskLevel.MEDIUM,
        reason="Manual memory management",
    ),
]


# =============================================================================
# SAFE ALTERNATIVES
# =============================================================================

SAFE_PATTERNS = {
    "memory allocation": [
        "std::make_unique<T>()",
        "std::make_shared<T>()",
        "std::vector<T>",
        "std::array<T, N>",
    ],
    "string operations": [
        "std::string",
        "std::string_view",
        "strncpy with explicit size",
        "snprintf with buffer size",
    ],
    "file operations": [
        "std::ifstream with bounds checking",
        "std::ofstream",
        "Read maximum N bytes only",
    ],
    "buffer writes": [
        "std::copy with iterators",
        "std::fill_n with explicit count",
        "memcpy with sizeof() check",
    ],
}


# =============================================================================
# FUZZ TEST SPECIFICATIONS
# =============================================================================

FUZZ_TARGETS = [
    {
        "name": "dom_diff_fuzzer",
        "input": "random HTML/DOM strings",
        "goals": [
            "No crashes",
            "No memory leaks",
            "No undefined behavior",
        ],
    },
    {
        "name": "network_parser_fuzzer",
        "input": "random HTTP headers/bodies",
        "goals": [
            "No buffer overflows",
            "No infinite loops",
            "Graceful error handling",
        ],
    },
    {
        "name": "har_parser_fuzzer",
        "input": "malformed HAR JSON",
        "goals": [
            "No JSON injection",
            "No memory corruption",
            "Size limits enforced",
        ],
    },
]


# =============================================================================
# RESOURCE LIMITS
# =============================================================================

RESOURCE_LIMITS = {
    "max_memory_mb": 512,
    "max_file_size_mb": 100,
    "max_request_size_mb": 10,
    "max_dom_depth": 100,
    "max_string_length": 1_000_000,
}


# =============================================================================
# VALIDATION
# =============================================================================

def get_required_flags() -> List[str]:
    """Get all required compile flags."""
    return REQUIRED_COMPILE_FLAGS + LINK_FLAGS


def get_debug_flags() -> List[str]:
    """Get debug/sanitizer flags."""
    return DEBUG_COMPILE_FLAGS


def get_forbidden_patterns() -> List[ForbiddenPattern]:
    """Get list of forbidden C++ patterns."""
    return FORBIDDEN_CPP_PATTERNS
