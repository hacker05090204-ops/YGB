import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiolimiter import AsyncLimiter

from backend.cve.cve_pipeline import CVEPipeline, CircuitState
from backend.cve.cve_scheduler import CVEIngestScheduler, SourceCycleStats
from backend.ingestion.adapters.bugcrowd import BugcrowdAdapter, BugcrowdFeedResult


async def _no_sleep(_seconds: float) -> None:
    return None


class _FakeRetryPipeline:
    def __init__(self) -> None:
        self._source_status: dict[str, object] = {}
        self.source_errors: list[tuple[str, str]] = []
        self.stage_results: list[tuple[str, str, str, dict[str, object]]] = []

    def mark_source_error(
        self,
        source_id: str,
        message: str,
        *,
        trip_circuit: bool = True,
    ) -> None:
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


class _FakeFetchPipeline:
    def __init__(self) -> None:
        self._freshness: dict[str, object] = {}
        self.no_delta_calls: list[str] = []
        self.success_calls: list[tuple[str, int, str, str]] = []
        self.stage_results: list[tuple[str, str, str, dict[str, object]]] = []

    def mark_source_no_delta(self, source_id: str) -> None:
        self.no_delta_calls.append(source_id)

    def mark_source_success(
        self,
        source_id: str,
        records_count: int,
        etag: str = "",
        last_modified_header: str = "",
    ) -> None:
        self.success_calls.append((source_id, records_count, etag, last_modified_header))

    def record_stage_result(
        self,
        source_id: str,
        stage: str,
        status: str,
        **kwargs: object,
    ) -> None:
        self.stage_results.append((source_id, stage, status, kwargs))


class _FakeHTTPXResponse:
    def __init__(
        self,
        status_code: int,
        *,
        json_data: dict[str, object] | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self._text = text
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> dict[str, object]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(
                self.status_code,
                request=request,
                text=self._text,
                headers=self.headers,
            )
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=response,
            )


class _FakeHTTPXClient:
    def __init__(
        self,
        response: _FakeHTTPXResponse,
        calls: list[tuple[str, dict[str, str], dict[str, str]]],
    ) -> None:
        self._response = response
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        follow_redirects: bool = False,
    ) -> _FakeHTTPXResponse:
        self._calls.append((url, dict(headers or {}), dict(params or {})))
        return self._response


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
async def test_http_400_does_not_trip_circuit_breaker(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "YGB_CVE_DEDUP_STORE_PATH",
        str(tmp_path / "group9_cve_dedup_store.json"),
    )
    scheduler = CVEIngestScheduler()
    pipeline = CVEPipeline()

    async def _bad_request(_pipeline: object, _source_id: str) -> SourceCycleStats:
        return SourceCycleStats(
            source_id="cve_services",
            success=False,
            error="HTTP 400",
            non_retryable=True,
            trip_circuit=False,
            requires_format_fix=True,
        )

    monkeypatch.setattr(scheduler, "_fetch_source", _bad_request)

    result = await scheduler._fetch_source_with_retry(pipeline, "cve_services")

    assert result.error == "HTTP 400"
    breaker = pipeline._circuit_breakers["cve_services"]
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    status = {
        entry.source_name: entry for entry in scheduler.get_feed_status()
    }["CVE Services / cve.org"]
    assert status.requires_format_fix is True


@pytest.mark.asyncio
async def test_304_response_logged_at_info_not_warning(monkeypatch, caplog):
    scheduler = CVEIngestScheduler()
    pipeline = _FakeFetchPipeline()
    response = _FakeHTTPXResponse(status_code=304)
    calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    monkeypatch.setattr(scheduler, "source_health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeHTTPXClient(response, calls),
    )

    with caplog.at_level(logging.INFO):
        result = await scheduler._fetch_source(pipeline, "cveproject")

    assert result.no_delta is True
    assert pipeline.no_delta_calls == ["cveproject"]
    assert any(
        "source returned no delta — skipping cycle" in record.message
        and record.levelno == logging.INFO
        for record in caplog.records
    )
    assert not any(
        record.levelno >= logging.WARNING
        and "no delta" in record.message.lower()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_nvd_v2_url_format_is_used(monkeypatch):
    scheduler = CVEIngestScheduler()
    pipeline = _FakeFetchPipeline()
    pipeline._freshness["cve_services"] = SimpleNamespace(
        last_seen_timestamp="2026-04-08T20:00:00+00:00",
        last_success_at="2026-04-08T20:00:00+00:00",
        last_etag=None,
        last_modified_header=None,
    )
    response = _FakeHTTPXResponse(status_code=200, json_data={"vulnerabilities": []})
    calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    monkeypatch.setattr(scheduler, "source_health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeHTTPXClient(response, calls),
    )
    monkeypatch.setattr(
        scheduler,
        "_parse_and_ingest",
        lambda *_args, **_kwargs: {
            "records_seen": 0,
            "records_ingested": 0,
            "duplicates": 0,
            "rejected": 0,
            "rejection_reasons": {},
        },
    )

    result = await scheduler._fetch_source(pipeline, "cve_services")

    assert result.success is True
    assert len(calls) == 1
    url, headers, params = calls[0]
    assert url == "https://services.nvd.nist.gov/rest/json/cves/2.0"
    assert "pubStartDate" in params
    assert "pubEndDate" in params
    assert "apiKey" not in headers


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
