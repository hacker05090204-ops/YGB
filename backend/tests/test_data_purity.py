from __future__ import annotations

import numpy as np
import pytest

from backend.training.data_purity import AllRowsRejectedError, DataPurityEnforcer


def _long_description(extra: str = "") -> str:
    return (
        "This vulnerability description includes detailed impact analysis, affected scope, "
        "exploitability context, and remediation guidance required for purity enforcement. "
        + extra
    )


def _payload(
    description: str,
    *,
    cve_id: str = "CVE-2026-0001",
    severity: str = "HIGH",
    source: str = "nvd",
) -> dict[str, object]:
    return {
        "source": source,
        "description": description,
        "raw_text": description,
        "url": "https://example.com/advisory",
        "cve_id": cve_id,
        "severity": severity,
        "cvss_score": 8.1,
        "is_exploited": True,
        "tags": ["CWE-79"],
    }


def _good_row() -> np.ndarray:
    return np.linspace(0.1, 1.0, 256, dtype=np.float32)


def test_enforce_rejects_hallucination_marker() -> None:
    enforcer = DataPurityEnforcer()

    accepted_sample, result = enforcer.enforce(
        _payload(_long_description("[hallucination] provenance missing"))
    )

    assert accepted_sample is None
    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.rejection_reasons == {"hallucination_marker": 1}


def test_enforce_rejects_invalid_cve_format() -> None:
    enforcer = DataPurityEnforcer()

    accepted_sample, result = enforcer.enforce(
        _payload(_long_description(), cve_id="CVE-2026-XYZ")
    )

    assert accepted_sample is None
    assert result.rejection_reasons == {"invalid_cve_id_format": 1}


def test_enforce_feature_tensor_removes_all_zero_row() -> None:
    enforcer = DataPurityEnforcer()
    features = np.stack([_good_row(), np.zeros(256, dtype=np.float32)], axis=0)
    labels = np.asarray([1, 0], dtype=np.int64)

    filtered_features, filtered_labels, filtered_ids, result = enforcer.enforce_feature_tensor(
        features,
        labels,
        ["good", "all-zero"],
    )

    assert filtered_features.shape == (1, 256)
    assert filtered_labels.tolist() == [1]
    assert filtered_ids == ["good"]
    assert result.rejection_reasons == {"all_zero_row": 1}


def test_enforce_feature_tensor_removes_zero_variance_row() -> None:
    enforcer = DataPurityEnforcer()
    features = np.stack([_good_row(), np.full(256, 0.5, dtype=np.float32)], axis=0)
    labels = np.asarray([1, 0], dtype=np.int64)

    filtered_features, filtered_labels, filtered_ids, result = enforcer.enforce_feature_tensor(
        features,
        labels,
        ["good", "constant"],
    )

    assert filtered_features.shape == (1, 256)
    assert filtered_labels.tolist() == [1]
    assert filtered_ids == ["good"]
    assert result.rejection_reasons == {"zero_variance_row": 1}


def test_enforce_batch_reports_counts() -> None:
    enforcer = DataPurityEnforcer()
    accepted_samples, result = enforcer.enforce_batch(
        [
            _payload(_long_description()),
            _payload(_long_description(), cve_id="BAD-CVE"),
            _payload(_long_description("hallucination_marker present")),
        ]
    )

    assert len(accepted_samples) == 1
    assert result.total_count == 3
    assert result.accepted_count == 1
    assert result.rejected_count == 2
    assert result.rejection_reasons == {
        "invalid_cve_id_format": 1,
        "hallucination_marker": 1,
    }


def test_enforce_feature_tensor_raises_when_all_rows_are_invalid() -> None:
    enforcer = DataPurityEnforcer()
    features = np.stack(
        [
            np.zeros(256, dtype=np.float32),
            np.full(256, 0.5, dtype=np.float32),
        ],
        axis=0,
    )
    labels = np.asarray([0, 1], dtype=np.int64)

    with pytest.raises(AllRowsRejectedError, match=DataPurityEnforcer.ALL_ROWS_REJECTED_MESSAGE) as exc_info:
        enforcer.enforce_feature_tensor(features, labels, ["all-zero", "constant"])

    assert exc_info.value.result.rejected_count == 2
    assert exc_info.value.result.rejection_reasons == {
        "all_zero_row": 1,
        "zero_variance_row": 1,
    }
