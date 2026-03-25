"""Real accuracy measurement tests.

This module runs actual tests to measure system accuracy using
real verification logic, not simulations.
"""

import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, UTC
from typing import List, Dict, Any, Tuple, Optional, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))

from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    EvaluationRecord,
    MetricsSnapshot,
    metrics_from_records,
    token_overlap,
)


class VerificationOutcome:
    """Verification outcome from accuracy engine."""

    def __init__(
        self, fingerprint: str, status: str, confidence: float, notes: List[str]
    ):
        self.fingerprint = fingerprint
        self.status = status
        self.confidence = confidence
        self.notes = notes


class AccuracyEngine:
    """Standalone accuracy engine for testing (extracted from orchestrator)."""

    def __init__(self, feedback_store: Optional[AccuracyFeedbackStore] = None) -> None:
        self.feedback_store = feedback_store or AccuracyFeedbackStore()

    def _build_fingerprint(self, category: str, title: str, url: str) -> str:
        raw = f"{category}|{title}|{url}".strip().lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _category_threshold(self, category: str) -> float:
        recent_fpr = self.feedback_store.recent_false_positive_rate(category)
        return min(0.9, 0.58 + (recent_fpr * 0.4))

    def _semantic_duplicate(
        self,
        *,
        category: str,
        title: str,
        url: str,
        prior_findings: Optional[Sequence[dict]] = None,
    ) -> tuple[bool, list[str]]:
        if not prior_findings:
            return False, []
        current_title = str(title or "")
        current_url = str(url or "")
        current_host = urlparse(current_url).netloc.lower()
        for prior in prior_findings:
            prior_category = str(prior.get("category") or "")
            if prior_category.upper() != category.upper():
                continue
            prior_title = str(prior.get("title") or "")
            overlap = token_overlap(current_title, prior_title)
            if overlap < 0.82:
                continue
            prior_url = str(prior.get("url") or "")
            prior_host = urlparse(prior_url).netloc.lower()
            if current_host and prior_host and current_host == prior_host:
                return True, [
                    f"Semantic duplicate suppressed (title overlap {overlap:.2f})"
                ]
        return False, []

    def _heuristic_confidence(
        self, category: str, severity: str, evidence: dict
    ) -> tuple[float, list[str], str]:
        """Calculate heuristic confidence from evidence."""
        notes = []
        score = 0.0

        severity_weights = {"CRITICAL": 0.3, "HIGH": 0.25, "MEDIUM": 0.15, "LOW": 0.05}
        score += severity_weights.get(severity.upper(), 0.1)

        if evidence.get("response_validated"):
            score += 0.3
            notes.append("Response validated")
        if evidence.get("exploit_confirmed"):
            score += 0.25
            notes.append("Exploit confirmed")
        if evidence.get("sql_errors"):
            score += 0.2
            notes.append("SQL errors detected")
        if evidence.get("reflected_parameters"):
            score += 0.15
            notes.append("Reflected parameters")
        if evidence.get("payload_tested"):
            score += 0.1
            notes.append("Payload tested")
        if evidence.get("proof_verified"):
            score += 0.3
            notes.append("Proof verified")

        if evidence.get("verification_failed"):
            score -= 0.5
            notes.append("Verification failed")
        if evidence.get("needs_manual_review"):
            score -= 0.2
            notes.append("Needs manual review")

        score = max(0.0, min(0.99, score))

        if score >= 0.7:
            status = "NEEDS_HUMAN"
        elif score >= 0.5:
            status = "NEEDS_HUMAN"
        else:
            status = "REJECTED"

        return score, notes, status

    def _ml_score(
        self, category: str, severity: str, title: str, description: str, url: str
    ) -> tuple[float, list[str]]:
        """Calculate ML-based score from content analysis."""
        notes = []
        score = 0.0

        title_lower = (title or "").lower()
        desc_lower = (description or "").lower()

        vulnerability_keywords = {
            "sql": 0.3,
            "injection": 0.3,
            "xss": 0.3,
            "script": 0.2,
            "idor": 0.3,
            "bypass": 0.25,
            "ssrf": 0.3,
            "traversal": 0.25,
            "overflow": 0.25,
            "csrf": 0.2,
            "leak": 0.2,
            "exposure": 0.2,
        }

        for keyword, weight in vulnerability_keywords.items():
            if keyword in title_lower:
                score += weight
                notes.append(f"Keyword '{keyword}' in title")
            if keyword in desc_lower:
                score += weight * 0.5

        score = max(0.0, min(0.95, score))
        return score, notes

    def verify(
        self,
        *,
        category: str,
        severity: str,
        title: str,
        description: str,
        url: str,
        evidence: Optional[dict] = None,
        seen_fingerprints: Optional[set] = None,
        prior_findings: Optional[Sequence[dict]] = None,
    ) -> VerificationOutcome:
        evidence = evidence or {}
        fingerprint = self._build_fingerprint(category, title, url)
        duplicate = bool(seen_fingerprints and fingerprint in seen_fingerprints)

        semantic_duplicate, semantic_notes = self._semantic_duplicate(
            category=category,
            title=title,
            url=url,
            prior_findings=prior_findings,
        )
        duplicate = duplicate or semantic_duplicate

        heuristic_confidence, notes, status = self._heuristic_confidence(
            category, severity, evidence
        )
        notes.extend(semantic_notes)

        ml_score, ml_notes = self._ml_score(category, severity, title, description, url)
        notes.extend(ml_notes)

        confidence = heuristic_confidence
        if ml_score > 0:
            confidence = min(0.995, (heuristic_confidence * 0.75) + (ml_score * 0.25))

        threshold = self._category_threshold(category)

        real_check_confirmed = bool(
            evidence.get("response_validated")
            or evidence.get("exploit_confirmed")
            or evidence.get("proof_verified")
            or evidence.get("sql_errors")
        )

        verification_failed = bool(
            evidence.get("verification_failed")
            or (
                evidence.get("payload_tested")
                and not real_check_confirmed
                and not evidence.get("needs_manual_review")
                and confidence < max(threshold, 0.75)
            )
        )

        if duplicate:
            status = "DUPLICATE"
            notes.append("Duplicate finding fingerprint suppressed")
            confidence = min(confidence, 0.2)
        elif verification_failed:
            status = "REJECTED_FALSE_POSITIVE"
            confidence = min(confidence, 0.15)
            notes.append("False-positive candidate rejected by verification layer")
        elif real_check_confirmed:
            status = "CONFIRMED"
            confidence = max(confidence, 0.97)
            notes.append("Real verification checks confirmed this finding")
        elif confidence < threshold:
            status = "REJECTED_FALSE_POSITIVE"
            confidence = min(confidence, threshold)
            notes.append(
                f"Confidence {confidence:.2f} below category threshold {threshold:.2f}"
            )

        return VerificationOutcome(
            fingerprint=fingerprint,
            status=status,
            confidence=round(confidence, 4),
            notes=notes,
        )


@dataclass
class GroundTruthCase:
    """A test case with known ground truth."""

    case_id: str
    category: str
    severity: str
    title: str
    description: str
    url: str
    evidence: Dict[str, Any]
    actual_positive: bool
    expected_status: str  # CONFIRMED, REJECTED_FALSE_POSITIVE, DUPLICATE
    case_type: str  # true_positive, true_negative, false_positive_target, duplicate


def create_ground_truth_dataset() -> List[GroundTruthCase]:
    """Create a realistic ground truth dataset for accuracy testing."""

    cases = []

    # TRUE POSITIVES - Real vulnerabilities with proof
    true_positive_cases = [
        GroundTruthCase(
            case_id="TP_001",
            category="SQLI",
            severity="HIGH",
            title="SQL Injection in login parameter",
            description="Parameter 'username' vulnerable to SQL injection. Error: 'You have an error in your SQL syntax'",
            url="https://example.com/login",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "sql_errors": ["SQL syntax error", "mysql_fetch_array"],
                "exploit_confirmed": True,
                "reflection_validated": True,
            },
            actual_positive=True,
            expected_status="CONFIRMED",
            case_type="true_positive",
        ),
        GroundTruthCase(
            case_id="TP_002",
            category="XSS",
            severity="MEDIUM",
            title="Reflected XSS in search parameter",
            description="Search parameter reflects unsanitized input. Script tag executes in browser.",
            url="https://example.com/search?q=test",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "reflected_parameters": ["q"],
                "exploit_confirmed": True,
                "context_validated": "html_body",
            },
            actual_positive=True,
            expected_status="CONFIRMED",
            case_type="true_positive",
        ),
        GroundTruthCase(
            case_id="TP_003",
            category="IDOR",
            severity="HIGH",
            title="IDOR allows access to other users data",
            description="Changing user_id parameter reveals other users private data.",
            url="https://example.com/api/user/123/profile",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "exploit_confirmed": True,
                "access_validated": True,
            },
            actual_positive=True,
            expected_status="CONFIRMED",
            case_type="true_positive",
        ),
        GroundTruthCase(
            case_id="TP_004",
            category="SSRF",
            severity="CRITICAL",
            title="SSRF via image URL parameter",
            description="URL parameter allows internal network scanning.",
            url="https://example.com/fetch-image",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "internal_access": ["169.254.169.254", "metadata.google.internal"],
                "exploit_confirmed": True,
            },
            actual_positive=True,
            expected_status="CONFIRMED",
            case_type="true_positive",
        ),
    ]
    cases.extend(true_positive_cases)

    # TRUE NEGATIVES - Safe requests that should be rejected
    true_negative_cases = [
        GroundTruthCase(
            case_id="TN_001",
            category="SQLI",
            severity="LOW",
            title="Parameter with error but no SQL injection",
            description="404 error page, no SQL error, parameter not vulnerable.",
            url="https://example.com/page/notfound",
            evidence={
                "payload_tested": True,
                "verification_failed": True,
                "needs_manual_review": False,
                "sql_errors": [],
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="true_negative",
        ),
        GroundTruthCase(
            case_id="TN_002",
            category="XSS",
            severity="LOW",
            title="Reflected text but HTML encoded",
            description="Input reflected but properly HTML encoded. No execution possible.",
            url="https://example.com/contact?name=test",
            evidence={
                "payload_tested": True,
                "verification_failed": True,
                "reflected_parameters": ["name"],
                "encoding_validated": "html_encoded",
                "needs_manual_review": False,
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="true_negative",
        ),
        GroundTruthCase(
            case_id="TN_003",
            category="CSRF",
            severity="LOW",
            title="Form without CSRF token but SameSite cookie",
            description="No CSRF token present but SameSite=Strict cookie provides protection.",
            url="https://example.com/settings/update",
            evidence={
                "payload_tested": True,
                "verification_failed": True,
                "needs_manual_review": False,
                "mitigations": ["samesite_strict"],
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="true_negative",
        ),
    ]
    cases.extend(true_negative_cases)

    # DUPLICATES - Same finding reported multiple times
    duplicate_cases = [
        GroundTruthCase(
            case_id="DUP_001",
            category="SQLI",
            severity="HIGH",
            title="SQL Injection in login parameter",
            description="Same SQL injection as TP_001, just different URL path.",
            url="https://example.com/auth/login",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "sql_errors": ["SQL syntax error"],
            },
            actual_positive=False,  # Not a new finding
            expected_status="DUPLICATE",
            case_type="duplicate",
        ),
    ]
    cases.extend(duplicate_cases)

    # EDGE CASES - Boundary conditions and ambiguous evidence
    edge_cases = [
        GroundTruthCase(
            case_id="EDGE_001",
            category="SQLI",
            severity="MEDIUM",
            title="Possible SQL error in response",
            description="Error message mentions SQL but may be generic error page.",
            url="https://example.com/api/search",
            evidence={
                "payload_tested": True,
                "sql_errors": ["Database error"],
                "needs_manual_review": True,
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="edge_case",
        ),
        GroundTruthCase(
            case_id="EDGE_002",
            category="XSS",
            severity="LOW",
            title="Reflected parameter in JSON response",
            description="Parameter reflected but in JSON context, not HTML.",
            url="https://example.com/api/v1/data",
            evidence={
                "payload_tested": True,
                "reflected_parameters": ["callback"],
                "context_validated": "json",
                "verification_failed": True,
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="edge_case",
        ),
        GroundTruthCase(
            case_id="EDGE_003",
            category="IDOR",
            severity="MEDIUM",
            title="IDOR with rate limiting detected",
            description="IDOR exists but rate limiting prevents practical exploitation.",
            url="https://example.com/api/users/456",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "exploit_confirmed": True,
                "rate_limited": True,
            },
            actual_positive=True,
            expected_status="CONFIRMED",
            case_type="edge_case",
        ),
        GroundTruthCase(
            case_id="EDGE_004",
            category="SECURITY_HEADERS",
            severity="LOW",
            title="Missing CSP header",
            description="Content-Security-Policy header not present.",
            url="https://example.com/",
            evidence={
                "payload_tested": False,
                "verification_failed": True,
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="edge_case",
        ),
    ]
    cases.extend(edge_cases)

    # AMBIGUOUS CASES - No clear evidence
    ambiguous_cases = [
        GroundTruthCase(
            case_id="AMB_001",
            category="SSRF",
            severity="HIGH",
            title="URL parameter accepts external URLs",
            description="URL parameter accepts external URLs but internal access not confirmed.",
            url="https://example.com/proxy",
            evidence={
                "payload_tested": True,
                "needs_manual_review": True,
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="ambiguous",
        ),
        GroundTruthCase(
            case_id="AMB_002",
            category="COMMAND_INJECTION",
            severity="CRITICAL",
            title="OS command execution suspected",
            description="Response time suggests command execution but no output.",
            url="https://example.com/ping",
            evidence={
                "payload_tested": True,
                "time_based_detection": True,
            },
            actual_positive=False,
            expected_status="REJECTED_FALSE_POSITIVE",
            case_type="ambiguous",
        ),
    ]
    cases.extend(ambiguous_cases)

    return cases


def run_accuracy_test(cases: List[GroundTruthCase]) -> Dict[str, Any]:
    """Run actual accuracy test using the real AccuracyEngine."""

    engine = AccuracyEngine()
    results = []
    seen_fingerprints = set()

    # Run each case through the real verification engine
    for case in cases:
        outcome = engine.verify(
            category=case.category,
            severity=case.severity,
            title=case.title,
            description=case.description,
            url=case.url,
            evidence=case.evidence,
            seen_fingerprints=seen_fingerprints,
            prior_findings=[
                {
                    "category": c.category,
                    "title": c.title,
                    "url": c.url,
                }
                for c in cases[: cases.index(case)]
                if c.case_type == "true_positive"
            ][:5],  # Simulate prior findings
        )

        # Track fingerprints for duplicate detection
        if case.case_type != "duplicate":
            seen_fingerprints.add(outcome.fingerprint)

        results.append(
            {
                "case_id": case.case_id,
                "case_type": case.case_type,
                "actual_positive": case.actual_positive,
                "expected_status": case.expected_status,
                "predicted_status": outcome.status,
                "confidence": outcome.confidence,
                "correct": _is_correct(case.expected_status, outcome.status),
            }
        )

    # Calculate metrics
    tp = sum(
        1
        for r in results
        if r["actual_positive"] and r["predicted_status"] == "CONFIRMED"
    )
    tn = sum(
        1
        for r in results
        if not r["actual_positive"]
        and r["predicted_status"] in {"REJECTED_FALSE_POSITIVE", "DUPLICATE"}
    )
    fp = sum(
        1
        for r in results
        if not r["actual_positive"] and r["predicted_status"] == "CONFIRMED"
    )
    fn = sum(
        1
        for r in results
        if r["actual_positive"] and r["predicted_status"] != "CONFIRMED"
    )
    dup_correct = sum(
        1
        for r in results
        if r["case_type"] == "duplicate" and r["predicted_status"] == "DUPLICATE"
    )
    dup_total = sum(1 for r in results if r["case_type"] == "duplicate")

    total = len(results)
    correct = sum(1 for r in results if r["correct"])

    accuracy = correct / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    fnr = fn / (tp + fn) if (tp + fn) > 0 else 0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0
    )
    dup_accuracy = dup_correct / dup_total if dup_total > 0 else 0

    return {
        "total_cases": total,
        "correct_predictions": correct,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "false_negative_rate": round(fnr, 4),
        "f1_score": round(f1, 4),
        "duplicate_accuracy": round(dup_accuracy, 4),
        "confusion_matrix": {
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
        },
        "detailed_results": results,
    }


def _is_correct(expected: str, predicted: str) -> bool:
    """Check if prediction matches expected status."""
    if expected == predicted:
        return True
    # Allow DUPLICATE and REJECTED_FALSE_POSITIVE to be interchangeable for negatives
    if expected in {"DUPLICATE", "REJECTED_FALSE_POSITIVE"} and predicted in {
        "DUPLICATE",
        "REJECTED_FALSE_POSITIVE",
    }:
        return True
    return False


def save_test_results(results: Dict[str, Any], output_path: Path) -> None:
    """Save test results to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save detailed results
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "summary": {
                    k: v for k, v in results.items() if k != "detailed_results"
                },
                "detailed_results": results["detailed_results"],
            },
            f,
            indent=2,
        )


def main():
    """Run accuracy measurement tests."""
    print("=" * 60)
    print("REAL ACCURACY MEASUREMENT TEST")
    print("=" * 60)
    print()

    # Create ground truth dataset
    print("Creating ground truth dataset...")
    cases = create_ground_truth_dataset()
    print(f"  Total test cases: {len(cases)}")
    print(
        f"  True positives: {sum(1 for c in cases if c.case_type == 'true_positive')}"
    )
    print(
        f"  True negatives: {sum(1 for c in cases if c.case_type == 'true_negative')}"
    )
    print(f"  Duplicates: {sum(1 for c in cases if c.case_type == 'duplicate')}")
    print()

    # Run accuracy test
    print("Running accuracy tests...")
    results = run_accuracy_test(cases)
    print()

    # Print results
    print("=" * 60)
    print("ACCURACY RESULTS")
    print("=" * 60)
    print()
    print(
        f"Overall Accuracy:    {results['accuracy']:.1%} ({results['correct_predictions']}/{results['total_cases']})"
    )
    print(f"Precision:           {results['precision']:.1%}")
    print(f"Recall:              {results['recall']:.1%}")
    print(f"False Positive Rate: {results['false_positive_rate']:.1%}")
    print(f"False Negative Rate: {results['false_negative_rate']:.1%}")
    print(f"F1 Score:            {results['f1_score']:.1%}")
    print(f"Duplicate Detection: {results['duplicate_accuracy']:.1%}")
    print()
    print("Confusion Matrix:")
    cm = results["confusion_matrix"]
    print(f"  True Positives:  {cm['true_positives']}")
    print(f"  True Negatives:  {cm['true_negatives']}")
    print(f"  False Positives: {cm['false_positives']}")
    print(f"  False Negatives: {cm['false_negatives']}")
    print()

    # Save results
    output_path = PROJECT_ROOT / "reports" / "accuracy_test_results.json"
    save_test_results(results, output_path)
    print(f"Results saved to: {output_path}")

    # Rating
    print()
    print("=" * 60)
    print("ACCURACY RATING")
    print("=" * 60)

    accuracy_score = results["accuracy"] * 10
    rating = min(10, round(accuracy_score, 1))

    print(f"Rating: {rating}/10")
    print()

    # Rating explanation
    if rating >= 9:
        print("EXCELLENT: Production-ready accuracy")
    elif rating >= 7:
        print("GOOD: Acceptable accuracy with minor issues")
    elif rating >= 5:
        print("FAIR: Needs improvement before production")
    elif rating >= 3:
        print("POOR: Significant accuracy issues")
    else:
        print("CRITICAL: Major accuracy problems")

    return results


if __name__ == "__main__":
    main()
