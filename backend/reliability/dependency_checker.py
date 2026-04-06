"""
Dependency Checker — Readiness sub-checks with timeout budgets.

Each dependency check runs with a configurable timeout (default 2s)
and returns a typed CheckResult with latency measurement. Checks
run in parallel via ThreadPoolExecutor.
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Union

logger = logging.getLogger("ygb.reliability.dependency_checker")

DEFAULT_TIMEOUT_S = 2.0
CHECK_ALL_TIMEOUT_S = 5.0


class CheckResult(NamedTuple):
    """Result of a single dependency check."""
    name: str
    ok: bool
    latency_ms: float
    detail: str


@dataclass(frozen=True)
class DependencyCheckResult:
    name: str
    available: bool
    latency_ms: float
    error: Optional[str]


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


def _normalize_dependency_result(
    result: Union[CheckResult, DependencyCheckResult, Any],
    *,
    fallback_name: str,
    fallback_latency_ms: float,
) -> DependencyCheckResult:
    if isinstance(result, DependencyCheckResult):
        return result
    if isinstance(result, CheckResult):
        return DependencyCheckResult(
            name=result.name,
            available=result.ok,
            latency_ms=float(result.latency_ms),
            error=None if result.ok else str(result.detail),
        )
    return DependencyCheckResult(
        name=fallback_name,
        available=False,
        latency_ms=float(fallback_latency_ms),
        error=f"unexpected_result:{type(result).__name__}",
    )


def _emit_check_metrics(
    result: Union[CheckResult, DependencyCheckResult],
    *,
    timed_out: bool = False,
) -> None:
    normalized = _normalize_dependency_result(
        result,
        fallback_name=getattr(result, "name", "unknown"),
        fallback_latency_ms=float(getattr(result, "latency_ms", 0.0) or 0.0),
    )
    try:
        from backend.observability.metrics import metrics_registry

        metrics_registry.record("dependency_latency_ms", float(normalized.latency_ms))
        if timed_out or normalized.error == "timeout":
            metrics_registry.increment("timeout_count")
        elif not normalized.available:
            metrics_registry.increment("error_count")
    except Exception:
        logger.debug("Failed to emit dependency-check metrics", exc_info=True)


def _run_check_with_timeout(
    check: Callable[[], CheckResult],
    timeout: float,
) -> DependencyCheckResult:
    start = time.monotonic()
    check_name = getattr(check, "__name__", str(check))

    async def _runner() -> Union[CheckResult, DependencyCheckResult, Any]:
        return await asyncio.wait_for(asyncio.to_thread(check), timeout=timeout)

    try:
        raw_result = asyncio.run(_runner())
    except asyncio.TimeoutError:
        result = DependencyCheckResult(
            name=check_name,
            available=False,
            latency_ms=round((time.monotonic() - start) * 1000, 2),
            error="timeout",
        )
        _emit_check_metrics(result, timed_out=True)
        logger.warning("Dependency check '%s' timed out after %.1fs", check_name, timeout)
        return result
    except BaseException as exc:
        result = DependencyCheckResult(
            name=check_name,
            available=False,
            latency_ms=round((time.monotonic() - start) * 1000, 2),
            error=type(exc).__name__,
        )
        _emit_check_metrics(result)
        logger.error("Dependency check '%s' raised: %s", check_name, exc)
        return result

    result = _normalize_dependency_result(
        raw_result,
        fallback_name=check_name,
        fallback_latency_ms=round((time.monotonic() - start) * 1000, 2),
    )
    _emit_check_metrics(result)
    return result


def check_all(
    checks: Optional[List[Callable[[], CheckResult]]] = None,
    timeout: float = CHECK_ALL_TIMEOUT_S,
) -> List[DependencyCheckResult]:
    try:
        check_fns = list(_BUILTIN_CHECKS if checks is None else checks)
    except BaseException as exc:
        logger.error("Failed to prepare dependency checks: %s", exc, exc_info=True)
        return [
            DependencyCheckResult(
                name="check_all",
                available=False,
                latency_ms=0.0,
                error=type(exc).__name__,
            )
        ]

    if not check_fns:
        return []

    results: List[Optional[DependencyCheckResult]] = [None] * len(check_fns)

    try:
        with ThreadPoolExecutor(max_workers=len(check_fns) or 1) as pool:
            futures = {
                pool.submit(_run_check_with_timeout, fn, timeout): (idx, fn)
                for idx, fn in enumerate(check_fns)
            }

            for future, (idx, fn) in futures.items():
                check_name = getattr(fn, "__name__", str(fn))
                try:
                    results[idx] = future.result()
                except BaseException as exc:
                    logger.error("Dependency check '%s' failed unexpectedly: %s", check_name, exc)
                    results[idx] = DependencyCheckResult(
                        name=check_name,
                        available=False,
                        latency_ms=0.0,
                        error=type(exc).__name__,
                    )
    except BaseException as exc:
        logger.error("Unexpected failure in check_all: %s", exc, exc_info=True)
        return [
            DependencyCheckResult(
                name="check_all",
                available=False,
                latency_ms=0.0,
                error=type(exc).__name__,
            )
        ]

    return [result for result in results if result is not None]


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
