"""Live benchmark runner for the Phase 13 startup path.

Runs the seven benchmark checks relevant to the current live benchmark flow,
using [`.env.benchmark`](../.env.benchmark) for API host/port defaults and the
existing PowerShell startup path in [`start_full_stack.ps1`](../start_full_stack.ps1).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


RESULTS: dict[str, dict[str, Any]] = {}
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env.benchmark"
DEFAULT_BENCHMARK_RESULTS_PATH = PROJECT_ROOT / "BENCHMARK_RESULTS.json"


class BenchmarkFailure(RuntimeError):
    """Raised when a benchmark check completes but fails its required assertions."""


def _load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Benchmark environment file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            separator = line.find("=")
            if separator <= 0:
                continue
            key = line[:separator].strip()
            value = line[separator + 1 :].strip()
            if key and key not in os.environ:
                os.environ[key] = value


def _connect_host(host: str) -> str:
    normalized = str(host or "").strip() or "127.0.0.1"
    if normalized in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return normalized


def _default_base_url() -> str:
    host = _connect_host(os.getenv("API_HOST", "127.0.0.1"))
    port = int(os.getenv("API_PORT", "8000"))
    return f"http://{host}:{port}"


def _json_request(url: str, *, timeout_seconds: float) -> tuple[int, dict[str, Any], float]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "YGB-Full-Benchmark/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw_body = response.read().decode("utf-8")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise BenchmarkFailure(f"{url} returned non-JSON content") from exc
        if not isinstance(parsed, dict):
            raise BenchmarkFailure(f"{url} returned a non-object JSON payload")
        return int(response.status), parsed, round(elapsed_ms, 2)


def _wait_for_live_server(
    base_url: str,
    *,
    boot_timeout_seconds: float,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(1.0, float(boot_timeout_seconds))
    last_error = "unknown"
    healthz_url = f"{base_url.rstrip('/')}/healthz"

    while time.monotonic() < deadline:
        try:
            status_code, payload, elapsed_ms = _json_request(
                healthz_url,
                timeout_seconds=request_timeout_seconds,
            )
            if status_code != 200:
                raise BenchmarkFailure(f"{healthz_url} returned HTTP {status_code}")
            if str(payload.get("status", "")).lower() != "alive":
                raise BenchmarkFailure(
                    f"{healthz_url} returned unexpected status payload: {payload!r}"
                )
            return {
                "url": healthz_url,
                "status_code": status_code,
                "response_time_ms": elapsed_ms,
                "payload": payload,
            }
        except Exception as exc:  # noqa: BLE001 - surfaced via last_error and final exception
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1.0)

    raise BenchmarkFailure(
        f"Live server did not become healthy at {healthz_url} within {boot_timeout_seconds:.0f}s: {last_error}"
    )


def _run_check(name: str, func: Callable[[], dict[str, Any]]) -> bool:
    print(f"\n{'=' * 70}")
    print(f"BENCHMARK: {name}")
    print("=" * 70)
    started = time.perf_counter()

    try:
        result = func()
        elapsed_s = round(time.perf_counter() - started, 3)
        RESULTS[name] = {
            "status": "PASS",
            "elapsed_s": elapsed_s,
            "result": result,
        }
        print(f"  STATUS: PASS ({elapsed_s:.3f}s)")
        print(json.dumps(result, indent=2, default=str))
        return True
    except Exception as exc:  # noqa: BLE001 - benchmark failures must be recorded explicitly
        elapsed_s = round(time.perf_counter() - started, 3)
        tb = traceback.format_exc()
        RESULTS[name] = {
            "status": "FAIL",
            "elapsed_s": elapsed_s,
            "error": str(exc),
            "traceback": tb,
        }
        print(f"  STATUS: FAIL ({elapsed_s:.3f}s)")
        print(f"  ERROR: {exc}")
        print(tb)
        return False


def benchmark_authority_lock() -> dict[str, Any]:
    from backend.governance.authority_lock import AuthorityLock

    verification = AuthorityLock.verify_all_locked()
    lock_names = [
        "AUTO_SUBMIT",
        "AUTHORITY_UNLOCK",
        "COMPANY_TARGETING",
        "MID_TRAINING_MERGE",
        "VOICE_HUNT_TRIGGER",
        "VOICE_SUBMIT",
        "AUTO_NEGOTIATE",
        "SKIP_CERTIFICATION",
        "CROSS_FIELD_DATA",
        "TIME_FORCED_COMPLETION",
        "PARALLEL_FIELD_TRAINING",
    ]
    lock_states = {name: getattr(AuthorityLock, name) for name in lock_names}

    if verification.get("total_locks") != len(lock_names):
        raise BenchmarkFailure(
            f"AuthorityLock total_locks mismatch: expected {len(lock_names)}, got {verification.get('total_locks')}"
        )
    if not verification.get("all_locked"):
        raise BenchmarkFailure(f"AuthorityLock reported violations: {verification}")
    if any(value is not False for value in lock_states.values()):
        raise BenchmarkFailure(f"AuthorityLock class attributes are not all False: {lock_states}")

    return {
        "verify_result": verification,
        "lock_states": lock_states,
        "all_false": True,
        "violations_found": verification.get("violations", []),
        "total_locks": verification.get("total_locks"),
    }


def benchmark_cve_ingestion() -> dict[str, Any]:
    from backend.ingestion.normalizer import QualityRejectionLog, SampleQualityScorer

    scorer = SampleQualityScorer(rejection_log=QualityRejectionLog(max_entries=100))
    test_samples = [
        {
            "source": "nvd",
            "cve_id": "CVE-2024-0001",
            "description": "A critical vulnerability in the authentication module allows remote attackers to bypass security controls through a specially crafted HTTP request that exploits improper input validation in the login endpoint.",
            "severity": "CRITICAL",
            "tags": ["authentication", "remote-code-execution", "cvss-9.8"],
            "token_count": 150,
            "is_exploited": True,
        },
        {
            "source": "nvd",
            "cve_id": "CVE-2024-0002",
            "description": "Buffer overflow vulnerability.",
            "severity": "HIGH",
            "tags": [],
            "token_count": 5,
        },
        {
            "source": "nvd",
            "description": "A critical vulnerability allows remote attackers to execute arbitrary code through improper input validation in the authentication module.",
            "severity": "CRITICAL",
            "tags": ["remote-code-execution"],
            "token_count": 100,
        },
        {
            "source": "unknown",
            "cve_id": "CVE-2024-0003",
            "description": "Something bad might happen maybe.",
            "severity": "UNKNOWN",
            "tags": [],
            "token_count": 10,
        },
        {
            "source": "cisa",
            "cve_id": "CVE-2024-0004",
            "description": "A critical vulnerability in the Apache Log4j library allows remote attackers to execute arbitrary code through JNDI lookup injection in logged user-controlled data with insufficient sanitization of specially crafted payloads.",
            "severity": "CRITICAL",
            "tags": ["log4j", "rce", "cisa-known-exploited"],
            "token_count": 200,
            "is_exploited": True,
            "has_public_exploit": True,
        },
    ]
    expected_results = [True, False, False, False, True]

    details: list[dict[str, Any]] = []
    passed = 0
    for sample, expected in zip(test_samples, expected_results):
        acceptable = scorer.is_acceptable(sample)
        is_correct = acceptable == expected
        if is_correct:
            passed += 1
        details.append(
            {
                "cve_id": sample.get("cve_id", "N/A"),
                "acceptable": acceptable,
                "expected": expected,
                "correct": is_correct,
                "score": scorer.last_score,
                "reason": scorer.last_rejection_reason,
            }
        )

    if passed != len(test_samples):
        raise BenchmarkFailure(f"CVE ingestion accuracy check failed: {passed}/{len(test_samples)} correct")

    return {
        "total": len(test_samples),
        "passed": passed,
        "accuracy": passed / len(test_samples),
        "details": details,
        "quality_stats": scorer.get_quality_stats(),
    }


def benchmark_moe_smoke() -> dict[str, Any]:
    from impl_v1.phase49.moe import EXPERT_FIELDS, create_moe_config_small, run_smoke_test

    config = create_moe_config_small()
    smoke_result = run_smoke_test()
    if not isinstance(smoke_result, dict):
        raise BenchmarkFailure(f"run_smoke_test() returned non-dict result: {type(smoke_result).__name__}")
    if len(EXPERT_FIELDS) != int(config.n_experts):
        raise BenchmarkFailure(
            f"MoE expert field count mismatch: len(EXPERT_FIELDS)={len(EXPERT_FIELDS)} config.n_experts={config.n_experts}"
        )
    if int(smoke_result.get("total_params", 0) or 0) <= 0:
        raise BenchmarkFailure(f"MoE smoke test reported invalid total_params: {smoke_result}")
    if int(smoke_result.get("expert_budget", 0) or 0) <= 0:
        raise BenchmarkFailure(f"MoE smoke test reported invalid expert_budget: {smoke_result}")

    return {
        "expert_fields_count": len(EXPERT_FIELDS),
        "config_n_experts": int(config.n_experts),
        **smoke_result,
    }


def benchmark_expert_queue() -> dict[str, Any]:
    from impl_v1.phase49.moe import EXPERT_FIELDS
    from scripts.expert_task_queue import (
        DEFAULT_STATUS_PATH,
        ExpertTaskQueue,
        STATUS_AVAILABLE,
        STATUS_CLAIMED,
        STATUS_COMPLETED,
        STATUS_FAILED,
    )

    queue = ExpertTaskQueue(status_path=DEFAULT_STATUS_PATH)
    if not Path(DEFAULT_STATUS_PATH).exists():
        queue.initialize_status_file()

    state = queue.load_status()
    status_text = queue.render_status()
    experts = state.get("experts", [])
    if len(experts) != len(EXPERT_FIELDS):
        raise BenchmarkFailure(
            f"Expert queue count mismatch: expected {len(EXPERT_FIELDS)}, got {len(experts)}"
        )

    status_counts = {
        STATUS_AVAILABLE: 0,
        STATUS_CLAIMED: 0,
        STATUS_COMPLETED: 0,
        STATUS_FAILED: 0,
    }
    for expert in experts:
        status = str(expert.get("status", STATUS_AVAILABLE))
        if status not in status_counts:
            raise BenchmarkFailure(f"Unexpected expert queue status value: {status}")
        status_counts[status] += 1

    return {
        "schema_version": state.get("schema_version"),
        "updated_at": state.get("updated_at"),
        "total_experts": len(experts),
        "status_counts": status_counts,
        "status_text_preview": status_text[:500],
    }


def benchmark_feature_dimension() -> dict[str, Any]:
    from backend.training.safetensors_store import FEATURE_DIM, SafetensorsFeatureStore

    store = SafetensorsFeatureStore(root=PROJECT_ROOT / "training" / "features_safetensors")
    shards = store.list_shards()
    if not shards:
        raise BenchmarkFailure("No feature shards found under training/features_safetensors")

    shard_details: list[dict[str, Any]] = []
    for shard_name in shards[:5]:
        shard = store.read(shard_name)
        feature_dim = int(shard.features.shape[1])
        matches = feature_dim == int(store.feature_dim)
        if not matches:
            raise BenchmarkFailure(
                f"Feature dimension mismatch for shard {shard_name}: expected {store.feature_dim}, got {feature_dim}"
            )
        shard_details.append(
            {
                "name": shard_name,
                "shape": list(shard.features.shape),
                "feature_dim": feature_dim,
                "expected_dim": int(store.feature_dim),
                "matches": matches,
            }
        )

    return {
        "configured_feature_dim": int(store.feature_dim),
        "expected_from_constant": int(FEATURE_DIM),
        "shards_found": len(shards),
        "shards_checked": len(shard_details),
        "verified_count": len(shard_details),
        "all_dimensions_match": True,
        "shard_details": shard_details[:3],
    }


def benchmark_live_server(base_url: str, *, boot_timeout_seconds: float, request_timeout_seconds: float) -> dict[str, Any]:
    result = _wait_for_live_server(
        base_url,
        boot_timeout_seconds=boot_timeout_seconds,
        request_timeout_seconds=request_timeout_seconds,
    )
    return {
        "server_available": True,
        "url": result["url"],
        "status_code": result["status_code"],
        "response_time_ms": result["response_time_ms"],
        "response": result["payload"],
    }


def benchmark_concurrent_stress(
    base_url: str,
    *,
    request_count: int,
    max_workers: int,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    healthz_url = f"{base_url.rstrip('/')}/healthz"

    def make_request(request_id: int) -> dict[str, Any]:
        started = time.perf_counter()
        request = urllib.request.Request(
            healthz_url,
            headers={"User-Agent": f"YGB-Concurrent-Stress/{request_id}"},
        )
        with urllib.request.urlopen(request, timeout=request_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if int(response.status) != 200:
                raise BenchmarkFailure(f"Request {request_id} returned HTTP {response.status}")
            if str(payload.get("status", "")).lower() != "alive":
                raise BenchmarkFailure(
                    f"Request {request_id} returned unexpected payload: {payload!r}"
                )
            return {
                "id": request_id,
                "status": int(response.status),
                "time_ms": round(elapsed_ms, 2),
                "success": True,
            }

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(make_request, request_id) for request_id in range(request_count)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    total_time = time.perf_counter() - started
    if len(results) != request_count:
        raise BenchmarkFailure(
            f"Concurrent stress test completed {len(results)} requests, expected {request_count}"
        )

    response_times = [float(item["time_ms"]) for item in results]
    return {
        "server_available": True,
        "url": healthz_url,
        "total_requests": request_count,
        "successful": len(results),
        "failed": 0,
        "total_time_s": round(total_time, 3),
        "avg_time_ms": round(sum(response_times) / len(response_times), 2),
        "min_time_ms": round(min(response_times), 2),
        "max_time_ms": round(max(response_times), 2),
        "requests_per_second": round(request_count / total_time, 2) if total_time > 0 else None,
    }


def _write_results(path: Path) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(RESULTS, handle, indent=2, default=str)
        handle.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 13 live benchmark suite")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="Path to .env.benchmark")
    parser.add_argument("--base-url", default="", help="Explicit API base URL, for example http://127.0.0.1:8000")
    parser.add_argument("--stress-requests", type=int, default=20, help="Concurrent stress request count")
    parser.add_argument("--stress-workers", type=int, default=10, help="Concurrent stress worker count")
    parser.add_argument("--boot-timeout-seconds", type=float, default=60.0, help="Maximum wait for /healthz to become healthy")
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0, help="Per-request timeout for live HTTP checks")
    parser.add_argument(
        "--results-path",
        default=str(DEFAULT_BENCHMARK_RESULTS_PATH),
        help="Output path for BENCHMARK_RESULTS.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    env_path = Path(args.env_file).resolve()
    results_path = Path(args.results_path).resolve()
    _load_env_file(env_path)

    base_url = str(args.base_url or "").strip() or _default_base_url()
    print("=" * 70)
    print("PHASE 13 LIVE FULL BENCHMARK")
    print("=" * 70)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Environment File: {env_path}")
    print(f"Base URL: {base_url}")
    print(f"Results Path: {results_path}")

    passed = 0
    failed = 0
    checks: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("AuthorityLock.verify_all_locked()", benchmark_authority_lock),
        ("CVE Ingestion Accuracy Probe", benchmark_cve_ingestion),
        ("MoE Smoke Test", benchmark_moe_smoke),
        ("Expert Queue Status", benchmark_expert_queue),
        ("Feature Dimension Check", benchmark_feature_dimension),
        (
            "Live Server /healthz",
            lambda: benchmark_live_server(
                base_url,
                boot_timeout_seconds=float(args.boot_timeout_seconds),
                request_timeout_seconds=float(args.request_timeout_seconds),
            ),
        ),
        (
            "Concurrent Stress Test",
            lambda: benchmark_concurrent_stress(
                base_url,
                request_count=int(args.stress_requests),
                max_workers=int(args.stress_workers),
                request_timeout_seconds=float(args.request_timeout_seconds),
            ),
        ),
    ]

    for name, func in checks:
        if _run_check(name, func):
            passed += 1
        else:
            failed += 1

    _write_results(results_path)
    print(f"\nResults saved to: {results_path}")
    print(f"Total: {passed} passed, {failed} failed out of {len(checks)} benchmarks")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
