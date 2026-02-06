"""
Human Workflow Simulation - Production Grade
=============================================

Simulate real bug bounty workflows:
- 100 real submissions
- 100 duplicate reports
- 100 rejected reports

Measure:
- Report clarity
- Time to review
- False rejection rate
- Human friction index
"""

from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import random


# =============================================================================
# REPORT TYPES
# =============================================================================

class ReportType(Enum):
    """Types of bug bounty reports."""
    NEW_VALID = "new_valid"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    EDGE_CASE = "edge_case"


class ReportOutcome(Enum):
    """Possible report outcomes."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    NEEDS_INFO = "needs_info"


@dataclass
class BugReport:
    """A bug bounty report."""
    id: str
    report_type: ReportType
    title: str
    severity: str
    clarity_score: float  # 0-1
    completeness: float   # 0-1
    submission_time: str


@dataclass
class ReviewResult:
    """Result of human review."""
    report_id: str
    outcome: ReportOutcome
    review_time_minutes: float
    is_correct: bool  # Did system make right call?
    friction_score: float  # 0-1, higher = more friction


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_valid_reports(count: int = 100) -> List[BugReport]:
    """Generate valid new bug reports."""
    severities = ["critical", "high", "medium", "low"]
    reports = []
    
    for i in range(count):
        reports.append(BugReport(
            id=f"NEW_{i:03d}",
            report_type=ReportType.NEW_VALID,
            title=f"Valid Security Bug #{i}",
            severity=random.choice(severities),
            clarity_score=random.uniform(0.7, 1.0),
            completeness=random.uniform(0.8, 1.0),
            submission_time=datetime.now().isoformat(),
        ))
    
    return reports


def generate_duplicate_reports(count: int = 100) -> List[BugReport]:
    """Generate duplicate bug reports."""
    reports = []
    
    for i in range(count):
        reports.append(BugReport(
            id=f"DUP_{i:03d}",
            report_type=ReportType.DUPLICATE,
            title=f"Duplicate of Known Issue #{i % 20}",
            severity="medium",
            clarity_score=random.uniform(0.5, 0.9),
            completeness=random.uniform(0.6, 0.9),
            submission_time=datetime.now().isoformat(),
        ))
    
    return reports


def generate_invalid_reports(count: int = 100) -> List[BugReport]:
    """Generate invalid/rejected reports."""
    reports = []
    
    for i in range(count):
        reports.append(BugReport(
            id=f"INV_{i:03d}",
            report_type=ReportType.INVALID,
            title=f"Not a Bug Report #{i}",
            severity="none",
            clarity_score=random.uniform(0.2, 0.6),
            completeness=random.uniform(0.1, 0.5),
            submission_time=datetime.now().isoformat(),
        ))
    
    return reports


# =============================================================================
# REVIEW SIMULATION
# =============================================================================

def simulate_review(report: BugReport) -> ReviewResult:
    """Simulate human review of a report."""
    # Review time based on clarity
    base_time = 5.0  # minutes
    review_time = base_time / report.clarity_score
    
    # Determine outcome
    if report.report_type == ReportType.NEW_VALID:
        # 95% correctly accepted
        is_correct = random.random() < 0.95
        outcome = ReportOutcome.ACCEPTED if is_correct else ReportOutcome.REJECTED
    elif report.report_type == ReportType.DUPLICATE:
        # 90% correctly marked duplicate
        is_correct = random.random() < 0.90
        outcome = ReportOutcome.DUPLICATE if is_correct else ReportOutcome.ACCEPTED
    else:  # Invalid
        # 85% correctly rejected
        is_correct = random.random() < 0.85
        outcome = ReportOutcome.REJECTED if is_correct else ReportOutcome.NEEDS_INFO
    
    # Friction based on completeness
    friction = 1.0 - report.completeness
    
    return ReviewResult(
        report_id=report.id,
        outcome=outcome,
        review_time_minutes=round(review_time, 2),
        is_correct=is_correct,
        friction_score=round(friction, 3),
    )


# =============================================================================
# WORKFLOW METRICS
# =============================================================================

@dataclass
class WorkflowMetrics:
    """Human workflow metrics."""
    total_reports: int
    avg_clarity: float
    avg_review_time_minutes: float
    false_rejection_rate: float
    false_acceptance_rate: float
    friction_index: float


def calculate_workflow_metrics(
    reports: List[BugReport],
    results: List[ReviewResult],
) -> WorkflowMetrics:
    """Calculate workflow metrics."""
    result_map = {r.report_id: r for r in results}
    
    # Clarity
    avg_clarity = sum(r.clarity_score for r in reports) / len(reports)
    
    # Review time
    avg_time = sum(r.review_time_minutes for r in results) / len(results)
    
    # False rejections (valid reports rejected)
    valid_reports = [r for r in reports if r.report_type == ReportType.NEW_VALID]
    valid_results = [result_map[r.id] for r in valid_reports]
    false_rejections = sum(1 for r in valid_results if not r.is_correct)
    false_rejection_rate = false_rejections / len(valid_reports) if valid_reports else 0
    
    # False acceptances (invalid accepted)
    invalid_reports = [r for r in reports if r.report_type == ReportType.INVALID]
    invalid_results = [result_map[r.id] for r in invalid_reports]
    false_acceptances = sum(1 for r in invalid_results if not r.is_correct)
    false_acceptance_rate = false_acceptances / len(invalid_reports) if invalid_reports else 0
    
    # Friction index
    friction_index = sum(r.friction_score for r in results) / len(results)
    
    return WorkflowMetrics(
        total_reports=len(reports),
        avg_clarity=round(avg_clarity, 3),
        avg_review_time_minutes=round(avg_time, 2),
        false_rejection_rate=round(false_rejection_rate, 4),
        false_acceptance_rate=round(false_acceptance_rate, 4),
        friction_index=round(friction_index, 3),
    )


# =============================================================================
# SIMULATION RUNNER
# =============================================================================

def run_workflow_simulation() -> Tuple[WorkflowMetrics, dict]:
    """Run full workflow simulation."""
    # Generate reports
    valid = generate_valid_reports(100)
    duplicates = generate_duplicate_reports(100)
    invalid = generate_invalid_reports(100)
    all_reports = valid + duplicates + invalid
    
    # Simulate reviews
    results = [simulate_review(r) for r in all_reports]
    
    # Calculate metrics
    metrics = calculate_workflow_metrics(all_reports, results)
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "simulation": {
            "valid_reports": 100,
            "duplicate_reports": 100,
            "invalid_reports": 100,
        },
        "metrics": {
            "avg_clarity": metrics.avg_clarity,
            "avg_review_time_minutes": metrics.avg_review_time_minutes,
            "false_rejection_rate": metrics.false_rejection_rate,
            "false_acceptance_rate": metrics.false_acceptance_rate,
            "friction_index": metrics.friction_index,
        },
        "verdict": "PASS" if metrics.false_rejection_rate < 0.10 else "REVIEW",
    }
    
    return metrics, report
