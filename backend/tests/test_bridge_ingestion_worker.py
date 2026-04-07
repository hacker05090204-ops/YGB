from __future__ import annotations

import logging
from types import SimpleNamespace

import backend.cve.cve_pipeline as pipeline_mod
import backend.cve.bridge_ingestion_worker as worker_module


class FakeBridgeState:
    def __init__(self, samples=None):
        self._samples = list(samples or [])
        self.appended = []
        self.recorded_batches = []
        self.recorded_drops = []
        self.recorded_dedup = []

    def get_counts(self):
        return {"bridge_count": 0, "bridge_verified_count": 0}

    def read_samples(self, max_samples: int = 0):
        return list(self._samples)

    def append_sample(self, sample):
        self.appended.append(sample)

    def record_ingest_batch(self, new_ingested: int, new_verified: int):
        self.recorded_batches.append((new_ingested, new_verified))

    def record_drop(self, count: int = 1):
        self.recorded_drops.append(count)

    def record_dedup(self, count: int = 1):
        self.recorded_dedup.append(count)

    def flush_samples(self):
        return None

    def set_counts(self, **kwargs):
        return None


class FakeBridgeLib:
    def __init__(self, return_code: int = 0):
        self.return_code = return_code
        self.count = 0
        self.verified = 0

    def bridge_ingest_sample(self, *args):
        if self.return_code == 0:
            self.count += 1
            self.verified += 1
        return self.return_code

    def bridge_get_count(self):
        return self.count

    def bridge_get_verified_count(self):
        return self.verified


def make_record(cve_id: str, description: str, source: str = "NVD API v2"):
    return SimpleNamespace(
        cve_id=cve_id,
        description=description,
        severity="HIGH",
        cvss_score=8.1,
        promotion_status="RESEARCH_PENDING",
        affected_products=["vendor/product"],
        provenance=[SimpleNamespace(source=source)],
    )


def build_worker(monkeypatch, state: FakeBridgeState, lib: FakeBridgeLib):
    monkeypatch.setattr(worker_module, "_worker", None)
    monkeypatch.setattr(
        worker_module.BridgeIngestionWorker,
        "_load_bridge",
        lambda self: setattr(self, "_lib", lib),
    )
    monkeypatch.setattr("backend.bridge.bridge_state.get_bridge_state", lambda: state)
    return worker_module.BridgeIngestionWorker()


def _long_description(seed: str) -> str:
    return (
        f"{seed} "
        "This description includes sufficient verified context, impact, and remediation detail "
        "to satisfy pipeline quality validation before bridge ingestion occurs."
    )


def test_stream_ingest_restores_persisted_idempotency(monkeypatch):
    state = FakeBridgeState(
        samples=[
            {
                "endpoint": "CVE-2024-1",
                "exploit_vector": "Persisted description",
                "idempotency_key": "persisted-key",
                "ingestion_batch_id": "CBI-000001",
            }
        ]
    )
    worker = build_worker(monkeypatch, state, FakeBridgeLib())
    pipeline = SimpleNamespace(
        _records={"CVE-2024-1": make_record("CVE-2024-1", "Persisted description")}
    )

    ingested = worker.stream_ingest_new(pipeline)

    assert ingested == 0
    assert state.recorded_dedup == [1]
    assert worker.get_status()["idempotency_keys_cached"] >= 1
    assert worker.get_status()["last_batch"]["deduped"] == 1


def test_stream_ingest_tracks_batch_metadata(monkeypatch):
    state = FakeBridgeState()
    worker = build_worker(monkeypatch, state, FakeBridgeLib())
    pipeline = SimpleNamespace(
        _records={"CVE-2024-2": make_record("CVE-2024-2", "Fresh description")}
    )

    ingested = worker.stream_ingest_new(pipeline)

    assert ingested == 1
    assert state.recorded_batches == [(1, 1)]
    assert len(state.appended) == 1
    persisted = state.appended[0]
    assert persisted["idempotency_key"]
    assert persisted["ingestion_batch_id"].startswith("CBI-")
    status = worker.get_status()
    assert status["last_batch"]["mode"] == "stream"
    assert status["last_batch"]["ingested"] == 1


def test_low_quality_sample_does_not_reach_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "YGB_CVE_DEDUP_STORE_PATH",
        str(tmp_path / "bridge_quality_dedup_store.json"),
    )
    state = FakeBridgeState()
    worker = build_worker(monkeypatch, state, FakeBridgeLib())
    pipeline = pipeline_mod.CVEPipeline()

    record, result = pipeline.ingest_record(
        cve_id="CVE-2026-5001",
        title="Rejected by quality gate",
        description="short desc",
        severity="HIGH",
        cvss_score=8.0,
        affected_products=["bridge-app"],
        references=[],
        is_exploited=False,
        source_id="nvd",
    )
    ingested = worker.stream_ingest_new(pipeline)

    assert record is None
    assert result == pipeline_mod.IngestResult.REJECTED
    assert ingested == 0
    assert state.appended == []


def test_high_quality_sample_reaches_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "YGB_CVE_DEDUP_STORE_PATH",
        str(tmp_path / "bridge_accept_dedup_store.json"),
    )
    state = FakeBridgeState()
    worker = build_worker(monkeypatch, state, FakeBridgeLib())
    pipeline = pipeline_mod.CVEPipeline()

    record, result = pipeline.ingest_record(
        cve_id="CVE-2026-5002",
        title="Accepted by quality gate",
        description=_long_description("Accepted bridge sample."),
        severity="HIGH",
        cvss_score=8.7,
        affected_products=["bridge-app"],
        references=["https://example.test/accepted"],
        is_exploited=True,
        source_id="nvd",
    )
    ingested = worker.stream_ingest_new(pipeline)

    assert record is not None
    assert result == pipeline_mod.IngestResult.NEW
    assert ingested == 1
    assert len(state.appended) == 1
    assert state.appended[0]["endpoint"] == "CVE-2026-5002"


def test_bridge_failure_logged_at_critical(monkeypatch, caplog):
    state = FakeBridgeState()
    worker = build_worker(monkeypatch, state, None)
    pipeline = SimpleNamespace(
        _records={"CVE-2024-9": make_record("CVE-2024-9", _long_description("Unavailable bridge."))}
    )

    with caplog.at_level(logging.CRITICAL):
        ingested = worker.stream_ingest_new(pipeline)

    assert ingested == 0
    assert worker.get_publish_stats()["published"] == 0
    assert worker.get_publish_stats()["failed"] == 1
    assert any(record.levelno == logging.CRITICAL for record in caplog.records)


def test_publish_stats_are_accurate(monkeypatch, caplog):
    state = FakeBridgeState()
    worker = build_worker(monkeypatch, state, FakeBridgeLib())
    first_pipeline = SimpleNamespace(
        _records={"CVE-2024-10": make_record("CVE-2024-10", _long_description("Published sample."))}
    )

    first_ingested = worker.stream_ingest_new(first_pipeline)
    worker._lib = FakeBridgeLib(return_code=-7)
    second_pipeline = SimpleNamespace(
        _records={"CVE-2024-11": make_record("CVE-2024-11", _long_description("Failed sample."))}
    )

    with caplog.at_level(logging.CRITICAL):
        second_ingested = worker.stream_ingest_new(second_pipeline)

    stats = worker.get_publish_stats()
    assert first_ingested == 1
    assert second_ingested == 0
    assert stats["published"] == 1
    assert stats["failed"] == 1
    assert stats["last_attempt"] is not None
    assert any(record.levelno == logging.CRITICAL for record in caplog.records)
