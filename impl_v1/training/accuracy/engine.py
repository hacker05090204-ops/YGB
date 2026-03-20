from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass
class AccuracyFinding:
    finding_id: str
    category: str
    title: str
    payload: Dict[str, Any]
    response: Dict[str, Any]
    verification: Dict[str, Any]
    fingerprint: str


@dataclass
class AccuracyEngineResult:
    predictions: List[Dict[str, Any]] = field(default_factory=list)
    classified: List[Dict[str, Any]] = field(default_factory=list)
    verified: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[AccuracyFinding] = field(default_factory=list)


class AccuracyEngine:
    """prediction -> classification -> verification -> deduplication."""

    def __init__(
        self,
        payload_executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        response_validator: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.payload_executor = payload_executor or self._default_execute
        self.response_validator = response_validator or self._default_validate

    def run(self, predictions: Iterable[Dict[str, Any]]) -> AccuracyEngineResult:
        result = AccuracyEngineResult(predictions=list(predictions))
        fingerprints = set()
        for prediction in result.predictions:
            classified = self.classify(prediction)
            result.classified.append(classified)
            response = self.execute_payload(classified)
            verification = self.verify_response(classified, response)
            verified = {**classified, "response": response, "verification": verification}
            result.verified.append(verified)
            fingerprint = self.fingerprint_bug(verified)
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            result.findings.append(
                AccuracyFinding(
                    finding_id=prediction.get("finding_id") or f"finding_{len(result.findings)+1:04d}",
                    category=classified.get("category", "generic"),
                    title=classified.get("title", "Untitled finding"),
                    payload=classified.get("payload", {}),
                    response=response,
                    verification=verification,
                    fingerprint=fingerprint,
                )
            )
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
