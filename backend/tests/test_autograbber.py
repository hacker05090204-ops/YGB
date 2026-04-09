from __future__ import annotations

import json
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
    monkeypatch.setenv(
        "YGB_PREVIOUS_SEVERITIES_PATH",
        str(tmp_path / "previous_severities.json"),
    )
    monkeypatch.setattr(
        autograbber_module.feature_extractor,
        "load_vocabulary",
        lambda: [f"token_{index}" for index in range(508)],
    )


class FakeRLCollector:
    def __init__(self) -> None:
        self.kev_batches: list[list[str]] = []
        self.severity_updates: list[tuple[str, str, str]] = []

    def process_new_cisa_kev_batch(self, cve_ids):
        batch = list(cve_ids)
        self.kev_batches.append(batch)
        return len(batch)

    def process_severity_update(self, cve_id: str, previous_severity: str, new_severity: str):
        self.severity_updates.append((cve_id, previous_severity, new_severity))
        return 1


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


class HallucinationScraper:
    SOURCE = "nvd"

    def fetch(self, max_items: int):
        return [
            _scraped_sample(
                "nvd",
                "NVD-HALL-1",
                "CVE-2026-6301",
                _long_description("[hallucination] marker must trigger purity rejection."),
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


class SeverityUpdateNVDScraper:
    SOURCE = "nvd"

    def fetch(self, max_items: int):
        return [
            _scraped_sample(
                "nvd",
                "NVD-SEVERITY-1",
                "CVE-2026-6100",
                _long_description("NVD severity update sample."),
                severity="HIGH",
            )
        ][:max_items]

    def close(self):
        return None


class KEVCISAScraper:
    SOURCE = "cisa"

    def fetch(self, max_items: int):
        return [
            _scraped_sample(
                "cisa",
                "CISA-KEV-1",
                "CVE-2026-7101",
                _long_description("CISA KEV sample."),
                severity="CRITICAL",
            )
        ][:max_items]

    def close(self):
        return None


class MultiSampleNVDScraper:
    SOURCE = "nvd"
    samples: list[ScrapedSample] = []

    def fetch(self, max_items: int):
        return list(type(self).samples)[:max_items]

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


def test_purity_rejected_samples_increment_purity_counter(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": HallucinationScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=10)
    )
    result = grabber.run_cycle()

    assert result.samples_fetched == 1
    assert result.samples_accepted == 0
    assert result.samples_rejected == 1
    assert result.purity_rejected == 1
    assert result.validator_rejections["purity"] == 1
    assert result.features_stored == 0
    assert result.bridge_published == 0


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
    assert result.validator_rejections["dedup"] == 1
    assert result.features_stored == 1
    assert result.bridge_published == 1


def test_run_cycle_calls_validators_in_requested_order(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-ORDER-1",
            "CVE-2026-7101",
            _long_description("Validator order sample."),
        )
    ]
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": MultiSampleNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=4)
    )
    call_sequence: list[str] = []

    def _wrap_method(method_name: str, label: str) -> None:
        original_method = getattr(grabber, method_name)

        def _wrapped(*args, **kwargs):
            call_sequence.append(label)
            return original_method(*args, **kwargs)

        monkeypatch.setattr(grabber, method_name, _wrapped)

    _wrap_method("_validate_structural_sample", "structural")
    _wrap_method("_enforce_sample_purity", "purity")
    _wrap_method("_score_sample_quality", "quality")
    _wrap_method("_check_duplicate_sample", "dedup")
    _wrap_method("_extract_feature_tensor", "feature_extract")
    _wrap_method("_enforce_feature_tensor_purity", "feature_purity")
    _wrap_method("_write_feature_store", "store_write")

    result = grabber.run_cycle()

    assert result.samples_accepted == 1
    assert call_sequence == [
        "structural",
        "purity",
        "quality",
        "dedup",
        "feature_extract",
        "feature_purity",
        "store_write",
    ]


def test_validator_rejections_are_counted_by_stage_and_aggregate(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    duplicate_description = _long_description("Duplicate validator sample.")
    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-STRUCT-1",
            "",
            _long_description("Structural rejection sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-PURITY-1",
            "CVE-2026-7202",
            _long_description("[hallucination] purity rejection sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-QUALITY-1",
            "CVE-2026-7203",
            _long_description("Quality rejection sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-DUP-ALLOW-1",
            "CVE-2026-7204",
            duplicate_description,
        ),
        _scraped_sample(
            "nvd",
            "NVD-DUP-REJECT-1",
            "CVE-2026-7204",
            duplicate_description,
        ),
        _scraped_sample(
            "nvd",
            "NVD-FEATURE-1",
            "CVE-2026-7205",
            _long_description("Feature rejection sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-ACCEPT-1",
            "CVE-2026-7206",
            _long_description("Accepted validator sample."),
        ),
    ]
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": MultiSampleNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=10)
    )
    original_score_sample_quality = grabber._score_sample_quality
    original_extract_feature_tensor = grabber._extract_feature_tensor

    def _score_sample_quality_wrapper(payload, quality_scorer):
        if payload.get("cve_id") == "CVE-2026-7203":
            return False, "quality_gate_failed", 0.61
        return original_score_sample_quality(payload, quality_scorer)

    def _extract_feature_tensor_wrapper(sample):
        if sample.cve_id == "CVE-2026-7205":
            raise RuntimeError("feature extraction failed for validator test")
        return original_extract_feature_tensor(sample)

    monkeypatch.setattr(grabber, "_score_sample_quality", _score_sample_quality_wrapper)
    monkeypatch.setattr(grabber, "_extract_feature_tensor", _extract_feature_tensor_wrapper)

    result = grabber.run_cycle()
    validator_stats = grabber.get_validator_stats()

    assert result.samples_fetched == 7
    assert result.samples_accepted == 2
    assert result.samples_rejected == 5
    assert result.features_stored == 2
    assert result.bridge_published == 2
    assert result.purity_rejected == 1
    assert result.validator_rejections == {
        "structural": 1,
        "purity": 1,
        "quality": 1,
        "dedup": 1,
        "feature": 1,
    }
    assert validator_stats["cycles_recorded"] == 1
    assert validator_stats["samples_accepted"] == 2
    assert validator_stats["samples_rejected"] == 5
    assert validator_stats["validator_rejections"] == result.validator_rejections


def test_single_feature_failure_only_skips_failed_sample(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-FEATURE-SKIP-1",
            "CVE-2026-7301",
            _long_description("Feature skip sample one."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-FEATURE-SKIP-2",
            "CVE-2026-7302",
            _long_description("Feature skip sample two."),
        ),
    ]
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": MultiSampleNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=4)
    )
    original_extract_feature_tensor = grabber._extract_feature_tensor

    def _extract_feature_tensor_wrapper(sample):
        if sample.cve_id == "CVE-2026-7301":
            raise RuntimeError("feature extraction failed for single-skip test")
        return original_extract_feature_tensor(sample)

    monkeypatch.setattr(grabber, "_extract_feature_tensor", _extract_feature_tensor_wrapper)

    result = grabber.run_cycle()

    assert result.samples_fetched == 2
    assert result.samples_accepted == 1
    assert result.samples_rejected == 1
    assert result.features_stored == 1
    assert result.bridge_published == 1
    assert result.validator_rejections["feature"] == 1
    assert result.errors == []


def test_quality_validator_exception_only_skips_failed_sample(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-QUALITY-FAIL-1",
            "CVE-2026-7351",
            _long_description("Quality exception sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-QUALITY-PASS-1",
            "CVE-2026-7352",
            _long_description("Quality exception control sample."),
        ),
    ]
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": MultiSampleNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=4)
    )
    original_score_sample_quality = grabber._score_sample_quality

    def _score_sample_quality_wrapper(payload, quality_scorer):
        if payload.get("cve_id") == "CVE-2026-7351":
            raise RuntimeError("quality validator failure for test")
        return original_score_sample_quality(payload, quality_scorer)

    monkeypatch.setattr(grabber, "_score_sample_quality", _score_sample_quality_wrapper)

    result = grabber.run_cycle()

    assert result.samples_fetched == 2
    assert result.samples_accepted == 1
    assert result.samples_rejected == 1
    assert result.features_stored == 1
    assert result.bridge_published == 1
    assert result.validator_rejections["quality"] == 1
    assert len(result.errors) == 1
    assert "quality_validation failed" in result.errors[0]


def test_get_validator_stats_aggregates_across_cycles(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": MultiSampleNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=6)
    )

    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-STATS-STRUCT-1",
            "",
            _long_description("Structural stats rejection sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-STATS-ACCEPT-1",
            "CVE-2026-7501",
            _long_description("First accepted stats sample."),
        ),
    ]
    first_result = grabber.run_cycle()

    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-STATS-DUP-1",
            "CVE-2026-7501",
            _long_description("First accepted stats sample."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-STATS-ACCEPT-2",
            "CVE-2026-7502",
            _long_description("Second accepted stats sample."),
        ),
    ]
    second_result = grabber.run_cycle()
    validator_stats = grabber.get_validator_stats()

    assert first_result.validator_rejections == {
        "structural": 1,
        "purity": 0,
        "quality": 0,
        "dedup": 0,
        "feature": 0,
    }
    assert second_result.validator_rejections == {
        "structural": 0,
        "purity": 0,
        "quality": 0,
        "dedup": 1,
        "feature": 0,
    }
    assert validator_stats == {
        "cycles_recorded": 2,
        "last_cycle_id": second_result.cycle_id,
        "samples_accepted": 2,
        "samples_rejected": 2,
        "purity_rejected": 0,
        "validator_rejections": {
            "structural": 1,
            "purity": 0,
            "quality": 0,
            "dedup": 1,
            "feature": 0,
        },
    }


def test_samples_accepted_matches_samples_that_pass_all_validators(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    MultiSampleNVDScraper.samples = [
        _scraped_sample(
            "nvd",
            "NVD-PASS-1",
            "CVE-2026-7401",
            _long_description("Accepted sample one."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-FAIL-1",
            "CVE-2026-7402",
            _long_description("Rejected sample by quality."),
        ),
        _scraped_sample(
            "nvd",
            "NVD-PASS-2",
            "CVE-2026-7403",
            _long_description("Accepted sample two."),
        ),
    ]
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": MultiSampleNVDScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd"], max_per_cycle=6)
    )
    original_score_sample_quality = grabber._score_sample_quality
    original_write_feature_store = grabber._write_feature_store
    passed_all_validators: list[str] = []

    def _score_sample_quality_wrapper(payload, quality_scorer):
        if payload.get("cve_id") == "CVE-2026-7402":
            return False, "quality_gate_failed", 0.62
        return original_score_sample_quality(payload, quality_scorer)

    def _write_feature_store_wrapper(sample, features, labels):
        passed_all_validators.append(sample.cve_id)
        return original_write_feature_store(sample, features, labels)

    monkeypatch.setattr(grabber, "_score_sample_quality", _score_sample_quality_wrapper)
    monkeypatch.setattr(grabber, "_write_feature_store", _write_feature_store_wrapper)

    result = grabber.run_cycle()

    assert sorted(passed_all_validators) == ["CVE-2026-7401", "CVE-2026-7403"]
    assert result.samples_accepted == len(passed_all_validators)
    assert result.bridge_published == len(passed_all_validators)


def test_run_cycle_processes_rl_feedback_and_persists_previous_severities(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)
    previous_severities_path = tmp_path / "previous_severities.json"
    previous_severities_path.write_text(
        json.dumps({"CVE-2026-6100": "LOW"}),
        encoding="utf-8",
    )
    fake_rl_collector = FakeRLCollector()
    monkeypatch.setattr(
        autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {"nvd": SeverityUpdateNVDScraper, "cisa": KEVCISAScraper},
    )
    monkeypatch.setattr(autograbber_module, "get_bridge_worker", lambda: FakeBridgeWorker())
    monkeypatch.setattr(
        autograbber_module,
        "get_rl_collector",
        lambda: fake_rl_collector,
    )

    grabber = autograbber_module.AutoGrabber(
        autograbber_module.AutoGrabberConfig(sources=["nvd", "cisa"], max_per_cycle=4)
    )
    result = grabber.run_cycle()
    persisted_payload = json.loads(previous_severities_path.read_text(encoding="utf-8"))

    assert result.sources_attempted == 2
    assert fake_rl_collector.kev_batches == [["CVE-2026-7101"]]
    assert fake_rl_collector.severity_updates == [("CVE-2026-6100", "LOW", "HIGH")]
    assert persisted_payload["CVE-2026-6100"] == "HIGH"


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
