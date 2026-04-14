from __future__ import annotations

import torch

import backend.ingestion.parallel_autograbber as parallel_autograbber_module
from backend.ingestion.scrapers import ScrapedSample
from backend.training.safetensors_store import SafetensorsFeatureStore


def _long_description(seed: str) -> str:
    return (
        f"{seed} "
        "This vulnerability description contains sufficient affected scope, exploit context, "
        "and remediation detail to satisfy the real quality and purity gates without fabricating metadata."
    )


class FakeBridgeWorker:
    def __init__(self, bridge_loaded: bool = True):
        self.bridge_loaded = bridge_loaded
        self.published_batches: list[list[object]] = []
        self.manifest_updates = 0

    @property
    def is_bridge_loaded(self) -> bool:
        return self.bridge_loaded

    def publish_ingestion_samples(self, samples):
        self.published_batches.append(list(samples))
        return len(samples)

    def update_manifest(self):
        self.manifest_updates += 1


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
        tags=("CWE-89",),
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


class SQLiNVDScraper:
    SOURCE = "nvd"

    def fetch(self, max_items: int):
        return [
            _scraped_sample(
                "nvd",
                "NVD-SQLI-1",
                "CVE-2026-9901",
                _long_description(
                    "Union-based SQL injection in the login endpoint allows authentication bypass."
                ),
            )
        ][:max_items]

    def close(self):
        return None


class LowQualityCISAScraper:
    SOURCE = "cisa"

    def fetch(self, max_items: int):
        return [
            _scraped_sample(
                "cisa",
                "CISA-LOW-1",
                "CVE-2026-9902",
                "too short",
                severity="CRITICAL",
            )
        ][:max_items]

    def close(self):
        return None


class FailingGitHubScraper:
    SOURCE = "github"

    def fetch(self, max_items: int):
        raise RuntimeError("upstream fetch failure")

    def close(self):
        return None


def test_route_vulnerability_text_to_expert_routes_sql_injection_to_expert_1():
    route = parallel_autograbber_module.route_vulnerability_text_to_expert(
        "Union-based SQL injection in login endpoint allows authentication bypass and data extraction."
    )

    assert route.expert_id == 1
    assert route.expert_label == "database_injection"
    assert "sql injection" in route.reasons


def test_phase8_smoke_gate_routes_sql_injection_and_initializes(monkeypatch, tmp_path):
    _configure_test_environment(monkeypatch, tmp_path)

    smoke_result = parallel_autograbber_module.phase8_smoke_gate(
        parallel_autograbber_module.ParallelAutoGrabberConfig(
            sources=["nvd"],
            max_per_cycle=1,
            max_workers=1,
        )
    )

    assert smoke_result["sql_injection_expert_id"] == 1
    assert smoke_result["initialized"] is True


def test_parallel_autograbber_run_cycle_processes_sources_and_observes_failures(
    monkeypatch,
    tmp_path,
):
    _configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        parallel_autograbber_module,
        "SCRAPER_TYPES_BY_SOURCE",
        {
            "nvd": SQLiNVDScraper,
            "github": FailingGitHubScraper,
            "cisa": LowQualityCISAScraper,
        },
    )
    bridge_worker = FakeBridgeWorker()
    monkeypatch.setattr(
        parallel_autograbber_module,
        "get_bridge_worker",
        lambda: bridge_worker,
    )

    grabber = parallel_autograbber_module.ParallelAutoGrabber(
        parallel_autograbber_module.ParallelAutoGrabberConfig(
            sources=["nvd", "github", "cisa"],
            max_per_cycle=6,
            max_workers=3,
        )
    )
    monkeypatch.setattr(
        grabber,
        "_extract_feature_tensor",
        lambda sample: torch.linspace(0.01, 5.12, steps=512, dtype=torch.float32),
    )
    monkeypatch.setattr(grabber, "_record_rl_feedback_prediction", lambda *args, **kwargs: None)
    monkeypatch.setattr(grabber, "_process_cisa_rl_feedback", lambda *args, **kwargs: None)
    monkeypatch.setattr(grabber, "_process_nvd_severity_feedback", lambda *args, **kwargs: None)
    monkeypatch.setattr(grabber, "_run_adaptive_learning_hook", lambda *args, **kwargs: None)

    result = grabber.run_cycle()
    feature_store = SafetensorsFeatureStore(tmp_path / "features_safetensors")

    assert result.parallel_fetch_used is True
    assert result.fetch_worker_count == 3
    assert result.sources_attempted == 3
    assert result.sources_succeeded == 2
    assert result.samples_fetched == 2
    assert result.samples_accepted == 1
    assert result.samples_rejected == 1
    assert result.features_stored == 1
    assert result.bridge_published == 1
    assert len(result.errors) == 1
    assert "github" in result.source_failures
    assert result.expert_route_counts[1] == 1
    assert result.expert_routes["CVE-2026-9901"] == 1
    assert any(failure.validator_key == "purity" for failure in result.validation_failures)
    assert bridge_worker.manifest_updates == 1
    assert feature_store.total_samples() == 1
