"""
Dependency Checker — Readiness sub-checks with timeout budgets.

Each dependency check runs with a configurable timeout (default 2s)
and returns a typed CheckResult with latency measurement. Checks
run in parallel via ThreadPoolExecutor.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, List, NamedTuple, Optional

logger = logging.getLogger("ygb.reliability.dependency_checker")

DEFAULT_TIMEOUT_S = 2.0


class CheckResult(NamedTuple):
    """Result of a single dependency check."""
    name: str
    ok: bool
    latency_ms: float
    detail: str


def _check_storage() -> CheckResult:
    """Verify HDD storage engine is initialised and root exists."""
    start = time.monotonic()
    try:
        from backend.storage.storage_bridge import get_storage_health
        health = get_storage_health()
        latency = (time.monotonic() - start) * 1000
        is_ok = health.get("status") == "ACTIVE" or health.get("storage_active") is True
        return CheckResult("storage", is_ok, round(latency, 2), health.get("status", "UNKNOWN"))
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult("storage", False, round(latency, 2), type(exc).__name__)


def _check_revocation_backend() -> CheckResult:
    """Verify revocation store backend is reachable."""
    start = time.monotonic()
    try:
        from backend.auth.revocation_store import get_backend_health
        health = get_backend_health()
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            "revocation_store",
            health.get("available", False),
            round(latency, 2),
            health.get("type", "unknown"),
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult("revocation_store", False, round(latency, 2), type(exc).__name__)


def _check_config_integrity() -> CheckResult:
    """Verify critical configuration is set."""
    start = time.monotonic()
    issues: List[str] = []

    if not os.environ.get("YGB_HMAC_SECRET", "").strip():
        issues.append("YGB_HMAC_SECRET not set")

    latency = (time.monotonic() - start) * 1000
    if issues:
        return CheckResult("config", False, round(latency, 2), "; ".join(issues))
    return CheckResult("config", True, round(latency, 2), "all required config present")


def _check_external_url(url: str, timeout: float = 2.0) -> CheckResult:
    """Probe an external HTTP endpoint for reachability."""
    import urllib.request
    import urllib.error

    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.monotonic() - start) * 1000
            return CheckResult(
                f"external:{url}",
                200 <= resp.status < 500,
                round(latency, 2),
                f"HTTP {resp.status}",
            )
    except urllib.error.URLError as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(f"external:{url}", False, round(latency, 2), str(exc.reason)[:100])
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(f"external:{url}", False, round(latency, 2), type(exc).__name__)


def _check_metrics_registry() -> CheckResult:
    """Verify the observability metrics registry is initialized and functional."""
    start = time.monotonic()
    try:
        from backend.observability.metrics import metrics_registry
        # Probe: record a value and read it back
        metrics_registry.increment("readiness_probe_count", 0)
        snapshot = metrics_registry.get_snapshot()
        latency = (time.monotonic() - start) * 1000
        has_counters = isinstance(snapshot.get("counters"), dict)
        return CheckResult(
            "metrics_registry",
            has_counters,
            round(latency, 2),
            f"counters={len(snapshot.get('counters', {}))}",
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult("metrics_registry", False, round(latency, 2), type(exc).__name__)


# ---------------------------------------------------------------------------
# Built-in checks registry
# ---------------------------------------------------------------------------

_BUILTIN_CHECKS: List[Callable[[], CheckResult]] = [
    _check_storage,
    _check_revocation_backend,
    _check_config_integrity,
    _check_metrics_registry,
]


def _emit_check_metrics(result: CheckResult, *, timed_out: bool = False) -> None:
    try:
        from backend.observability.metrics import metrics_registry

        metrics_registry.record("dependency_latency_ms", float(result.latency_ms))
        if timed_out:
            metrics_registry.increment("timeout_count")
        elif not result.ok:
            metrics_registry.increment("error_count")
    except Exception:
        logger.debug("Failed to emit dependency-check metrics", exc_info=True)


def register_external_check(url: str, timeout: float = 2.0) -> None:
    """Add an external URL check to the readiness suite."""
    _BUILTIN_CHECKS.append(lambda: _check_external_url(url, timeout))


def run_all_checks(
    timeout_per_check: float = DEFAULT_TIMEOUT_S,
    checks: Optional[List[Callable[[], CheckResult]]] = None,
) -> Dict[str, Any]:
    """Run all dependency checks in parallel with a per-check timeout.

    Returns:
        {
            "ready": bool,
            "total_latency_ms": float,
            "checks": [CheckResult, ...],
        }
    """
    check_fns = checks if checks is not None else list(_BUILTIN_CHECKS)
    if not check_fns:
        return {
            "ready": True,
            "total_latency_ms": 0.0,
            "checks": [],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    results: List[Optional[CheckResult]] = [None] * len(check_fns)
    overall_start = time.monotonic()

    pool = ThreadPoolExecutor(max_workers=len(check_fns) or 1)
    futures = {
        pool.submit(fn): (idx, fn)
        for idx, fn in enumerate(check_fns)
    }
    try:
        done, not_done = wait(futures, timeout=timeout_per_check)

        for future in done:
            idx, fn = futures[future]
            fn_name = getattr(fn, "__name__", str(fn))
            try:
                result = future.result()
            except Exception as exc:
                elapsed = (time.monotonic() - overall_start) * 1000
                result = CheckResult(fn_name, False, round(elapsed, 2), type(exc).__name__)
                logger.error("Readiness check '%s' raised: %s", fn_name, exc)
            results[idx] = result
            _emit_check_metrics(result)

        for future in not_done:
            idx, fn = futures[future]
            fn_name = getattr(fn, "__name__", str(fn))
            elapsed = (time.monotonic() - overall_start) * 1000
            result = CheckResult(fn_name, False, round(elapsed, 2), "TIMEOUT")
            results[idx] = result
            future.cancel()
            _emit_check_metrics(result, timed_out=True)
            logger.warning("Readiness check '%s' timed out after %.1fs", fn_name, timeout_per_check)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    total_latency = round((time.monotonic() - overall_start) * 1000, 2)
    complete_results = [r for r in results if r is not None]
    all_ok = all(r.ok for r in complete_results)

    if not all_ok:
        failed = [r.name for r in complete_results if not r.ok]
        logger.warning(
            "Readiness FAILED — %d/%d checks failing: %s (%.1fms total)",
            len(failed), len(complete_results), ", ".join(failed), total_latency,
        )

    return {
        "ready": all_ok,
        "total_latency_ms": total_latency,
        "checks": [r._asdict() for r in complete_results],
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
