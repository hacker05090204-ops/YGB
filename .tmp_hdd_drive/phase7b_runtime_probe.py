import json
import logging
import os
import tempfile
import time
import traceback
from pathlib import Path

import backend.ingestion.autograbber as ag
from backend.cve.bridge_ingestion_worker import get_bridge_worker as real_get_bridge_worker

logging.basicConfig(level=logging.ERROR)


class RecordingBridgeWorker:
    def __init__(self):
        self.published = 0
        self.failed = 0
        self.manifest_updates = 0

    @property
    def is_bridge_loaded(self):
        return True

    def publish_ingestion_samples(self, samples):
        count = len(samples)
        self.published += count
        return count

    def update_manifest(self):
        self.manifest_updates += 1

    def get_publish_stats(self):
        return {
            "published": self.published,
            "failed": self.failed,
            "last_attempt": "stubbed",
        }


def prepare_env(prefix: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    os.environ["YGB_CVE_DEDUP_STORE_PATH"] = str(root / "dedup_store.json")
    os.environ["YGB_AUTOGRABBER_FEATURE_STORE_PATH"] = str(root / "features_safetensors")
    os.environ["YGB_PREVIOUS_SEVERITIES_PATH"] = str(root / "previous_severities.json")
    return root


def summarize_result(result):
    if result is None:
        return None
    return {
        "cycle_id": result.cycle_id,
        "sources_attempted": result.sources_attempted,
        "sources_succeeded": result.sources_succeeded,
        "samples_fetched": result.samples_fetched,
        "samples_accepted": result.samples_accepted,
        "samples_rejected": result.samples_rejected,
        "features_stored": result.features_stored,
        "bridge_published": result.bridge_published,
        "purity_rejected": result.purity_rejected,
        "validator_rejections": result.validator_rejections,
        "errors": result.errors,
    }


def run_cycle_probe(root: Path, *, max_per_cycle: int = 50):
    bridge = RecordingBridgeWorker()
    ag.get_bridge_worker = lambda: bridge
    grabber = ag.AutoGrabber(ag.AutoGrabberConfig(max_per_cycle=max_per_cycle))
    source_fetch = {}
    accepted_by_source = {}
    accepted_records = []
    original_fetch = grabber._fetch_scraper_results
    original_write = grabber._write_feature_store

    def wrapped_fetch(scraper_type, max_items):
        started = time.perf_counter()
        source, fetch_result = original_fetch(scraper_type, max_items)
        elapsed = round(time.perf_counter() - started, 3)
        if isinstance(fetch_result, Exception):
            source_fetch[source] = {
                "fetch_success": False,
                "fetched": None,
                "elapsed_seconds": elapsed,
                "error": f"{type(fetch_result).__name__}: {fetch_result}",
            }
        else:
            source_fetch[source] = {
                "fetch_success": True,
                "fetched": len(fetch_result),
                "elapsed_seconds": elapsed,
                "error": None,
            }
        return source, fetch_result

    def wrapped_write(sample, features, labels):
        original_write(sample, features, labels)
        accepted_by_source[sample.source] = accepted_by_source.get(sample.source, 0) + 1
        accepted_records.append(
            {
                "source": sample.source,
                "cve_id": sample.cve_id,
                "severity": sample.severity,
                "sha256_hash": sample.sha256_hash,
            }
        )

    grabber._fetch_scraper_results = wrapped_fetch
    grabber._write_feature_store = wrapped_write

    result = None
    cycle_error = None
    started = time.perf_counter()
    try:
        result = grabber.run_cycle()
    except Exception as exc:
        cycle_error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    duration = round(time.perf_counter() - started, 3)

    feature_store_root = root / "features_safetensors"
    shard_names = sorted(path.name for path in feature_store_root.rglob("*.safetensors"))

    return {
        "root": str(root),
        "sources": list(grabber.config.sources),
        "per_source_limit": grabber.config.max_per_cycle // len(grabber._scraper_types),
        "duration_seconds": duration,
        "cycle_error": cycle_error,
        "source_fetch": source_fetch,
        "sources_with_samples": sum(1 for value in source_fetch.values() if (value.get("fetched") or 0) > 0),
        "accepted_by_source": accepted_by_source,
        "accepted_records": accepted_records,
        "accepted_cves": [record["cve_id"] for record in accepted_records if record["cve_id"]],
        "bridge_stub": bridge.get_publish_stats(),
        "bridge_manifest_updates": bridge.manifest_updates,
        "feature_store_shard_count": len(shard_names),
        "feature_store_shards": shard_names,
        "accepted_samples_purity_aligned": result is not None and result.samples_accepted == len(accepted_records) == len(shard_names) == bridge.published,
        "result": summarize_result(result),
    }


def run_stress_probe(root: Path, *, cycles: int = 3, max_per_cycle: int = 50):
    bridge = RecordingBridgeWorker()
    ag.get_bridge_worker = lambda: bridge
    grabber = ag.AutoGrabber(ag.AutoGrabberConfig(max_per_cycle=max_per_cycle))
    runs = []
    all_accepted_cves = []
    all_accepted_hashes = []
    base_fetch = grabber._fetch_scraper_results
    base_write = grabber._write_feature_store

    for index in range(cycles):
        source_fetch = {}
        accepted_records = []

        def wrapped_fetch(scraper_type, max_items):
            started = time.perf_counter()
            source, fetch_result = base_fetch(scraper_type, max_items)
            elapsed = round(time.perf_counter() - started, 3)
            if isinstance(fetch_result, Exception):
                source_fetch[source] = {
                    "fetch_success": False,
                    "fetched": None,
                    "elapsed_seconds": elapsed,
                    "error": f"{type(fetch_result).__name__}: {fetch_result}",
                }
            else:
                source_fetch[source] = {
                    "fetch_success": True,
                    "fetched": len(fetch_result),
                    "elapsed_seconds": elapsed,
                    "error": None,
                }
            return source, fetch_result

        def wrapped_write(sample, features, labels):
            base_write(sample, features, labels)
            accepted_records.append(
                {
                    "source": sample.source,
                    "cve_id": sample.cve_id,
                    "severity": sample.severity,
                    "sha256_hash": sample.sha256_hash,
                }
            )

        grabber._fetch_scraper_results = wrapped_fetch
        grabber._write_feature_store = wrapped_write

        result = None
        cycle_error = None
        started = time.perf_counter()
        try:
            result = grabber.run_cycle()
        except Exception as exc:
            cycle_error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        duration = round(time.perf_counter() - started, 3)

        accepted_cves = [record["cve_id"] for record in accepted_records if record["cve_id"]]
        accepted_hashes = [record["sha256_hash"] for record in accepted_records if record["sha256_hash"]]
        all_accepted_cves.extend(accepted_cves)
        all_accepted_hashes.extend(accepted_hashes)

        runs.append(
            {
                "cycle_number": index + 1,
                "duration_seconds": duration,
                "cycle_error": cycle_error,
                "source_fetch": source_fetch,
                "accepted_records": accepted_records,
                "accepted_cves": accepted_cves,
                "result": summarize_result(result),
            }
        )

    duplicate_cves = sorted({value for value in all_accepted_cves if all_accepted_cves.count(value) > 1})
    duplicate_hashes = sorted({value for value in all_accepted_hashes if all_accepted_hashes.count(value) > 1})

    return {
        "root": str(root),
        "cycles": runs,
        "duplicate_cves_across_accepted_cycles": duplicate_cves,
        "duplicate_hashes_across_accepted_cycles": duplicate_hashes,
        "dedup_prevented_duplicate_acceptance": not duplicate_cves and not duplicate_hashes,
        "bridge_stub": bridge.get_publish_stats(),
        "bridge_manifest_updates": bridge.manifest_updates,
    }


def main() -> None:
    try:
        live_bridge = real_get_bridge_worker()
        real_bridge = {
            "loaded": bool(live_bridge.is_bridge_loaded),
            "status": live_bridge.get_status(),
        }
    except Exception as exc:
        real_bridge = {
            "loaded": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    integration_root = prepare_env("phase7b_integration_")
    integration = run_cycle_probe(integration_root, max_per_cycle=50)

    benchmark_root = prepare_env("phase7b_benchmark_")
    benchmark = run_cycle_probe(benchmark_root, max_per_cycle=50)
    benchmark["under_120_seconds"] = benchmark["duration_seconds"] < 120.0

    stress_root = prepare_env("phase7b_stress_")
    stress = run_stress_probe(stress_root, cycles=3, max_per_cycle=50)

    payload = {
        "bridge_strategy": "real_network_and_real_autograbber_path_with_in_process_bridge_stub_only",
        "real_bridge": real_bridge,
        "integration": integration,
        "benchmark": benchmark,
        "stress": stress,
    }

    out_path = Path(".tmp_hdd_drive") / "phase7b_runtime_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print("PHASE7B_RUNTIME_RESULTS_PATH=" + str(out_path))
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
