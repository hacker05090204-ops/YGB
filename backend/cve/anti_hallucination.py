"""
Anti-Hallucination Controls — Provenance Validation for CVE Pipeline

Rules:
  - No generative inference in canonical pipeline.
  - Every field requires provenance: source, fetched_at, parser_version, confidence.
  - unverifiable_claim_rate must be 0 for production promotion.
  - Audit log for every provenance check.
"""

import logging
import math
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Iterable
from dataclasses import dataclass, asdict, is_dataclass

logger = logging.getLogger("ygb.anti_hallucination")

REQUIRED_PROVENANCE_FIELDS = frozenset([
    "source", "fetched_at", "parser_version", "confidence",
])
REFUSAL_TEXT = "Insufficient verified evidence."
GROUNDING_DISCLAIMER = (
    "This response could not be fully verified against the retrieved evidence."
)
_CVE_ID_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_SPECULATION_PATTERNS = (
    (re.compile(r"\bmay\b", re.IGNORECASE), "may", 0.15),
    (re.compile(r"\bmight\b", re.IGNORECASE), "might", 0.15),
    (re.compile(r"\bcould\b", re.IGNORECASE), "could", 0.12),
    (re.compile(r"\bpossibly\b", re.IGNORECASE), "possibly", 0.15),
    (re.compile(r"\bpotentially\b", re.IGNORECASE), "potentially", 0.12),
    (re.compile(r"\blikely\b", re.IGNORECASE), "likely", 0.1),
    (re.compile(r"\bprobably\b", re.IGNORECASE), "probably", 0.1),
    (re.compile(r"\bappears to\b", re.IGNORECASE), "appears to", 0.15),
    (re.compile(r"\bseems to\b", re.IGNORECASE), "seems to", 0.15),
    (re.compile(r"\bsuggests?\b", re.IGNORECASE), "suggests", 0.08),
)


@dataclass
class ProvenanceCheckResult:
    """Result of a single provenance validation."""
    cve_id: str
    passed: bool
    missing_fields: List[str]
    confidence: float
    source: str
    detail: str


@dataclass
class AntiHallucinationStats:
    """Aggregate grounding metrics derived from real grounding checks."""

    total_checked: int = 0
    grounded: int = 0
    ungrounded: int = 0
    _confidence_sum: float = 0.0

    def record(self, grounded: bool, confidence: float) -> None:
        bounded_confidence = max(0.0, min(1.0, float(confidence)))
        self.total_checked += 1
        if grounded:
            self.grounded += 1
        else:
            self.ungrounded += 1
        self._confidence_sum += bounded_confidence

    @property
    def mean_confidence(self) -> float:
        if self.total_checked == 0:
            return 0.0
        return round(self._confidence_sum / self.total_checked, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checked": self.total_checked,
            "grounded": self.grounded,
            "ungrounded": self.ungrounded,
            "mean_confidence": self.mean_confidence,
        }


@dataclass(frozen=True)
class GroundingCheckResult:
    """Result of validating assistant output against a real evidence store."""

    grounded: bool
    confidence: float
    reason: str
    cve_mentions: tuple[str, ...]
    unsupported_cves: tuple[str, ...]
    speculation_flags: tuple[str, ...]
    refusal_required: bool
    final_text: str


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _extract_cve_mentions(text: str) -> List[str]:
    seen = set()
    mentions: List[str] = []
    for match in _CVE_ID_PATTERN.findall(str(text or "")):
        normalized = match.upper()
        if normalized in seen:
            continue
        seen.add(normalized)
        mentions.append(normalized)
    return mentions


def _coerce_evidence_texts(evidence_store: Any) -> List[str]:
    """Flatten real evidence structures into plain text values for grounding checks."""

    texts: List[str] = []

    def _walk(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                texts.append(stripped)
            return
        if isinstance(value, bytes):
            decoded = value.decode("utf-8", errors="replace").strip()
            if decoded:
                texts.append(decoded)
            return
        if isinstance(value, dict):
            for nested in value.values():
                _walk(nested)
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for nested in value:
                _walk(nested)
            return
        if is_dataclass(value):
            _walk(asdict(value))
            return
        if hasattr(value, "__dict__"):
            _walk(vars(value))

    _walk(evidence_store)
    return texts


def _split_sentences(text: str) -> List[str]:
    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")):
        cleaned = " ".join(sentence.split()).strip()
        if len(cleaned) >= 20:
            sentences.append(cleaned)
    return sentences


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_-]{3,}", _normalize_text(text))
        if not token.isdigit()
    }


def _sentence_supported(sentence: str, evidence_sentences: Iterable[str], evidence_blob: str) -> bool:
    normalized_sentence = _normalize_text(sentence)
    if normalized_sentence and normalized_sentence in evidence_blob:
        return True

    sentence_tokens = _tokenize(sentence)
    if not sentence_tokens:
        return False

    for evidence_sentence in evidence_sentences:
        evidence_tokens = _tokenize(evidence_sentence)
        if not evidence_tokens:
            continue
        overlap = len(sentence_tokens & evidence_tokens) / len(sentence_tokens)
        if overlap >= 0.75:
            return True
    return False


class GroundingValidator:
    """Validate assistant output against real retrieved evidence."""

    def __init__(self, stats: Optional[AntiHallucinationStats] = None):
        self._stats = stats or AntiHallucinationStats()

    def get_stats(self) -> Dict[str, Any]:
        return self._stats.to_dict()

    def validate(self, response_text: str, evidence_store: Any) -> GroundingCheckResult:
        text = str(response_text or "").strip()
        if not text:
            self._stats.record(False, 0.0)
            return GroundingCheckResult(
                grounded=False,
                confidence=0.0,
                reason="empty_response",
                cve_mentions=(),
                unsupported_cves=(),
                speculation_flags=(),
                refusal_required=True,
                final_text=REFUSAL_TEXT,
            )

        evidence_texts = _coerce_evidence_texts(evidence_store)
        if not evidence_texts:
            self._stats.record(False, 0.0)
            return GroundingCheckResult(
                grounded=False,
                confidence=0.0,
                reason="evidence_store_empty",
                cve_mentions=tuple(_extract_cve_mentions(text)),
                unsupported_cves=tuple(_extract_cve_mentions(text)),
                speculation_flags=(),
                refusal_required=True,
                final_text=REFUSAL_TEXT,
            )

        evidence_blob = _normalize_text("\n".join(evidence_texts))
        evidence_sentences = _split_sentences("\n".join(evidence_texts))
        response_sentences = _split_sentences(text)
        cve_mentions = _extract_cve_mentions(text)
        unsupported_cves = [
            cve for cve in cve_mentions if _normalize_text(cve) not in evidence_blob
        ]

        support_ratio = 1.0
        if response_sentences:
            supported_sentences = sum(
                1
                for sentence in response_sentences
                if _sentence_supported(sentence, evidence_sentences, evidence_blob)
            )
            support_ratio = supported_sentences / len(response_sentences)
        elif _normalize_text(text) not in evidence_blob:
            support_ratio = 0.0

        confidence = 0.4 + (0.6 * support_ratio)
        reasons: List[str] = []

        if support_ratio < 1.0:
            reasons.append(f"sentence_support={support_ratio:.2f}")

        speculation_flags: List[str] = []
        speculation_penalty = 0.0
        for pattern, label, penalty in _SPECULATION_PATTERNS:
            if pattern.search(text):
                speculation_flags.append(label)
                speculation_penalty += penalty
        if speculation_flags:
            confidence -= min(0.45, speculation_penalty)
            reasons.append(
                "speculation_markers=" + ",".join(speculation_flags)
            )

        if unsupported_cves:
            confidence = min(confidence, 0.2)
            reasons.append(
                "unsupported_cves=" + ",".join(unsupported_cves)
            )

        confidence = round(max(0.0, min(1.0, confidence)), 4)
        grounded = (
            not unsupported_cves
            and not speculation_flags
            and support_ratio >= 0.85
            and confidence >= 0.3
        )
        refusal_required = confidence < 0.3

        if grounded:
            final_text = text
            reason = "grounded_against_evidence_store"
        elif refusal_required:
            final_text = REFUSAL_TEXT
            reason = "; ".join(reasons) if reasons else "insufficient_grounding_confidence"
        else:
            final_text = f"{text.rstrip()} {GROUNDING_DISCLAIMER}".strip()
            reason = "; ".join(reasons) if reasons else "partial_grounding_only"

        self._stats.record(grounded, confidence)
        return GroundingCheckResult(
            grounded=grounded,
            confidence=confidence,
            reason=reason,
            cve_mentions=tuple(cve_mentions),
            unsupported_cves=tuple(unsupported_cves),
            speculation_flags=tuple(speculation_flags),
            refusal_required=refusal_required,
            final_text=final_text,
        )


class AntiHallucinationValidator:
    """Validates that all CVE data has proper provenance and no generative content."""

    def __init__(self):
        self._audit_log: List[Dict[str, Any]] = []
        self._total_checks: int = 0
        self._passed_checks: int = 0
        self._failed_checks: int = 0
        self._grounding_stats = AntiHallucinationStats()
        self._grounding_validator = GroundingValidator(self._grounding_stats)

    @staticmethod
    def _read_provenance_value(provenance: Dict[str, Any], field_name: str) -> Any:
        if hasattr(provenance, field_name):
            return getattr(provenance, field_name, None)
        return provenance.get(field_name)

    def validate_provenance(
        self,
        cve_id: str,
        provenance: Dict[str, Any],
    ) -> ProvenanceCheckResult:
        """Validate that a provenance record has all required fields.

        Required: source, fetched_at, parser_version, confidence
        """
        self._total_checks += 1

        missing = []
        for field_name in REQUIRED_PROVENANCE_FIELDS:
            val = self._read_provenance_value(provenance, field_name)
            if field_name == "confidence":
                try:
                    numeric_confidence = float(val)
                except (TypeError, ValueError):
                    missing.append(field_name)
                    continue
                if not math.isfinite(numeric_confidence) or numeric_confidence <= 0.0:
                    missing.append(field_name)
                continue
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(field_name)

        raw_confidence = self._read_provenance_value(provenance, "confidence")
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        source = self._read_provenance_value(provenance, "source") or ""

        passed = len(missing) == 0
        if passed:
            self._passed_checks += 1
            detail = "All provenance fields present"
        else:
            self._failed_checks += 1
            detail = f"Missing provenance fields: {missing}"

        result = ProvenanceCheckResult(
            cve_id=cve_id,
            passed=passed,
            missing_fields=missing,
            confidence=confidence,
            source=source,
            detail=detail,
        )

        self._audit_log.append({
            "cve_id": cve_id,
            "passed": passed,
            "missing_fields": missing,
            "confidence": confidence,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return result

    def validate_record_provenance(
        self,
        cve_id: str,
        provenance_list: List[Any],
    ) -> List[ProvenanceCheckResult]:
        """Validate all provenance entries for a CVE record."""
        results = []
        for prov in provenance_list:
            result = self.validate_provenance(cve_id, prov)
            results.append(result)
        return results

    def compute_unverifiable_claim_rate(self) -> float:
        """Compute the fraction of provenance checks that failed.

        Must be 0.0 for production promotion.
        """
        if self._total_checks == 0:
            return 0.0
        return round(self._failed_checks / self._total_checks, 4)

    def is_production_ready(self) -> tuple:
        """Check if provenance meets production requirements.

        Returns (ready, reason).
        """
        rate = self.compute_unverifiable_claim_rate()
        if rate > 0:
            return False, (
                f"unverifiable_claim_rate={rate} > 0. "
                f"Failed {self._failed_checks}/{self._total_checks} checks."
            )
        if self._total_checks == 0:
            return False, "No provenance checks performed yet."
        return True, (
            f"All {self._total_checks} provenance checks passed. "
            f"unverifiable_claim_rate=0.0"
        )

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def validate_response_grounding(
        self,
        response_text: str,
        evidence_store: Any,
    ) -> GroundingCheckResult:
        return self._grounding_validator.validate(response_text, evidence_store)

    def get_hallucination_stats(self) -> Dict[str, Any]:
        return self._grounding_validator.get_stats()

    def get_status(self) -> Dict[str, Any]:
        return {
            "total_checks": self._total_checks,
            "passed": self._passed_checks,
            "failed": self._failed_checks,
            "audit_entries": len(self._audit_log),
            "unverifiable_claim_rate": self.compute_unverifiable_claim_rate(),
            "production_ready": self.is_production_ready()[0],
            "hallucination_stats": self.get_hallucination_stats(),
        }


# =============================================================================
# SINGLETON
# =============================================================================

_validator: Optional[AntiHallucinationValidator] = None


def get_anti_hallucination_validator() -> AntiHallucinationValidator:
    global _validator
    if _validator is None:
        _validator = AntiHallucinationValidator()
    return _validator
