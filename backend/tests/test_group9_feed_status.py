import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from aiolimiter import AsyncLimiter

from backend.cve.cve_scheduler import CVEIngestScheduler, SourceCycleStats
from backend.ingestion.adapters.bugcrowd import BugcrowdAdapter, BugcrowdFeedResult


async def _no_sleep(_seconds: float) -> None:
    return None


class _FakeRetryPipeline:
    def __init__(self) -> None:
        self._source_status: dict[str, object] = {}
        self.source_errors: list[tuple[str, str]] = []
        self.stage_results: list[tuple[str, str, str, dict[str, object]]] = []

    def mark_source_error(self, source_id: str, message: str) -> None:
        self.source_errors.append((source_id, message))

    def record_stage_result(
        self,
        source_id: str,
        stage: str,
        status: str,
        **kwargs: object,
    ) -> None:
        self.stage_results.append((source_id, stage, status, kwargs))


class _FakeCyclePipeline:
    def __init__(self) -> None:
        self._source_status: dict[str, object] = {}
        self.recorded_job_execution: list[bool] = []

    def can_fetch_source(self, source_id: str) -> bool:
        raise AssertionError(f"{source_id} should be skipped before any fetch attempt")

    def record_job_execution(self, success: bool) -> None:
        self.recorded_job_execution.append(success)


class _FakeBridgeWorker:
    is_bridge_loaded = True

    def stream_ingest_new(self, _pipeline: object) -> int:
        return 0

    def update_manifest(self) -> None:
        return None


class _FakeClientSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_feed_source_status_fields_after_success_and_failure(monkeypatch):
    scheduler = CVEIngestScheduler()
    pipeline = _FakeRetryPipeline()

    async def _success(_pipeline: object, _source_id: str) -> SourceCycleStats:
        return SourceCycleStats(
            source_id="cve_services",
            success=True,
            records_seen=5,
            records_ingested=4,
            duplicates=1,
        )

    async def _failure(_pipeline: object, _source_id: str) -> SourceCycleStats:
        return SourceCycleStats(
            source_id="cve_services",
            success=False,
            error="timeout",
        )

    monkeypatch.setattr("backend.cve.cve_scheduler.asyncio.sleep", _no_sleep)
    monkeypatch.setattr(scheduler, "_fetch_source", _success)

    await scheduler._fetch_source_with_retry(pipeline, "cve_services")

    status_by_name = {
        entry.source_name: entry for entry in scheduler.get_feed_status()
    }
    success_status = status_by_name["CVE Services / cve.org"]
    assert success_status.last_attempt is not None
    assert success_status.last_success is not None
    assert success_status.consecutive_failures == 0
    assert success_status.samples_fetched_total == 5
    assert success_status.available is True
    assert success_status.requires_credentials is False

    last_success = success_status.last_success
    last_attempt = success_status.last_attempt

    monkeypatch.setattr(scheduler, "_fetch_source", _failure)
    await scheduler._fetch_source_with_retry(pipeline, "cve_services")

    failed_status = {
        entry.source_name: entry for entry in scheduler.get_feed_status()
    }["CVE Services / cve.org"]
    assert failed_status.last_attempt is not None
    assert failed_status.last_attempt >= last_attempt
    assert failed_status.last_success == last_success
    assert failed_status.consecutive_failures == 1
    assert failed_status.samples_fetched_total == 5
    assert failed_status.available is True


@pytest.mark.asyncio
async def test_three_consecutive_failures_mark_source_unavailable(monkeypatch, caplog):
    scheduler = CVEIngestScheduler()
    pipeline = _FakeRetryPipeline()

    async def _failure(_pipeline: object, _source_id: str) -> SourceCycleStats:
        return SourceCycleStats(
            source_id="cve_services",
            success=False,
            error="timeout",
        )

    monkeypatch.setattr("backend.cve.cve_scheduler.asyncio.sleep", _no_sleep)
    monkeypatch.setattr(scheduler, "_fetch_source", _failure)

    await scheduler._fetch_source_with_retry(pipeline, "cve_services")
    await scheduler._fetch_source_with_retry(pipeline, "cve_services")

    with caplog.at_level(logging.WARNING):
        await scheduler._fetch_source_with_retry(pipeline, "cve_services")

    status = {
        entry.source_name: entry for entry in scheduler.get_feed_status()
    }["CVE Services / cve.org"]
    assert status.consecutive_failures == 3
    assert status.available is False
    assert any(
        "marked unavailable after 3 consecutive failures" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_missing_credentials_skips_gracefully_with_info_log(monkeypatch, caplog):
    import backend.cve.cve_pipeline as pipeline_mod
    import backend.cve.bridge_ingestion_worker as bridge_worker_mod

    fake_pipeline = _FakeCyclePipeline()
    monkeypatch.delenv("VULNERS_API_KEY", raising=False)
    monkeypatch.setattr(
        pipeline_mod,
        "_SOURCE_CONFIGS",
        {
            "vulners": {
                "name": "Vulners",
                "url": "https://vulners.com/api/v3/",
                "requires_key": True,
                "key_env": "VULNERS_API_KEY",
                "staleness_hours": 12,
                "confidence": 0.80,
                "priority": 5,
                "is_canonical": False,
                "severity_rank": 1,
            }
        },
    )
    monkeypatch.setattr(pipeline_mod, "get_pipeline", lambda: fake_pipeline)
    monkeypatch.setattr(
        bridge_worker_mod,
        "get_bridge_worker",
        lambda: _FakeBridgeWorker(),
    )

    scheduler = CVEIngestScheduler()

    with caplog.at_level(logging.INFO):
        await scheduler._execute_ingest_cycle()

    status = scheduler.get_feed_status()[0]
    assert status.source_name == "Vulners"
    assert status.requires_credentials is True
    assert status.available is False
    assert status.consecutive_failures == 0
    assert fake_pipeline.recorded_job_execution == [True]
    assert any(
        "requires credentials" in record.message and "being skipped" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_bugcrowd_unavailable_returns_result_object(monkeypatch):
    adapter = BugcrowdAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    monkeypatch.setattr(
        "backend.ingestion.adapters.bugcrowd.aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeClientSession(),
    )
    monkeypatch.setattr(
        adapter,
        "_get",
        AsyncMock(
            side_effect=[
                RuntimeError("engagements unavailable"),
                RuntimeError("disclosures unavailable"),
            ]
        ),
    )

    result = await adapter.fetch()

    assert isinstance(result, BugcrowdFeedResult)
    assert result.available is False
    assert result.samples_fetched == 0
    assert result.source == "bugcrowd"
    assert result.failure_reason is not None
    assert "engagements unavailable" in result.failure_reason
    assert "disclosures unavailable" in result.failure_reason
    assert list(result) == []
