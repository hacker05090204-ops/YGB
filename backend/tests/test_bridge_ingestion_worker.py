from __future__ import annotations

from types import SimpleNamespace

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
