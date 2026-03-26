"""Autonomous data-quality pipeline for verified learning.

This pipeline collects candidate findings, filters low-quality or duplicated
entries, validates evidence strength, and stores routed outcomes for later
training or review.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


@dataclass(slots=True)
class DataQualityAssessment:
    """Quality decision for a single candidate finding."""

    assessment_id: str
    accepted: bool
    score: float
    destination: str
    reasons: list[str] = field(default_factory=list)
    evidence_strength: float = 0.0
    duplicate_risk: float = 0.0
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 4)
        payload["evidence_strength"] = round(self.evidence_strength, 4)
        payload["duplicate_risk"] = round(self.duplicate_risk, 4)
        return payload


class AutonomousDataPipeline:
    """Collect -> filter -> validate -> store pipeline for runtime findings."""

    NOISE_CATEGORIES = frozenset({"HEADERS", "COOKIE", "SSL"})

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        base = root_dir or (Path(__file__).resolve().parents[3] / "reports")
        self.root_dir = base
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_path = self.root_dir / "quarantine_findings.jsonl"
        self.duplicates_path = self.root_dir / "duplicate_findings.jsonl"
        self.rejected_path = self.root_dir / "rejected_findings.jsonl"
        self.learning_path = self.root_dir / "active_learning_queue.jsonl"
        self.validated_path = self.root_dir / "validated_pipeline.jsonl"

    def assess_candidate(
        self,
        *,
        category: str,
        severity: str,
        title: str,
        description: str,
        url: str,
        evidence: Optional[dict[str, Any]] = None,
        verification_status: str = "UNVERIFIED",
        duplicate: bool = False,
        confidence: float = 0.0,
    ) -> DataQualityAssessment:
        evidence = dict(evidence or {})
        reasons: list[str] = []
        score = 0.35
        evidence_strength = 0.0
        duplicate_risk = 1.0 if duplicate else 0.0

        if len(title.strip()) >= 12:
            score += 0.1
        else:
            reasons.append("Title too short for high-confidence learning")

        if len(description.strip()) >= 40:
            score += 0.1
        else:
            reasons.append("Description too short for strong evidence")

        if url.strip():
            score += 0.05
        else:
            reasons.append("Missing canonical URL")

        if evidence.get("payload_tested"):
            evidence_strength += 0.15
        if evidence.get("response_validated"):
            evidence_strength += 0.3
        if evidence.get("exploit_confirmed"):
            evidence_strength += 0.3
        if evidence.get("proof_verified"):
            evidence_strength += 0.3
        if evidence.get("time_based_confirmed"):
            evidence_strength += 0.2
        if evidence.get("oob_confirmed"):
            evidence_strength += 0.25
        if evidence.get("sql_errors"):
            evidence_strength += 0.15
        if evidence.get("verification_failed"):
            evidence_strength -= 0.3
            reasons.append("Verification failure lowers data quality")
        if evidence.get("needs_manual_review"):
            evidence_strength -= 0.1
            reasons.append("Manual review still required")

        score += evidence_strength
        score += min(max(confidence, 0.0), 1.0) * 0.15

        if (
            category.upper() in self.NOISE_CATEGORIES
            and verification_status != "CONFIRMED"
        ):
            score -= 0.15
            reasons.append("Low-signal configuration finding without confirmation")

        if duplicate:
            reasons.append("Duplicate routed away from execution and training")
        if verification_status == "REJECTED_FALSE_POSITIVE":
            reasons.append("Rejected by verification engine")

        score = max(0.0, min(score, 1.0))
        accepted = score >= 0.45 and not duplicate

        if duplicate:
            destination = "duplicates"
        elif verification_status == "CONFIRMED":
            destination = "validated"
        elif verification_status == "REJECTED_FALSE_POSITIVE":
            destination = "rejected"
        elif accepted:
            destination = "quarantine"
            reasons.append("Candidate kept for active learning review")
        else:
            destination = "rejected"
            reasons.append("Candidate rejected as low quality")

        return DataQualityAssessment(
            assessment_id=f"DQA-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            accepted=accepted,
            score=score,
            destination=destination,
            reasons=reasons,
            evidence_strength=max(0.0, min(evidence_strength, 1.0)),
            duplicate_risk=duplicate_risk,
        )

    def record_candidate(
        self,
        *,
        category: str,
        severity: str,
        title: str,
        description: str,
        url: str,
        evidence: Optional[dict[str, Any]] = None,
        verification_status: str,
        duplicate: bool,
        confidence: float,
        metadata: Optional[dict[str, Any]] = None,
    ) -> DataQualityAssessment:
        assessment = self.assess_candidate(
            category=category,
            severity=severity,
            title=title,
            description=description,
            url=url,
            evidence=evidence,
            verification_status=verification_status,
            duplicate=duplicate,
            confidence=confidence,
        )
        destination_path = {
            "duplicates": self.duplicates_path,
            "rejected": self.rejected_path,
            "quarantine": self.quarantine_path,
            "validated": self.validated_path,
        }.get(assessment.destination, self.quarantine_path)
        payload = {
            "category": category,
            "severity": severity,
            "title": title,
            "description": description,
            "url": url,
            "verification_status": verification_status,
            "duplicate": duplicate,
            "confidence": round(confidence, 4),
            "evidence": evidence or {},
            "metadata": metadata or {},
            "assessment": assessment.to_dict(),
        }
        with destination_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return assessment

    def push_learning_candidate(
        self,
        *,
        candidate_type: str,
        payload: dict[str, Any],
    ) -> None:
        envelope = {
            "candidate_type": candidate_type,
            "payload": payload,
            "created_at": _now_iso(),
        }
        with self.learning_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, ensure_ascii=True) + "\n")

    def summary(self) -> dict[str, Any]:
        return {
            "quarantine": _line_count(self.quarantine_path),
            "duplicates": _line_count(self.duplicates_path),
            "rejected": _line_count(self.rejected_path),
            "validated": _line_count(self.validated_path),
            "learning_candidates": _line_count(self.learning_path),
        }
