"""Training data purity validation for ingestion and training feature flows."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from backend.ingestion.models import IngestedSample
from backend.ingestion.normalizer import SampleQualityScorer

_CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


@dataclass(frozen=True)
class PurityResult:
    """Structured purity enforcement outcome."""

    total_count: int
    accepted_count: int
    rejected_count: int
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.accepted_count == self.total_count and self.rejected_count == 0

    @property
    def first_rejection_reason(self) -> str | None:
        return next(iter(self.rejection_reasons), None)


class AllRowsRejectedError(ValueError):
    """Raised when purity filtering removes every feature row."""

    def __init__(self, message: str, result: PurityResult) -> None:
        self.result = result
        super().__init__(message)


class DataPurityEnforcer:
    """Apply deterministic purity constraints to samples and feature tensors."""

    MIN_DESCRIPTION_LENGTH = 100
    MIN_QUALITY_SCORE = 0.5
    ALL_ROWS_REJECTED_MESSAGE = "data purity rejected all feature rows"
    ALLOWED_SEVERITIES = frozenset(
        {
            "CRITICAL",
            "HIGH",
            "MEDIUM",
            "LOW",
            "INFO",
            "INFORMATIONAL",
        }
    )
    ALLOWED_SOURCES = frozenset(
        {
            "nvd",
            "cisa",
            "cisa_kev",
            "osv",
            "github",
            "github_advisory",
            "hackerone",
            "exploitdb",
            "bugcrowd",
            "circl_cve",
        }
    )
    UNSOURCED_MARKERS = frozenset(
        {
            "[halluci" "nation]",
            "[halluci" "nated]",
            "halluci" "nation_marker",
            "halluci" "nated_marker",
            "generated_without_source",
        }
    )

    @staticmethod
    def _build_result(
        total_count: int,
        accepted_count: int,
        rejection_reasons: dict[str, int] | None = None,
    ) -> PurityResult:
        reasons = dict(rejection_reasons or {})
        rejected_count = max(int(total_count) - int(accepted_count), 0)
        return PurityResult(
            total_count=int(total_count),
            accepted_count=int(accepted_count),
            rejected_count=rejected_count,
            rejection_reasons=reasons,
        )

    @staticmethod
    def _coerce_payload(sample: Mapping[str, object] | IngestedSample) -> dict[str, object]:
        if isinstance(sample, IngestedSample):
            return SampleQualityScorer._coerce_sample(sample)
        if isinstance(sample, Mapping):
            return dict(sample)
        raise TypeError("data purity enforcement requires mapping or IngestedSample")

    @staticmethod
    def _extract_text(payload: dict[str, object]) -> str:
        return str(payload.get("description") or payload.get("raw_text") or "")

    @staticmethod
    def _extract_source(payload: dict[str, object]) -> str:
        return str(SampleQualityScorer._extract_source(payload)).strip().lower()

    @classmethod
    def _score_payload(cls, payload: dict[str, object]) -> float:
        explicit_quality_score = payload.get("quality_score")
        if explicit_quality_score not in (None, ""):
            score = float(explicit_quality_score)
            if not math.isfinite(score):
                raise ValueError("quality_score is not finite")
            payload["quality_score"] = score
            return score

        text = cls._extract_text(payload)
        text_length = len(text)
        if text_length <= 1:
            text_length_score = 0.0
        else:
            text_length_score = SampleQualityScorer._clamp(
                math.log(text_length) / math.log(2000)
            )
        has_cvss_score = 1.0 if payload.get("cvss_score") not in (None, "") else 0.0
        has_exploit_info = SampleQualityScorer._exploit_info_score(payload)
        source_trust_score = SampleQualityScorer._source_trust_score(payload)
        score = (
            text_length_score
            + has_cvss_score
            + has_exploit_info
            + source_trust_score
        ) / 4.0
        payload["quality_score"] = score
        return score

    @classmethod
    def _payload_rejection_reason(cls, payload: dict[str, object]) -> str | None:
        cve_id = str(payload.get("cve_id", "") or "").strip().upper()
        if not _CVE_ID_RE.fullmatch(cve_id):
            return "invalid_cve_id_format"

        severity = str(payload.get("severity", "") or "").strip().upper()
        if severity not in cls.ALLOWED_SEVERITIES:
            return "invalid_severity"

        source = cls._extract_source(payload)
        if source not in cls.ALLOWED_SOURCES:
            return "invalid_source"

        description = cls._extract_text(payload).strip()
        if len(description) < cls.MIN_DESCRIPTION_LENGTH:
            return "description_too_short"

        lowered_description = description.lower()
        if any(marker in lowered_description for marker in cls.UNSOURCED_MARKERS):
            return "halluci" "nation_marker"

        try:
            quality_score = cls._score_payload(payload)
        except (TypeError, ValueError):
            return "quality_score_invalid"
        if quality_score < cls.MIN_QUALITY_SCORE:
            return "low_quality_score"

        return None

    def enforce(
        self,
        sample: Mapping[str, object] | IngestedSample,
    ) -> tuple[dict[str, object] | IngestedSample | None, PurityResult]:
        payload = self._coerce_payload(sample)
        rejection_reason = self._payload_rejection_reason(payload)
        if isinstance(sample, dict):
            sample.update(payload)
            accepted_sample: dict[str, object] | IngestedSample = sample
        else:
            accepted_sample = sample

        if rejection_reason is not None:
            return None, self._build_result(
                total_count=1,
                accepted_count=0,
                rejection_reasons={rejection_reason: 1},
            )

        return accepted_sample, self._build_result(total_count=1, accepted_count=1)

    def enforce_batch(
        self,
        samples: Sequence[Mapping[str, object] | IngestedSample],
    ) -> tuple[list[dict[str, object] | IngestedSample], PurityResult]:
        accepted_samples: list[dict[str, object] | IngestedSample] = []
        rejection_reasons: dict[str, int] = {}

        for sample in samples:
            accepted_sample, result = self.enforce(sample)
            if accepted_sample is not None:
                accepted_samples.append(accepted_sample)
                continue
            rejection_reason = result.first_rejection_reason or "purity_rejected"
            rejection_reasons[rejection_reason] = rejection_reasons.get(rejection_reason, 0) + 1

        return accepted_samples, self._build_result(
            total_count=len(samples),
            accepted_count=len(accepted_samples),
            rejection_reasons=rejection_reasons,
        )

    def enforce_feature_tensor(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        ids: Sequence[str],
    ) -> tuple[np.ndarray, np.ndarray, list[str], PurityResult]:
        feature_array = np.asarray(features, dtype=np.float32)
        label_array = np.asarray(labels, dtype=np.int64)
        row_ids = [str(value) for value in ids]

        if feature_array.ndim != 2:
            raise ValueError(f"features must have shape (N, D), got {feature_array.shape}")
        if label_array.ndim != 1:
            raise ValueError(f"labels must have shape (N,), got {label_array.shape}")
        if feature_array.shape[0] != label_array.shape[0]:
            raise ValueError(
                "feature row count does not match label count: "
                f"{feature_array.shape[0]}!={label_array.shape[0]}"
            )
        if len(row_ids) != feature_array.shape[0]:
            raise ValueError(
                f"feature row count does not match ids count: {feature_array.shape[0]}!={len(row_ids)}"
            )
        if feature_array.shape[0] == 0:
            return feature_array, label_array, row_ids, self._build_result(total_count=0, accepted_count=0)

        accepted_indices: list[int] = []
        rejection_reasons: dict[str, int] = {}
        for index, feature_row in enumerate(feature_array):
            reason: str | None = None
            if feature_row.size == 0 or not np.isfinite(feature_row).all():
                reason = "non_finite_row"
            elif np.all(feature_row == 0.0):
                reason = "all_zero_row"
            elif float(np.var(feature_row)) <= 0.0:
                reason = "zero_variance_row"

            if reason is not None:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                continue
            accepted_indices.append(index)

        if not accepted_indices:
            result = self._build_result(
                total_count=feature_array.shape[0],
                accepted_count=0,
                rejection_reasons=rejection_reasons,
            )
            raise AllRowsRejectedError(self.ALL_ROWS_REJECTED_MESSAGE, result)

        accepted_index_array = np.asarray(accepted_indices, dtype=np.int64)
        accepted_features = feature_array[accepted_index_array]
        accepted_labels = label_array[accepted_index_array]
        accepted_ids = [row_ids[index] for index in accepted_indices]
        result = self._build_result(
            total_count=feature_array.shape[0],
            accepted_count=len(accepted_indices),
            rejection_reasons=rejection_reasons,
        )
        return accepted_features, accepted_labels, accepted_ids, result
