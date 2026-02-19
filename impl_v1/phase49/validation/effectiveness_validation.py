"""
Effectiveness Validation - Phase 49
=====================================

Test scanning pipeline against known samples:
- 100 vulnerable apps (true positives)
- 100 clean apps (true negatives)

Measure:
- True Positive Rate (TPR)
- False Positive Rate (FPR)  
- False Negative Rate (FNR)
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple
from pathlib import Path
from enum import Enum
import json
from typing import Callable


# =============================================================================
# TEST SUITE CONFIGURATION
# =============================================================================

class VulnerabilityType(Enum):
    """Known vulnerability types for testing."""
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "cmd_injection"
    SSRF = "ssrf"
    XXE = "xxe"
    DESERIALIZATION = "deserialization"
    AUTH_BYPASS = "auth_bypass"
    IDOR = "idor"
    OPEN_REDIRECT = "open_redirect"


@dataclass
class TestCase:
    """A test case for effectiveness validation."""
    id: str
    name: str
    is_vulnerable: bool
    vulnerability_type: VulnerabilityType | None
    payload: str
    expected_detection: bool


@dataclass
class ScanResult:
    """Result from scanning a test case."""
    test_id: str
    detected: bool
    confidence: float
    detection_type: str | None


# =============================================================================
# TEST SUITE GENERATOR
# =============================================================================

def generate_vulnerable_cases(count: int = 100) -> List[TestCase]:
    """Generate known vulnerable test cases."""
    cases = []
    vuln_types = list(VulnerabilityType)
    
    for i in range(count):
        vuln_type = vuln_types[i % len(vuln_types)]
        
        cases.append(TestCase(
            id=f"VULN_{i:03d}",
            name=f"Vulnerable App {i} - {vuln_type.value}",
            is_vulnerable=True,
            vulnerability_type=vuln_type,
            payload=f"test_payload_{vuln_type.value}_{i}",
            expected_detection=True,
        ))
    
    return cases


def generate_clean_cases(count: int = 100) -> List[TestCase]:
    """Generate known clean test cases."""
    cases = []
    
    for i in range(count):
        cases.append(TestCase(
            id=f"CLEAN_{i:03d}",
            name=f"Clean App {i}",
            is_vulnerable=False,
            vulnerability_type=None,
            payload=f"safe_content_{i}",
            expected_detection=False,
        ))
    
    return cases


# =============================================================================
# METRICS CALCULATION
# =============================================================================

@dataclass
class EffectivenessMetrics:
    """Effectiveness metrics from test run."""
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    
    @property
    def tpr(self) -> float:
        """True Positive Rate (Sensitivity)."""
        total_positives = self.true_positives + self.false_negatives
        return self.true_positives / total_positives if total_positives > 0 else 0.0
    
    @property
    def fpr(self) -> float:
        """False Positive Rate."""
        total_negatives = self.true_negatives + self.false_positives
        return self.false_positives / total_negatives if total_negatives > 0 else 0.0
    
    @property
    def fnr(self) -> float:
        """False Negative Rate."""
        return 1.0 - self.tpr
    
    @property
    def precision(self) -> float:
        """Precision."""
        total_predicted = self.true_positives + self.false_positives
        return self.true_positives / total_predicted if total_predicted > 0 else 0.0
    
    @property
    def f1_score(self) -> float:
        """F1 Score."""
        if self.precision + self.tpr == 0:
            return 0.0
        return 2 * (self.precision * self.tpr) / (self.precision + self.tpr)


def calculate_metrics(
    cases: List[TestCase],
    results: List[ScanResult],
) -> EffectivenessMetrics:
    """Calculate effectiveness metrics from test results."""
    tp = tn = fp = fn = 0
    
    result_map = {r.test_id: r for r in results}
    
    for case in cases:
        result = result_map.get(case.id)
        if not result:
            continue
        
        if case.is_vulnerable:
            if result.detected:
                tp += 1
            else:
                fn += 1
        else:
            if result.detected:
                fp += 1
            else:
                tn += 1
    
    return EffectivenessMetrics(
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
    )


# =============================================================================
# SCANNER INTERFACE — Real scanner required, no mock
# =============================================================================

class RequireScannerError(RuntimeError):
    """Raised when no real scanner is provided for validation."""
    pass


def scan_case(
    case: TestCase,
    scanner: Callable[[TestCase], ScanResult],
) -> ScanResult:
    """
    Scan a test case using the provided REAL scanner.

    Args:
        case: Test case to scan.
        scanner: A callable that implements real detection logic.

    Returns:
        ScanResult from the real scanner.
    """
    if scanner is None:
        raise RequireScannerError(
            "A real scanner implementation is required. "
            "No mock/simulated scanning is allowed."
        )
    return scanner(case)


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_effectiveness_validation(
    scanner: Callable[[TestCase], ScanResult],
) -> tuple[EffectivenessMetrics, dict]:
    """
    Run full effectiveness validation.

    Args:
        scanner: Real scanner callable — REQUIRED. No mock fallback.
    """
    if scanner is None:
        raise RequireScannerError(
            "Real scanner required for effectiveness validation."
        )

    # Generate test cases
    vulnerable = generate_vulnerable_cases(100)
    clean = generate_clean_cases(100)
    all_cases = vulnerable + clean

    # Run scans using real scanner
    results = [scan_case(case, scanner) for case in all_cases]

    # Calculate metrics
    metrics = calculate_metrics(all_cases, results)

    # Generate detailed report
    report = {
        "total_cases": len(all_cases),
        "vulnerable_cases": len(vulnerable),
        "clean_cases": len(clean),
        "metrics": {
            "true_positive_rate": round(metrics.tpr, 4),
            "false_positive_rate": round(metrics.fpr, 4),
            "false_negative_rate": round(metrics.fnr, 4),
            "precision": round(metrics.precision, 4),
            "f1_score": round(metrics.f1_score, 4),
        },
        "counts": {
            "true_positives": metrics.true_positives,
            "true_negatives": metrics.true_negatives,
            "false_positives": metrics.false_positives,
            "false_negatives": metrics.false_negatives,
        },
    }

    return metrics, report
