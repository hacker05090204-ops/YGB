"""Phase 1 CVE ingestion tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.cve.cve_scheduler import CVEIngestScheduler
from backend.ingestion.normalizer import normalize_sample_with_quality
from backend.training.auto_train_controller import AutoTrainController
from backend.training.incremental_trainer import DatasetQualityGate


@pytest.mark.asyncio
async def test_nvd_400_not_retried():
    scheduler = CVEIngestScheduler()
    pipeline = MagicMock()
    pipeline._freshness = {}
    pipeline._source_status = {}
    pipeline.mark_source_error = MagicMock()
    pipeline.record_stage_result = MagicMock()

    response = MagicMock()
    response.status_code = 400
    response.text = "Bad Request: invalid request window"

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
        with patch.object(scheduler, "source_health_check", AsyncMock(return_value=True)):
            result = await scheduler._fetch_source_with_retry(pipeline, "nvd")

    assert result.error == "HTTP 400"
    assert result.attempts == 1
    status = {entry.source_name: entry for entry in scheduler.get_feed_status()}["NVD API v2"]
    assert status.health_state == "BROKEN"


@pytest.mark.asyncio
async def test_nvd_304_info_logged(caplog):
    scheduler = CVEIngestScheduler()
    pipeline = MagicMock()
    pipeline._freshness = {}
    pipeline.mark_source_no_delta = MagicMock()
    pipeline.record_stage_result = MagicMock()

    response = MagicMock()
    response.status_code = 304

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
        with caplog.at_level("INFO"):
            result = await scheduler._fetch_nvd_v2(
                pipeline,
                "nvd",
                {"url": "https://services.nvd.nist.gov/rest/json/cves/2.0"},
                {},
            )

    assert result.no_delta is True
    assert any("no delta" in record.message.lower() and record.levelname == "INFO" for record in caplog.records)
    assert not any(record.levelname == "WARNING" and "no delta" in record.message.lower() for record in caplog.records)


def test_cvss_severity_derivation():
    long_text = "Remote code execution vulnerability affecting multiple systems. " * 8
    cases = [
        (9.5, "CRITICAL"),
        (7.5, "HIGH"),
        (5.0, "MEDIUM"),
        (2.0, "LOW"),
    ]

    for score, expected in cases:
        normalized, accepted, _, _ = normalize_sample_with_quality(
            {
                "cve_id": f"CVE-2026-{int(score * 10):04d}",
                "description": long_text,
                "source": "nvd",
                "cvss_score": score,
            },
            ignore_duplicates=True,
        )
        assert accepted is True
        assert normalized["severity"] == expected


def test_missing_cvss_informational():
    normalized, accepted, _, _ = normalize_sample_with_quality(
        {
            "cve_id": "CVE-2026-9999",
            "description": "Informational advisory with sufficient detail for ingestion. " * 10,
            "source": "nvd",
        },
        ignore_duplicates=True,
    )

    assert accepted is True
    assert normalized["severity"] == "INFORMATIONAL"


def test_adaptive_threshold_50_samples():
    controller = AutoTrainController()
    with patch.object(controller.feature_store, "total_samples", return_value=100):
        assert controller._compute_trigger_threshold() == 50


def test_adaptive_threshold_200_samples():
    controller = AutoTrainController()
    with patch.object(controller.feature_store, "total_samples", return_value=1000):
        assert controller._compute_trigger_threshold() == 100


def test_per_class_distribution_realistic():
    gate = DatasetQualityGate()
    base_desc = "Security vulnerability with detailed impact and remediation guidance. " * 10
    samples = []
    for i in range(40):
        samples.append({"cve_id": f"CVE-2026-{i:04d}", "severity": "HIGH", "description": base_desc, "cvss_score": 7.5, "source": "nvd"})
    for i in range(35):
        samples.append({"cve_id": f"CVE-2026-{i+40:04d}", "severity": "MEDIUM", "description": base_desc, "cvss_score": 5.0, "source": "nvd"})
    for i in range(15):
        samples.append({"cve_id": f"CVE-2026-{i+75:04d}", "severity": "CRITICAL", "description": base_desc, "cvss_score": 9.5, "source": "nvd"})
    for i in range(10):
        samples.append({"cve_id": f"CVE-2026-{i+90:04d}", "severity": "LOW", "description": base_desc, "cvss_score": 2.0, "source": "nvd"})

    report = gate.validate(samples)

    assert report.passed is True
    assert report.sample_count == 100
