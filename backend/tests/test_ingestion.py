from __future__ import annotations

import asyncio
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
    index.mark_seen("abc")
    assert index.is_duplicate("abc") is True
    index.save()

    restored = DedupIndex(str(tmp_path / "dedup.json"))
    restored.load()
    restored.mark_seen("def")
    stats = index.stats()

    assert restored.seen_hashes == {"abc", "def"}
    assert stats["total_seen"] == 1.0
    assert stats["dupes_found"] == 1.0
    assert stats["duplicate_rate"] == 0.5
    assert (tmp_path / "dedup.db").exists()

    list_payload = tmp_path / "dedup_list.json"
    list_payload.write_text('["xyz"]', encoding="utf-8")
    from_list = DedupIndex(str(list_payload))
    from_list.load()
    assert from_list.seen_hashes == {"xyz"}
    assert list_payload.exists() is False


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
    monkeypatch.setattr("backend.ingestion.async_ingestor.normalize_batch", lambda samples: samples)

    result = await ingestor.run_cycle()

    assert isinstance(result, IngestCycleResult)
    assert result.new_count == 2
    assert result.dupes_found == 1
    assert result.errors == 1
    assert metrics_registry.get_counter("ingest_total_count") == 3.0
    assert metrics_registry.get_counter("ingest_new_count") == 2.0
    assert metrics_registry.get_gauge("duplicate_rate") == pytest.approx(1 / 3)
    written = list((tmp_path / "raw").rglob("*.json"))
    assert any(path.name == f"{sample_one.sha256_hash}.json" for path in written)

    with patch("backend.ingestion.async_ingestor.AsyncIngestor.run_cycle", AsyncMock(return_value=result)):
        helper_result = await run_ingestion_cycle()
    assert helper_result == result
