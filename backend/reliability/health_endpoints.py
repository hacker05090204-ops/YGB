"""
Health Endpoints — /healthz (liveness) and /readyz (readiness) probes.

These are infrastructure-grade endpoints intended for container orchestrators,
load balancers, and monitoring systems. They are intentionally separate from
the existing /api/health frontend connectivity probe.

- /healthz  → Zero-dep liveness check (is the process alive?)
- /readyz   → Dependency readiness (are all backends reachable?)
"""

import logging
import time

from fastapi import APIRouter
from starlette.responses import JSONResponse

from backend.reliability.dependency_checker import run_all_checks

logger = logging.getLogger("ygb.reliability.health")

health_router = APIRouter(tags=["health"])

# Process start time for uptime calculation
_BOOT_MONOTONIC = time.monotonic()
_BOOT_WALL = time.time()


@health_router.get("/healthz")
async def liveness():
    """Liveness probe — confirms the process is running.

    Always returns 200 unless the event loop is completely wedged.
    No dependency checks, no I/O, no auth.
    """
    uptime_s = round(time.monotonic() - _BOOT_MONOTONIC, 1)
    return JSONResponse(
        status_code=200,
        content={
            "status": "alive",
            "uptime_s": uptime_s,
            "boot_time": _BOOT_WALL,
        },
    )


@health_router.get("/readyz")
async def readiness():
    """Readiness probe — verifies all dependencies are healthy.

    Runs parallel checks with per-check timeout budgets.
    Returns 200 if all pass, 503 if any fail.
    """
    start = time.monotonic()
    result = run_all_checks(timeout_per_check=2.0)
    total_ms = round((time.monotonic() - start) * 1000, 2)

    result["readiness_latency_ms"] = total_ms

    # Try to emit readiness latency to metrics (best-effort)
    try:
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("readiness_latency_ms", total_ms)
    except Exception as exc:
        logger.warning(
            "Non-critical failure while recording readiness latency: %s",
            exc,
            exc_info=True,
        )

    status_code = 200 if result["ready"] else 503
    return JSONResponse(status_code=status_code, content=result)
