from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from urllib.robotparser import RobotFileParser
from unittest.mock import AsyncMock, patch

import pytest
from aiolimiter import AsyncLimiter

from backend.ingestion import AsyncIngestor, IngestCycleResult, IngestedSample, run_ingestion_cycle
import backend.ingestion.models as ingestion_models
from backend.ingestion import normalizer
from backend.ingestion.adapters import (
    BugcrowdAdapter,
    CISAKEVAdapter,
    ExploitDBAdapter,
    GitHubAdvisoryAdapter,
    HackerOneAdapter,
    NVDAdapter,
)
from backend.ingestion.base_adapter import BaseAdapter
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import detect_language, make_sample, normalize_severity, sample_to_dict
from backend.observability.metrics import metrics_registry


class DummyAdapter(BaseAdapter):
    SOURCE = "dummy"

    async def fetch(self) -> list[IngestedSample]:
        return []


class FakeResponse:
    def __init__(self, status: int, body: str, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class FakeClientSession:
    def __init__(self, *args, **kwargs) -> None:
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeExecutor:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def __enter__(self) -> "FakeExecutor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def map(self, func, values):
        return [func(value) for value in values]


class StubAdapter:
    def __init__(self, source: str, result) -> None:
        self.SOURCE = source
        self._result = result

    async def fetch(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _make_quality_scorer(tmp_path):
    return normalizer.SampleQualityScorer(
        dedup_store=DedupIndex(str(tmp_path / "dedup_store.json")),
        rejection_log=normalizer.QualityRejectionLog(),
    )


def _quality_payload(
    description: str,
    *,
    cve_id: str = "CVE-2026-0001",
    severity: str = "HIGH",
    source: str = "nvd",
    cvss_score: float | None = 8.1,
    is_exploited: bool = True,
    tags: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "source": source,
        "description": description,
        "raw_text": description,
        "url": "https://example.com/advisory",
        "cve_id": cve_id,
        "severity": severity,
        "cvss_score": cvss_score,
        "is_exploited": is_exploited,
        "tags": list(tags),
    }


@pytest.fixture(autouse=True)
def reset_metrics_and_caches(monkeypatch, tmp_path):
    metrics_registry.reset()
    BaseAdapter._robots_cache.clear()
    BaseAdapter._domain_limiters.clear()
    monkeypatch.setattr(normalizer, "NORMALIZED_ROOT", tmp_path / "normalized")
    yield


def test_model_helpers_and_exports():
    sample = make_sample("source", "hello world", "https://example.com", "", "high", ("tag",))
    payload = sample_to_dict(sample)
    assert normalize_severity("low") == "LOW"
    assert normalize_severity("bogus") == "UNKNOWN"
    assert detect_language("") == "en"
    with patch("backend.ingestion.models.detect", side_effect=ingestion_models.LangDetectException(0, "bad")):
        assert detect_language("bad input") == "en"
    assert payload["source"] == "source"
    assert payload["tags"] == ["tag"]
    assert isinstance(sample, IngestedSample)
    assert AsyncIngestor is not None
    assert run_ingestion_cycle is not None


def test_dedup_load_save_and_stats(tmp_path):
    index = DedupIndex(str(tmp_path / "dedup.json"))
    index.load()
    index.record_seen("CVE-2026-0001", "abc", source="nvd")
    assert index.is_duplicate("CVE-2026-0001", "fresh") is True
    assert index.is_duplicate("CVE-2026-9999", "abc") is True
    index.save()

    restored = DedupIndex(str(tmp_path / "dedup.json"))
    restored.load()
    restored.record_seen("CVE-2026-0002", "def", source="nvd")
    stats = index.stats()

    assert restored.seen_hashes == {"abc", "def"}
    assert restored.seen_cve_ids == {"CVE-2026-0001", "CVE-2026-0002"}
    assert stats["total_seen"] == 1.0
    assert stats["dupes_found"] == 2.0
    assert stats["duplicate_rate"] == pytest.approx(2 / 3)
    assert (tmp_path / "dedup_store.json").exists()

    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    list_payload = legacy_root / "dedup_list.json"
    list_payload.write_text('["xyz"]', encoding="utf-8")
    from_list = DedupIndex(str(list_payload))
    from_list.load()
    assert from_list.seen_hashes == {"xyz"}
    assert list_payload.exists() is False


def test_quality_score_computed_correctly(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    description = "A" * 200
    sample = _quality_payload(description)

    score = scorer.score(sample)

    expected = (
        min(math.log(len(description)) / math.log(2000), 1.0)
        + 1.0
        + 1.0
        + 1.0
    ) / 4.0
    assert score == pytest.approx(expected)
    assert float(sample["quality_score"]) == pytest.approx(expected)


def test_quality_gate_rejects_short_description(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    accepted, reason, score = scorer.evaluate(_quality_payload("Too short for acceptance"))

    assert accepted is False
    assert reason == "description_too_short"
    assert score < 1.0


def test_quality_gate_rejects_missing_cve_id(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    description = "Detailed vulnerability context that exceeds the minimum description length by design."
    accepted, reason, _ = scorer.evaluate(_quality_payload(description, cve_id=""))

    assert accepted is False
    assert reason == "missing_cve_id"


def test_quality_gate_rejects_low_score(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    description = "This narrative is long enough to pass length checks but lacks trust and exploit detail."
    accepted, reason, score = scorer.evaluate(
        _quality_payload(
            description,
            source="other",
            cvss_score=None,
            is_exploited=False,
        )
    )

    assert accepted is False
    assert reason == "low_quality_score"
    assert score < 0.4


def test_quality_gate_accepts_high_quality_nvd_sample(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    description = (
        "This NVD vulnerability description contains detailed impact analysis, affected scope, "
        "exploitability context, and remediation guidance for downstream ingestion quality checks."
    )
    sample = _quality_payload(description, cve_id="CVE-2026-1001")

    accepted, reason, score = scorer.evaluate(sample)
    if accepted:
        scorer.record_seen(sample)

    stats = scorer.get_quality_stats()
    assert accepted is True
    assert reason is None
    assert score >= 0.4
    assert stats["accepted"] == 1
    assert stats["rejected"] == 0


def test_quality_gate_rejects_duplicate_cve_id(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    first = _quality_payload(
        "A sufficiently detailed vulnerability description for the first accepted CVE sample.",
        cve_id="CVE-2026-2222",
    )
    accepted, _, _ = scorer.evaluate(first)
    assert accepted is True
    scorer.record_seen(first)

    second = _quality_payload(
        "A different but equally detailed vulnerability narrative for the duplicate CVE identifier.",
        cve_id="CVE-2026-2222",
    )
    accepted, reason, _ = scorer.evaluate(second)

    assert accepted is False
    assert reason == "duplicate_cve_id"


def test_quality_gate_rejects_duplicate_text_hash(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    description = (
        "This identical normalized vulnerability description is reused to trigger text hash deduplication."
    )
    first = _quality_payload(description, cve_id="CVE-2026-3001")
    accepted, _, _ = scorer.evaluate(first)
    assert accepted is True
    scorer.record_seen(first)

    second = _quality_payload(description, cve_id="CVE-2026-3002")
    accepted, reason, _ = scorer.evaluate(second)

    assert accepted is False
    assert reason == "duplicate_text_hash"


def test_quality_stats_reflect_counts(tmp_path):
    scorer = _make_quality_scorer(tmp_path)
    accepted_sample = _quality_payload(
        "This accepted sample includes extensive detail about scope, impact, exploitability, and remediation.",
        cve_id="CVE-2026-4001",
    )
    accepted, _, _ = scorer.evaluate(accepted_sample)
    assert accepted is True
    scorer.record_seen(accepted_sample)
    scorer.evaluate(_quality_payload("short text", cve_id="CVE-2026-4002"))
    scorer.evaluate(_quality_payload(accepted_sample["description"], cve_id="CVE-2026-4003"))

    stats = scorer.get_quality_stats()
    assert stats["accepted"] == 1
    assert stats["rejected"] == 2
    assert stats["rejection_reasons"]["description_too_short"] == 1
    assert stats["rejection_reasons"]["duplicate_text_hash"] == 1


def test_normalize_text_and_batch_cache(monkeypatch, tmp_path):
    sample = make_sample(
        "source",
        "<p>caf\u00e9</p>\n" + "word " * 600,
        "https://example.com",
        "",
        "info",
        (),
    )
    monkeypatch.setattr(normalizer, "ProcessPoolExecutor", FakeExecutor)
    batch = normalizer.normalize_batch([sample])
    cached = normalizer.normalize_batch([sample])
    normalized_text = batch[0].raw_text

    assert "\n" not in normalized_text
    assert "<p>" not in normalized_text
    assert len(normalized_text.split()) == 512
    assert batch[0].raw_text == cached[0].raw_text
    assert (tmp_path / "normalized" / f"{sample.sha256_hash}.json").exists()


def test_normalize_batch_report_tracks_cache_and_backpressure(monkeypatch):
    sample_one = make_sample("source", "<p>alpha</p>", "https://example.com/a", "", "info", ())
    sample_two = make_sample("source", "<p>beta</p>", "https://example.com/b", "", "info", ())
    monkeypatch.setattr(normalizer, "ProcessPoolExecutor", FakeExecutor)

    batch, report = normalizer.normalize_batch_with_report([sample_one, sample_two], batch_limit=1)
    cached_batch, cached_report = normalizer.normalize_batch_with_report(
        [sample_one, sample_two],
        batch_limit=1,
    )

    assert len(batch) == 2
    assert report.requested == 2
    assert report.cache_hits == 0
    assert report.cache_misses == 2
    assert report.backpressure_applied is True
    assert report.chunk_count == 2
    assert cached_batch[0].raw_text == batch[0].raw_text
    assert cached_report.cache_hits == 2
    assert cached_report.normalized == 0
    assert cached_report.emitted == 2


def test_normalize_batch_falls_back_without_spawnable_main(monkeypatch):
    sample = make_sample("source", "<p>hello</p>", "https://example.com", "", "info", ())
    monkeypatch.setattr(normalizer, "_main_module_supports_spawn", lambda: False)
    monkeypatch.setattr(normalizer, "_POOL_DISABLED", False)

    batch = normalizer.normalize_batch([sample])

    assert batch[0].raw_text == "hello"


def test_normalize_batch_guard(monkeypatch):
    assert normalizer.normalize_batch([]) == []
    sample = make_sample("source", "hello", "https://example.com", "", "info", ())
    monkeypatch.setattr(normalizer, "can_ai_execute", lambda: (True, "blocked"))
    with pytest.raises(RuntimeError, match="GUARD"):
        normalizer.normalize_batch([sample])


@pytest.mark.asyncio
async def test_base_adapter_perform_request_robots_and_retries(monkeypatch):
    adapter = DummyAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    session = FakeSession(
        [
            FakeResponse(200, "User-agent: *\nDisallow: /blocked", {"Content-Type": "text/plain"}),
            FakeResponse(429, '{"status":"retry"}', {"Content-Type": "application/json"}),
            FakeResponse(500, '{"status":"server"}', {"Content-Type": "application/json"}),
            FakeResponse(200, '{"status":"ok"}', {"Content-Type": "application/json", "X-Test": "1"}),
        ]
    )
    sleep_calls: list[int] = []

    async def fake_sleep(value: int) -> None:
        sleep_calls.append(value)

    monkeypatch.setattr("backend.ingestion.base_adapter.asyncio.sleep", fake_sleep)

    allowed = await adapter._robots_allowed(session, "https://example.com/open")
    blocked = await adapter._robots_allowed(session, "https://example.com/blocked")
    response = await adapter._get(session, "https://example.com/open")

    assert allowed is True
    assert blocked is False
    assert response == {"status": "ok"}
    assert sleep_calls == [2, 5]
    assert metrics_registry.get_counter("ingest_http_requests_total") == 4.0
    assert adapter._last_response_headers["X-Test"] == "1"


@pytest.mark.asyncio
async def test_nvd_adapter_includes_pub_end_date(monkeypatch):
    adapter = NVDAdapter(asyncio.Semaphore(1), AsyncLimiter(2, 1))
    captured: dict[str, object] = {}

    async def fake_get(session, url, *, params=None, **kwargs):
        captured.update(params or {})
        return {"totalResults": 0, "resultsPerPage": 1, "vulnerabilities": []}

    monkeypatch.setattr(adapter, "_get", fake_get)
    monkeypatch.setattr(
        "backend.ingestion.adapters.nvd.aiohttp.ClientSession",
        lambda *args, **kwargs: FakeClientSession(*args, **kwargs),
    )

    await adapter.fetch()

    assert "pubStartDate" in captured
    assert "pubEndDate" in captured


@pytest.mark.asyncio
async def test_base_adapter_guard_and_permission_errors(monkeypatch):
    adapter = DummyAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    monkeypatch.setattr("backend.ingestion.base_adapter.can_ai_use_network", lambda: (True, "blocked"))
    with pytest.raises(RuntimeError, match="GUARD"):
        await adapter._get(FakeSession([]), "https://example.com")

    monkeypatch.setattr("backend.ingestion.base_adapter.can_ai_use_network", lambda: (False, "allowed"))
    monkeypatch.setattr(adapter, "_robots_allowed", AsyncMock(return_value=False))
    with pytest.raises(PermissionError):
        await adapter._get(FakeSession([]), "https://example.com")


@pytest.mark.asyncio
async def test_base_adapter_cache_eviction_and_http_error(monkeypatch):
    adapter = DummyAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    BaseAdapter._domain_limiters = OrderedDict((f"old{i}.example", AsyncLimiter(2, 1)) for i in range(100))
    BaseAdapter._get_domain_limiter("fresh.example")
    assert "old0.example" not in BaseAdapter._domain_limiters

    BaseAdapter._robots_cache = OrderedDict((f"old{i}.example", RobotFileParser()) for i in range(100))
    monkeypatch.setattr(
        adapter,
        "_perform_request",
        AsyncMock(return_value=(200, "User-agent: *\nAllow: /", {"Content-Type": "text/plain"})),
    )
    await adapter._get_robot_parser(FakeSession([]), "https://fresh.example/open")
    assert "old0.example" not in BaseAdapter._robots_cache

    monkeypatch.setattr(adapter, "_robots_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        adapter,
        "_perform_request",
        AsyncMock(return_value=(404, "missing", {"Content-Type": "text/plain"})),
    )
    with pytest.raises(RuntimeError, match="HTTP 404"):
        await adapter._get(FakeSession([]), "https://fresh.example/open")


@pytest.mark.asyncio
async def test_base_adapter_decode_plain_text(monkeypatch):
    adapter = DummyAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    monkeypatch.setattr(adapter, "_robots_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        adapter,
        "_perform_request",
        AsyncMock(return_value=(200, "plain text", {"Content-Type": "text/plain"})),
    )
    result = await adapter._get(FakeSession([]), "https://example.com")
    assert result == "plain text"


@pytest.mark.asyncio
async def test_hackerone_adapter_parses_directory_html(monkeypatch):
    adapter = HackerOneAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    payload = """
    <html><body>
      <a href="https://hackerone.com/program-one" data-item-name="Program One" class="bug-bounty-list-item">
        <span class="bug-bounty-list-item-meta-item">Public</span>
        <div class="bug-bounty-list-item-policy">Find real bugs fast</div>
      </a>
      <a href="https://hackerone.com/program-two" data-item-name="Program Two" class="bug-bounty-list-item">
        <span class="bug-bounty-list-item-meta-item">Private</span>
        <div class="bug-bounty-list-item-policy">Second policy summary</div>
      </a>
    </body></html>
    """
    monkeypatch.setattr("backend.ingestion.adapters.hackerone.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(return_value=payload))
    samples = await adapter.fetch()

    assert client.entered is True
    assert len(samples) == 2
    assert samples[0].url == "https://hackerone.com/program-one"
    assert all(sample.severity == "INFO" for sample in samples)


@pytest.mark.asyncio
async def test_hackerone_adapter_skips_short_and_duplicate_entries(monkeypatch):
    adapter = HackerOneAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    payload = """
    <html><body>
      <a href="https://hackerone.com/skip" data-item-name="Tiny" class="bug-bounty-list-item">
        <div class="bug-bounty-list-item-policy">short</div>
      </a>
      <a href="https://hackerone.com/keep" data-item-name="Keep Me" class="bug-bounty-list-item">
        <span class="bug-bounty-list-item-meta-item">Public</span>
        <div class="bug-bounty-list-item-policy">A much longer policy description for ingestion</div>
      </a>
      <a href="https://hackerone.com/keep" data-item-name="Keep Me Again" class="bug-bounty-list-item">
        <span class="bug-bounty-list-item-meta-item">Duplicate</span>
        <div class="bug-bounty-list-item-policy">Duplicate URL should be dropped</div>
      </a>
    </body></html>
    """
    monkeypatch.setattr("backend.ingestion.adapters.hackerone.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(return_value=payload))
    samples = await adapter.fetch()

    assert len(samples) == 1
    assert samples[0].url == "https://hackerone.com/keep"
    assert samples[0].raw_text


@pytest.mark.asyncio
async def test_nvd_adapter_parsing(monkeypatch):
    adapter = NVDAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    payload = {
        "totalResults": 1,
        "resultsPerPage": 2000,
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-0001",
                    "descriptions": [{"lang": "en", "value": "NVD description"}],
                    "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}]},
                    "weaknesses": [{"description": [{"value": "CWE-79"}]}],
                }
            }
        ],
    }
    monkeypatch.setattr("backend.ingestion.adapters.nvd.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(return_value=payload))
    samples = await adapter.fetch()

    assert adapter._extract_description({"descriptions": [{"lang": "fr", "value": "French"}]}) == "French"
    assert adapter._extract_description({"descriptions": []}) == ""
    assert adapter._extract_severity({"metrics": {}}) == "UNKNOWN"
    assert samples[0].cve_id == "CVE-2026-0001"
    assert samples[0].tags == ("CWE-79",)


@pytest.mark.asyncio
async def test_nvd_adapter_empty_pages_and_blank_descriptions(monkeypatch):
    adapter = NVDAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    empty_payload = {"totalResults": 0, "resultsPerPage": 2000, "vulnerabilities": []}
    blank_payload = {
        "totalResults": 1,
        "resultsPerPage": 2000,
        "vulnerabilities": [{"cve": {"id": "CVE-EMPTY", "descriptions": [], "metrics": {}, "weaknesses": []}}],
    }
    monkeypatch.setattr("backend.ingestion.adapters.nvd.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(side_effect=[empty_payload, blank_payload]))
    assert await adapter.fetch() == []
    assert await adapter.fetch() == []


@pytest.mark.asyncio
async def test_github_advisory_adapter_link_pagination(monkeypatch):
    adapter = GitHubAdvisoryAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    payloads = [
        [
            {"summary": "", "description": "", "html_url": "https://gh/skip", "severity": "low", "cwes": []},
            {"summary": "One", "description": "A", "html_url": "https://gh/1", "severity": "high", "cwes": [{"cwe_id": "CWE-89"}]},
        ],
        [{"summary": "Two", "description": "B", "html_url": "https://gh/2", "severity": "medium", "cve_id": "CVE-2", "cwes": []}],
    ]

    async def fake_get(session, url, **kwargs):
        if url == adapter.BASE:
            adapter._last_response_headers = {"Link": '<https://api.github.com/advisories?page=2>; rel="next"'}
            return payloads[0]
        adapter._last_response_headers = {"Link": ""}
        return payloads[1]

    monkeypatch.setattr("backend.ingestion.adapters.github_advisory.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", fake_get)
    samples = await adapter.fetch()

    assert len(samples) == 2
    assert samples[1].cve_id == "CVE-2"


@pytest.mark.asyncio
async def test_cisa_kev_adapter(monkeypatch):
    adapter = CISAKEVAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    payload = {
        "vulnerabilities": [
            {"vendorProject": "Vendor", "product": "Product", "shortDescription": "Desc", "cveID": "CVE-1"}
        ]
    }
    monkeypatch.setattr("backend.ingestion.adapters.cisa_kev.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(return_value=payload))
    samples = await adapter.fetch()

    assert samples[0].severity == "CRITICAL"
    assert samples[0].tags == ("kev", "exploited_in_wild")


@pytest.mark.asyncio
async def test_exploitdb_adapter(monkeypatch):
    adapter = ExploitDBAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    csv_payload = 'id,description,verified,type,platform\n1,Remote exploit,1,remote,"linux,windows"\n2,Ignore me,0,local,linux\n3,,1,local,linux\n'
    monkeypatch.setattr("backend.ingestion.adapters.exploitdb.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(return_value=csv_payload))
    samples = await adapter.fetch()

    assert len(samples) == 1
    assert samples[0].severity == "HIGH"


@pytest.mark.asyncio
async def test_bugcrowd_adapter(monkeypatch):
    adapter = BugcrowdAdapter(asyncio.Semaphore(10), AsyncLimiter(2, 1))
    client = FakeClientSession()
    payload = {
        "engagements": [
            {"name": "", "tagline": "", "briefUrl": "/skip"},
            {"name": "Program", "tagline": "Tag", "briefUrl": "/p/1"}
        ]
    }
    monkeypatch.setattr("backend.ingestion.adapters.bugcrowd.aiohttp.ClientSession", lambda *args, **kwargs: client)
    monkeypatch.setattr(adapter, "_get", AsyncMock(return_value=payload))
    samples = await adapter.fetch()

    assert samples[0].url == "https://bugcrowd.com/p/1"
    assert samples[0].severity == "INFO"


@pytest.mark.asyncio
async def test_async_ingestor_full_cycle_and_helper(monkeypatch, tmp_path):
    sample_one = make_sample("hackerone", "Alpha", "https://a", "", "high", ("x",))
    sample_two = make_sample("nvd", "Beta", "https://b", "CVE-1", "medium", ("CWE-79",))
    adapters = [
        StubAdapter("hackerone", [sample_one]),
        StubAdapter("nvd", [sample_two, sample_one]),
        StubAdapter("github_advisory", []),
        StubAdapter("cisa_kev", []),
        StubAdapter("exploitdb", RuntimeError("boom")),
        StubAdapter("bugcrowd", []),
    ]
    ingestor = AsyncIngestor(
        raw_root=str(tmp_path / "raw"),
        dedup_index_path=str(tmp_path / "raw" / "dedup_index.json"),
        adapters=adapters,
    )

    def fake_normalize_with_report(samples, batch_limit=0, quality_scorer=None):
        return samples, normalizer.NormalizationReport(
            requested=len(samples),
            cache_hits=0,
            cache_misses=len(samples),
            normalized=len(samples),
            emitted=len(samples),
            used_process_pool=False,
            pool_disabled=False,
            backpressure_applied=False,
            chunk_count=1 if samples else 0,
        )

    monkeypatch.setattr(
        "backend.ingestion.async_ingestor.normalize_batch_with_report",
        fake_normalize_with_report,
    )

    result = await ingestor.run_cycle()

    assert isinstance(result, IngestCycleResult)
    assert result.new_count == 2
    assert result.dupes_found == 1
    assert result.errors == 1
    assert result.normalized_count == 2
    assert result.backpressure_events == 0
    assert metrics_registry.get_counter("ingest_total_count") == 3.0
    assert metrics_registry.get_counter("ingest_new_count") == 2.0
    assert metrics_registry.get_gauge("duplicate_rate") == pytest.approx(1 / 3)
    written = list((tmp_path / "raw").rglob("*.json"))
    assert any(path.name == f"{sample_one.sha256_hash}.json" for path in written)

    with patch("backend.ingestion.async_ingestor.AsyncIngestor.run_cycle", AsyncMock(return_value=result)):
        helper_result = await run_ingestion_cycle()
    assert helper_result == result


@pytest.mark.asyncio
async def test_async_ingestor_reports_backpressure(monkeypatch, tmp_path):
    samples = [
        make_sample("nvd", f"Alpha {index}", f"https://example.com/{index}", f"CVE-{index}", "high", ())
        for index in range(3)
    ]
    ingestor = AsyncIngestor(
        raw_root=str(tmp_path / "raw"),
        dedup_index_path=str(tmp_path / "raw" / "dedup_index.json"),
        adapters=[StubAdapter("nvd", samples)],
    )
    ingestor.max_pending_samples = 1
    ingestor.max_normalize_batch = 1

    def fake_normalize_with_report(samples, batch_limit=0, quality_scorer=None):
        return samples, normalizer.NormalizationReport(
            requested=len(samples),
            cache_hits=0,
            cache_misses=len(samples),
            normalized=len(samples),
            emitted=len(samples),
            used_process_pool=False,
            pool_disabled=False,
            backpressure_applied=True,
            chunk_count=max(1, len(samples)),
        )

    monkeypatch.setattr(
        "backend.ingestion.async_ingestor.normalize_batch_with_report",
        fake_normalize_with_report,
    )

    result = await ingestor.run_cycle()

    assert result.backpressure_events == 1
    assert result.max_pending_depth == 3
    assert result.normalization_reports[0]["backpressure_applied"] is True
