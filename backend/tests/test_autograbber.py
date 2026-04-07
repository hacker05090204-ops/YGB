from __future__ import annotations

import time

import backend.ingestion.autograbber as autograbber_module
from backend.ingestion.scrapers import ScrapedSample
from backend.training.safetensors_store import SafetensorsFeatureStore


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


def _scraped_sample(
    source: str,
    advisory_id: str,
    cve_id: str,
    description: str,
    *,
    severity: str = "HIGH",
) -> ScrapedSample:
    return ScrapedSample(
        source=source,
        advisory_id=advisory_id,
        url=f"https://example.test/{advisory_id.lower()}",
        title=advisory_id,
        description=description,
        severity=severity,
        cve_id=cve_id,
        cvss_score=8.7,
        tags=("CWE-79",),
        references=(f"https://example.test/reference/{advisory_id.lower()}",),
    )


def _configure_test_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_CVE_DEDUP_STORE_PATH", str(tmp_path / "dedup_store.json"))
    monkeypatch.setenv(
        "YGB_AUTOGRABBER_FEATURE_STORE_PATH",
        str(tmp_path / "features_safetensors"),
    )
    monkeypatch.setattr(
        autograbber_module.feature_extractor,
        "load_vocabulary",
        lambda: [f"token_{index}" for index in range(508)],
    )


class NVDSuccessScraper:
    SOURCE = "nvd"
    last_max_items: int | None = None

    def fetch(self, max_items: int):
        type(self).last_max_items = max_items
        return [
            _scraped_sample(
                "nvd",
                f"NVD-{index}",
                f"CVE-2026-610{index}",
                _long_description(f"Accepted NVD sample {index}."),
            )
            for index in range(max_items)
        ]

    def close(self):
        return None


class CISARejectedScraper:
    SOURCE = "cisa"
    last_max_items: int | None = None

    def fetch(self, max_items: int):
        type(self).last_max_items = max_items
        return [
            _scraped_sample(
                "cisa",
                "CISA-LOW-1",
                "CVE-2026-7101",
                "too short",
                severity="CRITICAL",
            )
        ][:max_items]

    def close(self):
        return None


class FailingScraper:
    SOURCE = "github"

    def fetch(self, max_items: int):
        raise RuntimeError("upstream fetch failure")

    def close(self):
        return None


class LowQualityScraper:
    SOURCE = "nvd"

    def fetch(self, max_items: int):
        return [
            _scraped_sample(
                "nvd",
                "NVD-LOW-1",
                "CVE-2026-6201",
                "too short",
                severity="HIGH",
            )
        ][:max_items]

    def close(self):
        return None


class DuplicateNVDScraper:
    SOURCE = "nvd"

    def fetch(self, max_items: int):
        description = _long_description("Duplicate sample.")
        return [
            _scraped_sample(
                "nvd",
                "NVD-DUP-1",
                "CVE-2026-6201",
                description,
            ),
            _scraped_sample(
                "nvd",
                "NVD-DUP-2",
                "CVE-2026-6202",
                description,
            ),
        ][:max_items]

    def close(self):
        return None


def test_run_cycle_returns_real_counts_and_stores_history(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": NVDSuccessScraper, "cisa": CISARejectedScraper},
    )
    bridge_worker = FakeBridgeWorker()
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: bridge_worker)

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd", "cisa"], max_per_cycle=6)
    )
    result = grabber.run_cycle()
    feature_store = SafetensorsFeatureStore(tmp_path / "features_safetensors")

    assert result.sources_attempted == 2
    assert result.sources_succeeded == 2
    assert NVDSuccessScraper.last_max_items == 3
    assert CISARejectedScraper.last_max_items == 3
    assert result.samples_fetched == 4
    assert result.samples_accepted == 3
    assert result.samples_rejected == 1
    assert result.features_stored == 3
    assert result.bridge_published == 3
    assert result.errors == []
    assert grabber.get_last_cycle_result() == result
    assert grabber.get_all_results() == [result]
    assert bridge_worker.manifest_updates == 1
    assert feature_store.total_samples() == 3


def test_one_source_failure_does_not_stop_other_sources(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"github": FailingScraper, "nvd": NVDSuccessScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["github", "nvd"], max_per_cycle=4)
    )
    result = grabber.run_cycle()

    assert result.sources_attempted == 2
    assert result.sources_succeeded == 1
    assert result.samples_accepted == 2
    assert result.features_stored == 2
    assert result.bridge_published == 2
    assert len(result.errors) == 1
    assert "github" in result.errors[0]


def test_rejected_samples_do_not_enter_bridge_or_store_counts(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": LowQualityScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=10)
    )
    result = grabber.run_cycle()
    feature_store = SafetensorsFeatureStore(tmp_path / "features_safetensors")

    assert result.samples_fetched == 1
    assert result.samples_accepted == 0
    assert result.samples_rejected == 1
    assert result.features_stored == 0
    assert result.bridge_published == 0
    assert feature_store.list_shards() == []


def test_duplicate_samples_are_not_counted_twice(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": DuplicateNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=10)
    )
    result = grabber.run_cycle()

    assert result.samples_fetched == 2
    assert result.samples_accepted == 1
    assert result.samples_rejected == 1
    assert result.features_stored == 1
    assert result.bridge_published == 1


def test_scheduled_loop_starts_and_stops_cleanly(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": NVDSuccessScraper},
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
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": NVDSuccessScraper},
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
