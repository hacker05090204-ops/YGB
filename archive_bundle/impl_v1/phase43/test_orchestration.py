# Phase-43: Test Orchestration Engine
"""Precision test selection and early-exit logic."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import uuid
from datetime import datetime


class TestDecision(Enum):
    """CLOSED ENUM - 5 members"""
    RUN = "RUN"
    SKIP = "SKIP"
    CHAIN = "CHAIN"
    EXIT_EARLY = "EXIT_EARLY"
    ESCALATE = "ESCALATE"


class ExitReason(Enum):
    """CLOSED ENUM - 6 members"""
    ALL_PASS = "ALL_PASS"
    CRITICAL_FAIL = "CRITICAL_FAIL"
    RATE_LIMIT = "RATE_LIMIT"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    TIMEOUT = "TIMEOUT"
    NO_EXIT = "NO_EXIT"


class ChainType(Enum):
    """CLOSED ENUM - 4 members"""
    SEQUENTIAL = "SEQUENTIAL"
    DEPENDENT = "DEPENDENT"
    PARALLEL_SAFE = "PARALLEL_SAFE"
    NONE = "NONE"


@dataclass(frozen=True)
class TestSpec:
    """Frozen dataclass for test specification."""
    test_id: str
    priority: int  # 1-10
    chain_type: ChainType
    depends_on: tuple  # tuple of test_ids
    target_id: str


@dataclass(frozen=True)
class TestResult:
    """Frozen dataclass for test result."""
    test_id: str
    decision: TestDecision
    exit_reason: ExitReason
    chained_tests: tuple
    explanation: str


def should_run_test(
    spec: TestSpec,
    completed_tests: List[str],
    failed_tests: List[str],
) -> TestResult:
    """Determine if a test should run."""
    # Check dependencies
    for dep in spec.depends_on:
        if dep not in completed_tests:
            return TestResult(
                test_id=spec.test_id,
                decision=TestDecision.SKIP,
                exit_reason=ExitReason.NO_EXIT,
                chained_tests=(),
                explanation=f"Dependency {dep} not completed",
            )
        if dep in failed_tests:
            return TestResult(
                test_id=spec.test_id,
                decision=TestDecision.EXIT_EARLY,
                exit_reason=ExitReason.CRITICAL_FAIL,
                chained_tests=(),
                explanation=f"Dependency {dep} failed",
            )
    
    return TestResult(
        test_id=spec.test_id,
        decision=TestDecision.RUN,
        exit_reason=ExitReason.NO_EXIT,
        chained_tests=(),
        explanation="All dependencies satisfied",
    )


def check_early_exit(
    failed_tests: List[str],
    critical_threshold: int = 3,
) -> Optional[ExitReason]:
    """Check if early exit is warranted."""
    if len(failed_tests) >= critical_threshold:
        return ExitReason.CRITICAL_FAIL
    return None
