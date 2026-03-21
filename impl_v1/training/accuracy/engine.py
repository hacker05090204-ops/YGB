from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from impl_v1.phase49.governors.g23_reasoning_engine import (
    EvidenceType,
    create_evidence_item,
    create_evidence_pack,
    perform_reasoning,
)
from impl_v1.phase49.governors.g33_proof_verification import verify_bug_proof
from impl_v1.phase49.governors.g34_duplicate_intelligence import (
    ReportFingerprint,
    analyze_duplicates,
    create_report_fingerprint,
)
from impl_v1.training.distributed.impact_confidence_calibrator import (
    ImpactConfidenceCalibrator,
)


@dataclass
class AccuracyFinding:
    finding_id: str
    category: str
    title: str
    payload: Dict[str, Any]
    response: Dict[str, Any]
    verification: Dict[str, Any]
    fingerprint: str
    confidence: Dict[str, Any] = field(default_factory=dict)
    proof: Dict[str, Any] = field(default_factory=dict)
    duplicate: Dict[str, Any] = field(default_factory=dict)
    reasoning: Dict[str, Any] = field(default_factory=dict)
    retraining_signal: Dict[str, Any] = field(default_factory=dict)
    memory_tags: List[str] = field(default_factory=list)


@dataclass
class AccuracyEngineResult:
    predictions: List[Dict[str, Any]] = field(default_factory=list)
    classified: List[Dict[str, Any]] = field(default_factory=list)
    verified: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[AccuracyFinding] = field(default_factory=list)
    retraining_queue: List[Dict[str, Any]] = field(default_factory=list)
    duplicates: List[Dict[str, Any]] = field(default_factory=list)


class AccuracyEngine:
    """prediction -> classification -> verification -> deduplication."""

    def __init__(
        self,
        payload_executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        response_validator: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.payload_executor = payload_executor or self._default_execute
        self.response_validator = response_validator or self._default_validate
        self.confidence_engine = ImpactConfidenceCalibrator()

    def run(
        self,
        predictions: Iterable[Dict[str, Any]],
        known_report_fingerprints: Iterable[Tuple[str, ReportFingerprint]] = (),
    ) -> AccuracyEngineResult:
        result = AccuracyEngineResult(predictions=list(predictions))
        fingerprints = set()
        known_reports = list(known_report_fingerprints)
        for prediction in result.predictions:
            classified = self.classify(prediction)
            result.classified.append(classified)
            response = self.execute_payload(classified)
            verification = self.verify_response(classified, response)
            proof = self._run_proof_engine(classified, response, verification)
            confidence = self._run_confidence_engine(classified, verification, proof)
            report_fingerprint = self._create_report_fingerprint(classified, verification)
            duplicate = self._run_duplicate_engine(report_fingerprint, known_reports)
            reasoning = self._run_evidence_engine(classified, response, verification, confidence)
            retraining_signal = self._build_retraining_signal(classified, confidence, proof, duplicate)
            verified = {
                **classified,
                "response": response,
                "verification": verification,
                "proof": proof,
                "confidence": confidence,
                "duplicate": duplicate,
                "reasoning": reasoning,
                "retraining_signal": retraining_signal,
            }
            result.verified.append(verified)
            fingerprint = self.fingerprint_bug(verified)
            if duplicate.get("is_duplicate"):
                result.duplicates.append(
                    {
                        "finding_id": prediction.get("finding_id", ""),
                        "fingerprint": fingerprint,
                        "duplicate": duplicate,
                    }
                )
                continue
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            finding = AccuracyFinding(
                finding_id=prediction.get("finding_id") or f"finding_{len(result.findings)+1:04d}",
                category=classified.get("category", "generic"),
                title=classified.get("title", "Untitled finding"),
                payload=classified.get("payload", {}),
                response=response,
                verification=verification,
                fingerprint=fingerprint,
                confidence=confidence,
                proof=proof,
                duplicate=duplicate,
                reasoning=reasoning,
                retraining_signal=retraining_signal,
                memory_tags=[
                    classified.get("category", "generic"),
                    verification.get("verification_status", "UNKNOWN"),
                    confidence.get("severity", "INFO"),
                ],
            )
            result.findings.append(finding)
            result.retraining_queue.append(retraining_signal)
            known_reports.append((finding.finding_id, report_fingerprint))
        return result

    def classify(self, prediction: Dict[str, Any]) -> Dict[str, Any]:
        category = prediction.get("category") or prediction.get("type") or "generic"
        title = prediction.get("title") or prediction.get("description") or "Predicted issue"
        payload = prediction.get("payload") or {
            "method": prediction.get("method", "GET"),
            "url": prediction.get("url", ""),
            "body": prediction.get("body"),
            "headers": prediction.get("headers", {}),
        }
        return {**prediction, "category": category, "title": title, "payload": payload}

    def execute_payload(self, classified: Dict[str, Any]) -> Dict[str, Any]:
        return self.payload_executor(classified)

    def verify_response(self, classified: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        return self.response_validator(classified, response)

    def fingerprint_bug(self, finding: Dict[str, Any]) -> str:
        base = {
            "category": finding.get("category"),
            "title": finding.get("title"),
            "url": finding.get("payload", {}).get("url"),
            "method": finding.get("payload", {}).get("method"),
            "verification_status": finding.get("verification", {}).get("verification_status"),
        }
        return hashlib.sha256(json.dumps(base, sort_keys=True).encode("utf-8")).hexdigest()

    def _default_execute(self, classified: Dict[str, Any]) -> Dict[str, Any]:
        payload = classified.get("payload", {})
        return {
            "executed": True,
            "status_code": int(payload.get("expected_status", 200)),
            "body": payload.get("body"),
            "headers": payload.get("headers", {}),
        }

    def _default_validate(self, classified: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        expected = classified.get("expected_status")
        status_code = response.get("status_code")
        is_valid = expected is None or expected == status_code
        return {
            "verification_status": "VERIFIED" if is_valid else "LIKELY",
            "verification_score": 1.0 if is_valid else 0.6,
            "evidence_strength": "strong" if is_valid else "medium",
            "reason": "status match" if is_valid else f"expected {expected}, got {status_code}",
        }

    def _run_proof_engine(
        self,
        classified: Dict[str, Any],
        response: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> Dict[str, Any]:
        category = str(classified.get("category", "generic")).lower()
        payload = classified.get("payload", {})
        response_after = json.dumps(response, sort_keys=True)
        finding_data = {
            "input_vector": payload.get("url", ""),
            "parameter": payload.get("method", "GET"),
            "payload": json.dumps(payload, sort_keys=True),
            "response_before": json.dumps(classified.get("baseline_response", {}), sort_keys=True),
            "response_after": response_after,
            "unauthorized_access": category in {"idor", "auth_bypass"},
            "privilege_escalation": category in {"privilege_escalation", "idor"},
            "data_leak": category in {"data_leak", "idor"},
            "xss_stored": category == "xss",
            "rce": category == "rce",
        }
        proof = verify_bug_proof(
            finding_text=classified.get("title", "Predicted issue"),
            finding_data=finding_data,
        )
        return {
            "status": proof.status.value,
            "confidence": proof.confidence / 100.0,
            "impact": proof.impact.value,
            "reason": proof.reason,
            "rejection_reason": proof.rejection_reason.value,
            "determinism_hash": proof.determinism_hash,
            "evidence_hash": proof.evidence.evidence_hash if proof.evidence else "",
        }

    def _run_confidence_engine(
        self,
        classified: Dict[str, Any],
        verification: Dict[str, Any],
        proof: Dict[str, Any],
    ) -> Dict[str, Any]:
        category = str(classified.get("category", "generic")).lower()
        calibrated = self.confidence_engine.calibrate(
            raw_confidence=float(verification.get("verification_score", 0.0)),
            exploit_delta=float(proof.get("confidence", 0.0)),
            privilege_escalation=category in {"privilege_escalation", "idor"},
            data_exposure=category in {"data_leak", "idor"},
        )
        return {
            "raw_confidence": calibrated.raw_confidence,
            "calibrated_confidence": calibrated.calibrated_confidence,
            "severity": calibrated.severity,
            "cvss_estimate": calibrated.cvss_estimate,
            "reliable": calibrated.reliable,
        }

    def _create_report_fingerprint(
        self,
        classified: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> ReportFingerprint:
        payload = classified.get("payload", {})
        params = json.dumps(
            {
                "headers": payload.get("headers", {}),
                "body": payload.get("body"),
                "method": payload.get("method", "GET"),
            },
            sort_keys=True,
        )
        reproduction_steps = verification.get("reason", "verification recorded")
        cve_refs = tuple(classified.get("cve_refs", ()) or ())
        return create_report_fingerprint(
            endpoint=payload.get("url", ""),
            params=params,
            cve_refs=cve_refs,
            reproduction_steps=reproduction_steps,
        )

    def _run_duplicate_engine(
        self,
        current_fingerprint: ReportFingerprint,
        known_reports: List[Tuple[str, ReportFingerprint]],
    ) -> Dict[str, Any]:
        duplicate = analyze_duplicates(
            current_fingerprint=current_fingerprint,
            known_reports=tuple(known_reports),
        )
        return {
            "duplicate_probability": duplicate.duplicate_probability,
            "confidence": duplicate.confidence.value,
            "matching_factors": list(duplicate.matching_factors),
            "is_duplicate": duplicate.is_duplicate,
            "recommendation": duplicate.recommendation,
        }

    def _run_evidence_engine(
        self,
        classified: Dict[str, Any],
        response: Dict[str, Any],
        verification: Dict[str, Any],
        confidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = classified.get("payload", {})
        category = str(classified.get("category", "generic")).upper()
        evidence_pack = create_evidence_pack(
            browser_observation=create_evidence_item(
                EvidenceType.BROWSER_OBSERVATION,
                "accuracy-engine",
                json.dumps(response, sort_keys=True),
            ),
            scope_extraction=create_evidence_item(
                EvidenceType.SCOPE_EXTRACTION,
                "accuracy-engine",
                payload.get("url", ""),
            ),
            platform_metadata=create_evidence_item(
                EvidenceType.PLATFORM_METADATA,
                "accuracy-engine",
                category,
            ),
            cve_context=create_evidence_item(
                EvidenceType.CVE_CONTEXT,
                "accuracy-engine",
                f"{category} verification lineage",
            ),
            screen_evidence=create_evidence_item(
                EvidenceType.SCREEN_EVIDENCE,
                "accuracy-engine",
                verification.get("reason", "verification recorded"),
            ),
        )
        reasoning = perform_reasoning(
            evidence_pack=evidence_pack,
            target=payload.get("url", ""),
            bug_type=category,
            severity=confidence.get("severity", "INFO"),
            reproduction_steps=[
                f"Send {payload.get('method', 'GET')} request to {payload.get('url', '')}",
                verification.get("reason", "verify response delta"),
                f"Observe status {response.get('status_code', 'unknown')}",
            ],
        )
        return {
            "status": reasoning.status.value,
            "report_id": reasoning.report.report_id if reasoning.report else "",
            "evidence_pack_id": reasoning.evidence_pack.pack_id,
            "determinism_hash": reasoning.report.determinism_hash if reasoning.report else "",
            "voice_script_en": list(reasoning.voice_script_en.sections) if reasoning.voice_script_en else [],
        }

    def _build_retraining_signal(
        self,
        classified: Dict[str, Any],
        confidence: Dict[str, Any],
        proof: Dict[str, Any],
        duplicate: Dict[str, Any],
    ) -> Dict[str, Any]:
        label = 1 if proof.get("status") == "REAL" else 0
        priority = "high" if confidence.get("reliable") else "medium"
        if duplicate.get("is_duplicate"):
            priority = "low"
        return {
            "finding_id": classified.get("finding_id", ""),
            "label": label,
            "priority": priority,
            "category": classified.get("category", "generic"),
            "confidence": confidence.get("calibrated_confidence", 0.0),
            "reason": proof.get("reason", ""),
            "skip_retrain": duplicate.get("is_duplicate", False),
        }
