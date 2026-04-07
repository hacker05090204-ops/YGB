from __future__ import annotations

import time

import backend.ingestion.autograbber as autograbber_module
import backend.ingestion.normalizer as normalizer
from backend.ingestion.models import make_sample


def _long_description(seed: str) -> str:
    return (
        f"{seed} "
        "This vulnerability description contains sufficient affected scope, exploit context, "
        "and remediation detail to satisfy the real quality gate without fabricating metadata."
    )


class FakeBridgeWorker:
    def __init__(self, bridge_loaded: bool = True):
        self.bridge_loaded = bridge_loaded
        self.published_batches: list[list[object]] = []
        self.manifest_updates = 0
        self._stats = {"published": 0, "failed": 0, "last_attempt": None}

    @property
    def is_bridge_loaded(self) -> bool:
        return self.bridge_loaded

    def publish_ingestion_samples(self, samples):
        self.published_batches.append(list(samples))
        self._stats["last_attempt"] = "attempted"
        if not self.bridge_loaded:
            self._stats["failed"] += len(samples)
            return 0
        self._stats["published"] += len(samples)
        return len(samples)

    def update_manifest(self):
        self.manifest_updates += 1

    def get_publish_stats(self):
        return dict(self._stats)


class NVDSuccessAdapter:
    SOURCE = "nvd"

    def __init__(self, semaphore, limiter) -> None:
        self.semaphore = semaphore
        self.limiter = limiter

    async def fetch(self):
        return [
            make_sample(
                "nvd",
                _long_description("Accepted NVD sample."),
                "https://example.test/nvd",
                "CVE-2026-6101",
                "HIGH",
                ("kev",),
            )
        ]


class OSVRejectedAdapter:
    SOURCE = "osv"

    def __init__(self, semaphore, limiter) -> None:
        self.semaphore = semaphore
        self.limiter = limiter

    async def fetch(self):
        return [
            make_sample(
                "osv",
                "too short",
                "https://example.test/osv",
                "CVE-2026-6102",
                "MEDIUM",
                (),
            )
        ]


class FailingAdapter:
    SOURCE = "github_advisory"

    def __init__(self, semaphore, limiter) -> None:
        self.semaphore = semaphore
        self.limiter = limiter

    async def fetch(self):
        raise RuntimeError("upstream fetch failure")


class DuplicateNVDAdapter:
    SOURCE = "nvd"

    def __init__(self, semaphore, limiter) -> None:
        self.semaphore = semaphore
        self.limiter = limiter

    async def fetch(self):
        description = _long_description("Duplicate sample.")
        return [
            make_sample(
                "nvd",
                description,
                "https://example.test/dup-1",
                "CVE-2026-6201",
                "HIGH",
                (),
            ),
            make_sample(
                "nvd",
                description,
                "https://example.test/dup-2",
                "CVE-2026-6202",
                "HIGH",
                (),
            ),
        ]


def test_run_cycle_returns_real_counts_and_stores_history(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_CVE_DEDUP_STORE_PATH", str(tmp_path / "autograbber_counts.json"))
    monkeypatch.setattr(normalizer, "NORMALIZED_ROOT", tmp_path / "normalized")
    monkeypatch.setattr(normalizer, "_main_module_supports_spawn", lambda: False)
    monkeypatch.setattr(
        autograbber_module,
        "DEFAULT_ADAPTER_TYPES",
        (NVDSuccessAdapter, OSVRejectedAdapter),
    )
    bridge_worker = FakeBridgeWorker()
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: bridge_worker)

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd", "osv"], max_per_cycle=10)
    )
    result = grabber.run_cycle()

    assert result.sources_attempted == 2
    assert result.sources_succeeded == 2
    assert result.samples_fetched == 2
    assert result.samples_accepted == 1
    assert result.samples_rejected == 1
    assert result.bridge_published == 1
    assert result.errors == []
    assert grabber.get_last_cycle_result() == result
    assert grabber.get_all_results() == [result]
    assert bridge_worker.manifest_updates == 1


def test_one_source_failure_does_not_stop_other_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_CVE_DEDUP_STORE_PATH", str(tmp_path / "autograbber_failure.json"))
    monkeypatch.setattr(normalizer, "NORMALIZED_ROOT", tmp_path / "normalized")
    monkeypatch.setattr(normalizer, "_main_module_supports_spawn", lambda: False)
    monkeypatch.setattr(
        autograbber_module,
        "DEFAULT_ADAPTER_TYPES",
        (FailingAdapter, NVDSuccessAdapter),
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["github_advisory", "nvd"], max_per_cycle=10)
    )
    result = grabber.run_cycle()

    assert result.sources_attempted == 2
    assert result.sources_succeeded == 1
    assert result.samples_accepted == 1
    assert result.bridge_published == 1
    assert len(result.errors) == 1
    assert "github_advisory" in result.errors[0]


def test_rejected_samples_are_not_counted_in_bridge_published(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_CVE_DEDUP_STORE_PATH", str(tmp_path / "autograbber_rejected.json"))
    monkeypatch.setattr(normalizer, "NORMALIZED_ROOT", tmp_path / "normalized")
    monkeypatch.setattr(normalizer, "_main_module_supports_spawn", lambda: False)
    monkeypatch.setattr(
        autograbber_module,
        "DEFAULT_ADAPTER_TYPES",
        (DuplicateNVDAdapter,),
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=10)
    )
    result = grabber.run_cycle()

    assert result.samples_fetched == 2
    assert result.samples_accepted == 1
    assert result.samples_rejected == 1
    assert result.bridge_published == 1


def test_scheduled_loop_starts_and_stops_cleanly(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_CVE_DEDUP_STORE_PATH", str(tmp_path / "autograbber_scheduled.json"))
    monkeypatch.setattr(normalizer, "NORMALIZED_ROOT", tmp_path / "normalized")
    monkeypatch.setattr(normalizer, "_main_module_supports_spawn", lambda: False)
    monkeypatch.setattr(
        autograbber_module,
        "DEFAULT_ADAPTER_TYPES",
        (NVDSuccessAdapter,),
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(
            sources=["nvd"],
            cycle_interval_seconds=1,
            max_per_cycle=10,
        )
    )
    grabber.start_scheduled()

    deadline = time.time() + 2.0
    while time.time() < deadline and not grabber.get_all_results():
        time.sleep(0.05)

    grabber.stop()

    assert grabber.get_last_cycle_result() is not None
    assert grabber._thread is None or not grabber._thread.is_alive()


def test_bridge_backend_not_configured_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_CVE_DEDUP_STORE_PATH", str(tmp_path / "autograbber_bridge_missing.json"))
    monkeypatch.setattr(normalizer, "NORMALIZED_ROOT", tmp_path / "normalized")
    monkeypatch.setattr(normalizer, "_main_module_supports_spawn", lambda: False)
    monkeypatch.setattr(
        autograbber_module,
        "DEFAULT_ADAPTER_TYPES",
        (NVDSuccessAdapter,),
    )
    monkeypatch.setattr(
        autograbber_module,
        "get_bridge_worker",
        lambda: FakeBridgeWorker(bridge_loaded=False),
    )

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=10)
    )

    try:
        grabber.run_cycle()
        raise AssertionError("Expected RealBackendNotConfiguredError to be raised")
    except autograbber_module.RealBackendNotConfiguredError as exc:
        assert "Bridge ingestion backend is not configured" in str(exc)
