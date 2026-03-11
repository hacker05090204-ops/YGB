"""
Dependency Checker — Readiness sub-checks with timeout budgets.

Each dependency check runs with a configurable timeout (default 2s)
and returns a typed CheckResult with latency measurement. Checks
run in parallel via ThreadPoolExecutor.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
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
    results: List[CheckResult] = []
    overall_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=len(check_fns) or 1) as pool:
        futures = {pool.submit(fn): fn for fn in check_fns}

        for future in futures:
            fn = futures[future]
            fn_name = getattr(fn, "__name__", str(fn))
            try:
                result = future.result(timeout=timeout_per_check)
                results.append(result)
            except FuturesTimeout:
                elapsed = (time.monotonic() - overall_start) * 1000
                results.append(
                    CheckResult(fn_name, False, round(elapsed, 2), "TIMEOUT")
                )
                logger.warning("Readiness check '%s' timed out after %.1fs", fn_name, timeout_per_check)
            except Exception as exc:
                elapsed = (time.monotonic() - overall_start) * 1000
                results.append(
                    CheckResult(fn_name, False, round(elapsed, 2), type(exc).__name__)
                )
                logger.error("Readiness check '%s' raised: %s", fn_name, exc)

    total_latency = round((time.monotonic() - overall_start) * 1000, 2)
    all_ok = all(r.ok for r in results)

    if not all_ok:
        failed = [r.name for r in results if not r.ok]
        logger.warning(
            "Readiness FAILED — %d/%d checks failing: %s (%.1fms total)",
            len(failed), len(results), ", ".join(failed), total_latency,
        )

    return {
        "ready": all_ok,
        "total_latency_ms": total_latency,
        "checks": [r._asdict() for r in results],
    }
