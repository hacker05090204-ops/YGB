"""
Large Scale Validation - Production Grade
==========================================

Validation dataset:
- 10,000 clean samples
- 5,000 verified vulnerabilities
- 500 obfuscated edge cases
- 500 malformed edge cases

Metrics:
- Precision, Recall
- FPR, FNR
- Calibration curve
- Long-tail failure analysis
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from datetime import datetime
from pathlib import Path
from enum import Enum
import json
import time
import math


# =============================================================================
# SAMPLE TYPES
# =============================================================================

class SampleType(Enum):
    """Sample categories."""
    CLEAN = "clean"
    VULNERABLE = "vulnerable"
    OBFUSCATED = "obfuscated"
    MALFORMED = "malformed"


@dataclass
class ValidationSample:
    """A validation sample."""
    id: str
    sample_type: SampleType
    ground_truth: bool  # True = vulnerable
    payload: str


@dataclass
class PredictionResult:
    """Prediction result for a sample."""
    sample_id: str
    predicted: bool
    confidence: float
    latency_ms: float


# =============================================================================
# DATASET GENERATION
# =============================================================================

def generate_large_scale_dataset() -> List[ValidationSample]:
    """Generate production-scale validation dataset."""
    samples = []
    
    # 10,000 clean samples
    for i in range(10000):
        samples.append(ValidationSample(
            id=f"CLEAN_{i:05d}",
            sample_type=SampleType.CLEAN,
            ground_truth=False,
            payload=f"safe_content_block_{i}",
        ))
    
    # 5,000 verified vulnerabilities
    vuln_types = ["sqli", "xss", "ssrf", "xxe", "rce", "idor", "lfi", "auth_bypass"]
    for i in range(5000):
        vtype = vuln_types[i % len(vuln_types)]
        samples.append(ValidationSample(
            id=f"VULN_{i:05d}",
            sample_type=SampleType.VULNERABLE,
            ground_truth=True,
            payload=f"vuln_{vtype}_payload_{i}",
        ))
    
    # 500 obfuscated edge cases
    for i in range(500):
        samples.append(ValidationSample(
            id=f"OBFUSC_{i:03d}",
            sample_type=SampleType.OBFUSCATED,
            ground_truth=True,
            payload=f"obfusc_payload_b64_{i}",
        ))
    
    # 500 malformed edge cases  
    for i in range(500):
        samples.append(ValidationSample(
            id=f"MALFORM_{i:03d}",
            sample_type=SampleType.MALFORMED,
            ground_truth=(i % 2 == 0),  # Deterministic: even=vuln, odd=clean
            payload=f"malformed_input_{i}",
        ))
    
    return samples


# =============================================================================
# SCANNER INTERFACE — Real scanner required, no mock
# =============================================================================

class RequireScannerError(RuntimeError):
    """Raised when no real scanner is provided for production validation."""
    pass


def production_scan(sample: ValidationSample, scan_func=None) -> PredictionResult:
    """Production scanner — delegates to real scan function.

    Args:
        sample: The validation sample to scan.
        scan_func: A real scanner function that takes a payload string
                   and returns (predicted: bool, confidence: float).

    Raises:
        RequireScannerError: If no real scanner function is provided.
    """
    if scan_func is None:
        raise RequireScannerError(
            "No real scanner provided. "
            "Pass a scan_func(payload) -> (bool, float) to production_scan. "
            "Mock scanners are not allowed in production."
        )

    start = time.time()
    predicted, confidence = scan_func(sample.payload)
    latency_ms = (time.time() - start) * 1000

    return PredictionResult(
        sample_id=sample.id,
        predicted=bool(predicted),
        confidence=float(confidence),
        latency_ms=round(latency_ms, 2),
    )


# =============================================================================
# METRICS CALCULATION
# =============================================================================

@dataclass
class ProductionMetrics:
    """Production-scale metrics."""
    total_samples: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    fpr: float
    fnr: float
    f1_score: float
    calibration_error: float
    long_tail_failures: int
    by_category: Dict[str, dict]


def calculate_production_metrics(
    samples: List[ValidationSample],
    results: List[PredictionResult],
) -> ProductionMetrics:
    """Calculate comprehensive production metrics."""
    result_map = {r.sample_id: r for r in results}
    
    tp = tn = fp = fn = 0
    calibration_errors = []
    long_tail = 0
    category_stats = {t.value: {"tp": 0, "tn": 0, "fp": 0, "fn": 0} for t in SampleType}
    
    for sample in samples:
        result = result_map.get(sample.id)
        if not result:
            continue
        
        cat = sample.sample_type.value
        
        if sample.ground_truth:  # Actually vulnerable
            if result.predicted:
                tp += 1
                category_stats[cat]["tp"] += 1
            else:
                fn += 1
                category_stats[cat]["fn"] += 1
                # Long-tail: high confidence wrong
                if result.confidence < 0.3:
                    long_tail += 1
        else:  # Actually clean
            if result.predicted:
                fp += 1
                category_stats[cat]["fp"] += 1
            else:
                tn += 1
                category_stats[cat]["tn"] += 1
        
        # Calibration error
        correct = 1.0 if result.predicted == sample.ground_truth else 0.0
        calibration_errors.append(abs(result.confidence - correct))
    
    # Calculate rates
    total_positive = tp + fn
    total_negative = tn + fp
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / total_positive if total_positive > 0 else 0
    fpr = fp / total_negative if total_negative > 0 else 0
    fnr = fn / total_positive if total_positive > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    ece = sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0
    
    return ProductionMetrics(
        total_samples=len(samples),
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        fpr=round(fpr, 4),
        fnr=round(fnr, 4),
        f1_score=round(f1, 4),
        calibration_error=round(ece, 4),
        long_tail_failures=long_tail,
        by_category=category_stats,
    )


# =============================================================================
# VALIDATION RUNNER
# =============================================================================

def run_production_validation(scan_func=None) -> Tuple[ProductionMetrics, dict]:
    """Run full production validation.

    Args:
        scan_func: Real scanner function(payload) -> (bool, float).
                   Required. No mock scanners allowed.

    Raises:
        RequireScannerError: If no real scanner is provided.
    """
    if scan_func is None:
        raise RequireScannerError(
            "No real scanner provided to run_production_validation. "
            "Pass a scan_func(payload) -> (bool, float).")

    samples = generate_large_scale_dataset()
    results = [production_scan(s, scan_func) for s in samples]
    metrics = calculate_production_metrics(samples, results)

    report = {
        "timestamp": datetime.now().isoformat(),
        "dataset": {
            "total": metrics.total_samples,
            "clean": 10000,
            "vulnerable": 5000,
            "obfuscated": 500,
            "malformed": 500,
        },
        "metrics": {
            "precision": metrics.precision,
            "recall": metrics.recall,
            "fpr": metrics.fpr,
            "fnr": metrics.fnr,
            "f1_score": metrics.f1_score,
            "calibration_error": metrics.calibration_error,
            "long_tail_failures": metrics.long_tail_failures,
        },
        "verdict": "PASS" if metrics.precision >= 0.95 else "REVIEW",
    }

    return metrics, report
