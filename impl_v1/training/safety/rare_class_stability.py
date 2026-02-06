"""
Rare Class Stability Enforcement
=================================

Per-class metrics tracking:
- Per-vulnerability-type recall
- Per-class FPR
- Class confidence calibration
- Edge-case robustness score

Auto-disable if any class drops below thresholds.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import datetime
from collections import defaultdict


# =============================================================================
# THRESHOLDS
# =============================================================================

@dataclass
class RareClassThresholds:
    """Thresholds for rare class stability."""
    min_recall: float = 0.90
    max_calibration_gap: float = 0.03
    min_sample_count: int = 10  # Minimum samples to evaluate


# =============================================================================
# PER-CLASS METRICS
# =============================================================================

@dataclass
class ClassMetrics:
    """Metrics for a single class."""
    class_name: str
    true_positives: int = 0
    false_negatives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    confidence_sum: float = 0.0
    confidence_count: int = 0
    correct_confidence_sum: float = 0.0
    correct_count: int = 0
    
    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0
    
    @property
    def fpr(self) -> float:
        total = self.false_positives + self.true_negatives
        return self.false_positives / total if total > 0 else 0.0
    
    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / self.confidence_count if self.confidence_count > 0 else 0.5
    
    @property
    def calibration_gap(self) -> float:
        if self.confidence_count == 0:
            return 0.0
        avg_conf = self.avg_confidence
        accuracy = self.correct_count / self.confidence_count
        return abs(avg_conf - accuracy)


# =============================================================================
# CLASS STABILITY MONITOR
# =============================================================================

class RareClassStabilityMonitor:
    """Monitor per-class stability metrics."""
    
    VULNERABILITY_TYPES = [
        "sqli", "xss", "ssrf", "xxe", "rce",
        "idor", "lfi", "rfi", "auth_bypass",
        "csrf", "command_injection", "path_traversal",
    ]
    
    def __init__(self, thresholds: RareClassThresholds = None):
        self.thresholds = thresholds or RareClassThresholds()
        self.class_metrics: Dict[str, ClassMetrics] = {
            vt: ClassMetrics(class_name=vt) for vt in self.VULNERABILITY_TYPES
        }
        self.auto_mode_disabled = False
        self.disable_reason = ""
    
    def record_prediction(
        self,
        class_name: str,
        ground_truth: bool,
        predicted: bool,
        confidence: float,
    ) -> None:
        """Record a prediction result."""
        if class_name not in self.class_metrics:
            self.class_metrics[class_name] = ClassMetrics(class_name=class_name)
        
        metrics = self.class_metrics[class_name]
        
        if ground_truth and predicted:
            metrics.true_positives += 1
        elif ground_truth and not predicted:
            metrics.false_negatives += 1
        elif not ground_truth and predicted:
            metrics.false_positives += 1
        else:
            metrics.true_negatives += 1
        
        metrics.confidence_sum += confidence
        metrics.confidence_count += 1
        
        if predicted == ground_truth:
            metrics.correct_confidence_sum += confidence
            metrics.correct_count += 1
    
    def check_stability(self) -> Tuple[bool, Dict[str, dict]]:
        """
        Check if all classes meet stability thresholds.
        
        Returns:
            Tuple of (is_stable, per_class_status)
        """
        results = {}
        all_stable = True
        violations = []
        
        for class_name, metrics in self.class_metrics.items():
            total_samples = (
                metrics.true_positives + metrics.false_negatives +
                metrics.false_positives + metrics.true_negatives
            )
            
            # Skip classes with insufficient data
            if total_samples < self.thresholds.min_sample_count:
                results[class_name] = {
                    "status": "insufficient_data",
                    "samples": total_samples,
                }
                continue
            
            recall_ok = metrics.recall >= self.thresholds.min_recall
            calibration_ok = metrics.calibration_gap <= self.thresholds.max_calibration_gap
            
            class_stable = recall_ok and calibration_ok
            
            results[class_name] = {
                "status": "ok" if class_stable else "VIOLATION",
                "recall": round(metrics.recall, 4),
                "fpr": round(metrics.fpr, 4),
                "calibration_gap": round(metrics.calibration_gap, 4),
                "recall_ok": recall_ok,
                "calibration_ok": calibration_ok,
            }
            
            if not class_stable:
                all_stable = False
                violations.append(class_name)
        
        if not all_stable:
            self.auto_mode_disabled = True
            self.disable_reason = f"Class violations: {', '.join(violations)}"
        
        return all_stable, results
    
    def should_disable_auto_mode(self) -> Tuple[bool, str]:
        """Check if auto-mode should be disabled."""
        _, _ = self.check_stability()
        return self.auto_mode_disabled, self.disable_reason
    
    def get_edge_case_robustness(self) -> Dict[str, float]:
        """Calculate edge-case robustness per class."""
        robustness = {}
        
        for class_name, metrics in self.class_metrics.items():
            # Robustness = recall on difficult samples
            if metrics.true_positives + metrics.false_negatives > 0:
                robustness[class_name] = metrics.recall
            else:
                robustness[class_name] = 1.0
        
        return robustness
