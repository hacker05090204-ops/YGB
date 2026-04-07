"""
YGB API Server

FastAPI backend providing REST and WebSocket endpoints for the YGB frontend.
Bridges Python governance phases and HUMANOID_HUNTER modules with the UI.

THIS SERVER IS FOR DISPLAY AND COORDINATION ONLY.
IT CANNOT EXECUTE BROWSER ACTIONS OR BYPASS GOVERNANCE.
"""

import os

from pathlib import Path as _Path


def _is_placeholder_env_value(key: str, value: str) -> bool:
    upper = value.strip().upper()
    if not upper:
        return False
    if upper.startswith("CHANGE_ME"):
        return True
    if key == "GITHUB_CLIENT_ID" and upper.startswith("CONNECTED_GITHUB_CLIENT_ID"):
        return True
    if key == "GITHUB_CLIENT_SECRET" and upper.startswith("CHANGE_ME_PROVIDE_REAL"):
        return True
    if key == "GOOGLE_CLIENT_ID" and upper.startswith("CONNECTED_GOOGLE_CLIENT_ID"):
        return True
    if key == "GOOGLE_CLIENT_SECRET" and upper.startswith("CHANGE_ME_PROVIDE_REAL"):
        return True
    return False


def _load_env_file(
    path: _Path,
    *,
    allow_placeholders: bool = False,
    allowed_keys: set[str] | None = None,
) -> None:
    if not path.exists():
        return
    with open(path) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            _eq = _line.find("=")
            if _eq <= 0:
                continue
            _key = _line[:_eq].strip()
            _val = _line[_eq + 1 :].strip()
            if allowed_keys is not None and _key not in allowed_keys:
                continue
            if not allow_placeholders and _is_placeholder_env_value(_key, _val):
                continue
            # Don't override existing env vars (command-line takes precedence)
            if _key not in os.environ:
                os.environ[_key] = _val


def _oauth_provider_env_keys(provider: str) -> dict[str, str]:
    normalized = (provider or "github").strip().lower()
    if normalized == "google":
        return {
            "client_id": "GOOGLE_CLIENT_ID",
            "client_secret": "GOOGLE_CLIENT_SECRET",
            "redirect_uri": "GOOGLE_REDIRECT_URI",
        }
    return {
        "client_id": "GITHUB_CLIENT_ID",
        "client_secret": "GITHUB_CLIENT_SECRET",
        "redirect_uri": "GITHUB_REDIRECT_URI",
    }


def _shared_oauth_candidate_files(provider: str = "github") -> list[_Path]:
    candidates: list[_Path] = []
    explicit = os.getenv("YGB_SHARED_OAUTH_FILE", "").strip()
    if explicit:
        candidates.append(_Path(explicit).expanduser())

    normalized = (provider or "github").strip().lower()
    filenames = [f"{normalized}_oauth.env", "oauth.env"]

    for root in (
        os.getenv("YGB_HDD_ROOT", "D:/ygb_hdd"),
        os.getenv("YGB_HDD_FALLBACK_ROOT", "C:/ygb_hdd_fallback"),
    ):
        if not root:
            continue
        base = _Path(root)
        for filename in filenames:
            candidates.extend(
                [
                    base / "secrets" / filename,
                    base / "config" / filename,
                ]
            )

    deduped: list[_Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            deduped.append(candidate)
            seen.add(key)
    return deduped


def _load_shared_oauth_env(provider: str) -> None:
    keys = _oauth_provider_env_keys(provider)
    needed = {
        keys["client_id"],
        keys["client_secret"],
        keys["redirect_uri"],
        "FRONTEND_URL",
        "YGB_ALLOWED_ORIGINS",
    }
    if os.getenv(keys["client_id"]) and os.getenv(keys["client_secret"]):
        return
    for candidate in _shared_oauth_candidate_files(provider):
        _load_env_file(candidate, allow_placeholders=False, allowed_keys=needed)
        if os.getenv(keys["client_id"]) and os.getenv(keys["client_secret"]):
            break


async def _abort_if_disconnected(request: "Request") -> None:
    if await request.is_disconnected():
        raise HTTPException(status_code=499, detail="Client disconnected")


# Load env files FIRST — before any other imports read env vars.
_ENV_ROOT = _Path(__file__).resolve().parent.parent
_load_env_file(_ENV_ROOT / ".env", allow_placeholders=False)
_load_env_file(_ENV_ROOT / ".env.connected", allow_placeholders=False)
_load_shared_oauth_env("github")
_load_shared_oauth_env("google")

import sys
import uuid
import json
import asyncio
import hashlib
import hmac
import zlib
import base64
import secrets
import logging
import ipaddress
import threading
import time
import mimetypes

logger = logging.getLogger("ygb.server")
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Request,
    Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel

# Centralized auth guard
from backend.auth.auth_guard import (
    require_auth,
    require_admin,
    build_temporary_auth_user,
    is_temporary_auth_bypass_enabled,
    revoke_token,
    revoke_session,
    preflight_check_secrets,
    get_required_secret,
    validate_target_url,
    ws_authenticate,
    AUTH_COOKIE_NAME,
    LEGACY_AUTH_COOKIE_NAME,
    CSRF_COOKIE_NAME,
)
from backend.auth.ownership import check_resource_owner, check_ws_resource_owner
from backend.api.runtime_state import runtime_state

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure HDD storage root points to the dedicated YGB_DATA partition (D:\)
import platform as _plat

if _plat.system() == "Windows":
    os.environ.setdefault("YGB_HDD_ROOT", "D:/ygb_hdd")
    os.environ.setdefault("YGB_HDD_FALLBACK_ROOT", "C:/ygb_hdd_fallback")

# Import HDD storage bridge (replaces SQLite database module)
from backend.storage.storage_bridge import (
    init_storage,
    shutdown_storage,
    create_user,
    get_user,
    get_all_users,
    get_users_page,
    update_user_stats,
    create_target,
    get_all_targets,
    get_targets_page,
    get_target,
    create_bounty,
    get_user_bounties,
    get_all_bounties,
    get_bounties_page,
    update_bounty_status,
    create_session,
    get_user_sessions,
    update_session_progress,
    log_activity,
    get_recent_activity,
    get_admin_stats,
    get_storage_stats,
    get_lifecycle_status,
    get_disk_status,
    get_delete_preview,
    store_video,
    get_video_stream_token,
    stream_video,
    list_videos,
    get_storage_health,
    update_user_auth_profile,
    get_admin_user_security_view,
)
from api.routers.report_router import build_report_router
from api.routers.storage_router import build_storage_router
from api.services.runtime_status_service import (
    get_accuracy_snapshot_payload,
    get_runtime_status_payload,
)
from api.services.execution_control_service import enforce_governed_execution
from api.services.auth_read_service import (
    build_auth_me_response,
    build_auth_profile_payload,
    build_auth_provider_status,
)
from api.services.voice_parse_service import parse_voice_request, voice_mode_payload
from api.services.voice_service import get_voice_orchestrator
from training_core.scheduler import register_execution_validator

# Import tiered storage manager (SSD cap + HDD overflow)
try:
    from backend.storage.tiered_storage import (
        get_storage_report as get_tiered_report,
        enforce_ssd_cap,
        start_enforcement_loop as start_storage_enforcement,
        resolve_path as resolve_storage_path,
    )

    TIERED_STORAGE_AVAILABLE = True
    # NOTE: start_storage_enforcement() is called inside lifespan() to avoid
    # spawning background threads at import time (test pollution / orphaned threads).
    logger.info(
        "[BOOT] Tiered storage module loaded (enforcement deferred to lifespan)"
    )
except Exception as _ts_err:
    TIERED_STORAGE_AVAILABLE = False
    logger.warning("[BOOT] Tiered storage not available: %s", _ts_err)

# Import activation profiles
try:
    from backend.config.activation_profiles import (
        validate_startup,
        log_boot_summary,
        get_profile,
        get_smtp_pass,
        IntegrationState,
    )

    ACTIVATION_PROFILES_AVAILABLE = True
except ImportError:
    ACTIVATION_PROFILES_AVAILABLE = False

# Import training state manager
from backend.training.state_manager import get_training_state_manager
from backend.training.runtime_artifacts import (
    bootstrap_runtime_artifacts,
    repair_runtime_artifacts_if_needed,
)
from backend.api.system_status_store import (
    read_or_refresh_system_status_file,
    refresh_system_status_file,
)
from backend.training.runtime_status_validator import validate_precision_breach_status

# Import auth and alerts
from backend.auth.auth import (
    hash_password,
    verify_password,
    generate_jwt,
    verify_jwt,
    compute_device_hash,
    get_rate_limiter,
    generate_csrf_token,
    verify_csrf_token,
    needs_rehash,
)
from backend.auth.geoip import resolve_ip_geolocation
from backend.alerts.email_alerts import (
    alert_new_login,
    alert_new_device,
    alert_multiple_devices,
    alert_suspicious_activity,
    alert_rate_limit_exceeded,
)
from backend.storage.storage_bridge import (
    register_device,
    get_user_devices,
    get_all_active_devices,
    get_active_device_count,
    get_active_sessions,
    end_session,
    get_user_by_email,
    get_user_by_github_id,
    get_user_by_google_sub,
    update_user_password,
)

# Import REAL phase runner with actual browser automation
try:
    from api.phase_runner import RealPhaseRunner, run_real_workflow

    PHASE_RUNNER_AVAILABLE = True
except ImportError:
    try:
        from phase_runner import RealPhaseRunner, run_real_workflow

        PHASE_RUNNER_AVAILABLE = True
    except ImportError:
        PHASE_RUNNER_AVAILABLE = False
        RealPhaseRunner = None
        run_real_workflow = None
        logger.warning(
            "[BOOT] phase_runner not available — browser automation routes degraded"
        )

# =============================================================================
# G38 AUTO-TRAINING IMPORTS
# =============================================================================

try:
    from impl_v1.phase49.runtime import (
        get_auto_trainer,
        start_auto_training,
        stop_auto_training,
        start_continuous_training,
        stop_continuous_training,
        get_idle_seconds,
        is_power_connected,
        is_scan_active,
        set_scan_active,
        TrainingState,
    )
    from impl_v1.phase49.governors.g38_self_trained_model import (
        verify_all_guards,
        ALL_GUARDS,
        can_ai_execute,
        can_ai_submit,
    )
    from impl_v1.phase49.governors.g38_safe_pretraining import (
        verify_pretraining_guards,
        get_mode_a_status,
        get_training_mode_summary,
    )

    G38_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] G38 modules not available: {e}")
    verify_all_guards = lambda: {}
    ALL_GUARDS = ()
    can_ai_execute = lambda: (False, "G38 unavailable")
    can_ai_submit = lambda: (False, "G38 unavailable")
    G38_AVAILABLE = False

# =============================================================================
# SYSTEM INTEGRITY SUPERVISOR
# =============================================================================

try:
    from backend.integrity.integrity_bridge import get_integrity_supervisor

    INTEGRITY_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Integrity supervisor not available: {e}")
    INTEGRITY_AVAILABLE = False

# =============================================================================
# RESEARCH ASSISTANT (DUAL-MODE VOICE)
# =============================================================================

try:
    from backend.assistant.query_router import (
        QueryRouter,
        ResearchSearchPipeline,
        VoiceMode,
        ResearchStatus,
    )
    from backend.assistant.isolation_guard import IsolationGuard

    RESEARCH_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Research assistant not available: {e}")
    RESEARCH_AVAILABLE = False

# =============================================================================
# APP CONFIGURATION
# =============================================================================

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    """Unified server lifespan: preflight → storage → CVE scheduler → G38."""
    # --- STARTUP ---
    # Activate structured JSON logging at boot
    try:
        from backend.observability.log_config import configure_logging

        configure_logging(level="INFO", structured=True)
        logger.info("[BOOT] Structured logging activated")
    except ImportError as exc:
        logger.debug(
            "[BOOT] Structured logging configuration module unavailable: %s", exc
        )

    logger.info("[BOOT] Server lifespan BOOTING")
    g38_started = False

    # SECURITY: Preflight checks — fail-closed on missing/weak secrets
    preflight_check_secrets()

    phases = discover_python_phases()
    hunter = discover_hunter_modules()
    _HEALTH_STATIC["python_phases"] = len([p for p in phases if p["number"] <= 19])
    _HEALTH_STATIC["impl_phases"] = len([p for p in phases if p["number"] >= 20])
    _HEALTH_STATIC["hunter_modules"] = len(hunter)
    print(f"[*] YGB API Server starting...")
    print(f"[*] Project root: {PROJECT_ROOT}")
    print(f"[*] Python phases: {len(phases)}")
    print(f"[*] Hunter modules: {len(hunter)}")

    # Initialize HDD storage engine (replaces SQLite)
    try:
        result = init_storage()
        print(f"[+] HDD Storage Engine initialized at: {result['hdd_root']}")
        print(f"[+] Subsystems: {result['subsystems']}")
    except Exception as e:
        print(f"[!] HDD Storage Engine init failed: {e}")

    try:
        bootstrap_runtime_artifacts()
        logger.info("[BOOT] Runtime artifacts bootstrapped")
    except Exception as e:
        logger.warning("[BOOT] Runtime artifact bootstrap degraded: %s", e)

    try:
        precision_status = validate_precision_breach_status()
        if precision_status.get("checked"):
            logger.info(
                "[BOOT] Runtime precision status reconciled: %s "
                "(precision=%.4f threshold=%.4f samples=%s source=%s)",
                precision_status.get("state"),
                float(precision_status.get("current_precision", 0.0)),
                float(precision_status.get("precision_threshold", 0.0)),
                precision_status.get("validation_samples"),
                precision_status.get("validation_source"),
            )
    except Exception as e:
        logger.warning("[BOOT] Runtime precision reconciliation degraded: %s", e)

    try:
        read_or_refresh_system_status_file(force_refresh=True)
        logger.info("[BOOT] Canonical system status refreshed")
    except Exception as e:
        logger.warning("[BOOT] Canonical system status refresh degraded: %s", e)

    # Start CVE scheduler (async — must be awaited)
    try:
        from backend.cve.cve_scheduler import get_scheduler

        scheduler = get_scheduler()
        await scheduler.start()
        logger.info(
            f"[BOOT] CVE scheduler RUNNING "
            f"(interval={scheduler.interval_seconds}s, "
            f"running={scheduler.is_running})"
        )
        print("[OK] CVE scheduler started (5-minute interval)")
    except Exception as e:
        logger.error(f"[BOOT] CVE scheduler DEGRADED: {e}")
        print(f"[WARN] CVE scheduler not started: {e}")

    # Start bridge ingestion worker (CVE → training bridge)
    try:
        from backend.cve.bridge_ingestion_worker import get_bridge_worker

        bridge_worker = get_bridge_worker()
        logger.info(
            f"[BOOT] Bridge ingestion worker initialized "
            f"(dll_loaded={bridge_worker.is_bridge_loaded})"
        )
    except Exception as e:
        logger.warning(f"[BOOT] Bridge ingestion worker not available: {e}")

    try:
        from backend.startup.pipeline_bootstrap import bootstrap_pipeline

        bootstrap_pipeline()
        logger.info("[BOOT] Fully automatic ingestion-to-training pipeline started")
    except Exception as e:
        logger.critical(
            "[BOOT] Fully automatic ingestion-to-training pipeline bootstrap failed; "
            "server will continue and the pipeline can be restarted later: %s",
            e,
            exc_info=True,
        )

    # Start G38 auto-training scheduler only when explicitly enabled.
    if G38_AVAILABLE and _ENABLE_G38_AUTO_TRAINING:
        start_auto_training()  # Starts background monitor
        # Enable 24/7 continuous training (infinite epochs)
        try:
            result = start_continuous_training(0)
            if result.get("started"):
                print("[*] G38 24/7 continuous training STARTED")
            else:
                print(
                    f"[*] G38 continuous training deferred: {result.get('reason', 'unknown')}"
                )
        except Exception as e:
            logger.warning(f"[BOOT] G38 continuous training start failed: {e}")
        g38_started = True
        print("[*] G38 auto-training started")

    # Start tiered-storage SSD cap enforcement inside lifespan (not at import)
    if TIERED_STORAGE_AVAILABLE:
        try:
            start_storage_enforcement(300)
            logger.info(
                "[BOOT] Tiered storage SSD cap enforcement started (5 min interval)"
            )
        except Exception as _enf_err:
            logger.warning("[BOOT] Tiered storage enforcement failed: %s", _enf_err)

    print(f"[+] Server ready at http://localhost:8000")
    logger.info("[BOOT] Server lifespan RUNNING")
    yield
    # --- SHUTDOWN ---
    logger.info("[SHUTDOWN] Server lifespan stopping")
    print("[*] YGB API Server shutting down...")
    try:
        from backend.cve.cve_scheduler import get_scheduler

        scheduler = get_scheduler()
        await scheduler.stop()
        logger.info("[SHUTDOWN] CVE scheduler stopped")
        print("CVE scheduler stopped")
    except Exception:
        logger.warning("[SHUTDOWN] CVE scheduler stop failed", exc_info=True)

    # Stop G38 auto-training
    if G38_AVAILABLE and g38_started:
        stop_auto_training()
        print("[*] G38 auto-training stopped")

    # Shutdown HDD storage engine
    shutdown_storage()
    print("[*] HDD Storage Engine shutdown complete")


app = FastAPI(
    title="YGB API",
    description="Bug Bounty Governance Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for frontend — include FRONTEND_URL and LAN origins
_CONFIGURED_FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
_PRIVATE_FRONTEND_ORIGIN_REGEX = (
    r"^https?://(?:(?:localhost|127\.0\.0\.1)"
    r"|(?:10(?:\.\d{1,3}){3})"
    r"|(?:192\.168(?:\.\d{1,3}){2})"
    r"|(?:172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
    r"|(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}))"
    r":(?:3000|8000)$"
)
_cors_origins: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if _CONFIGURED_FRONTEND_URL and _CONFIGURED_FRONTEND_URL not in _cors_origins:
    _cors_origins.append(_CONFIGURED_FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_PRIVATE_FRONTEND_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sync engine API endpoints
try:
    from backend.sync.sync_routes import api_sync_router, sync_router

    app.include_router(sync_router, prefix="/sync")
    app.include_router(api_sync_router, prefix="/api/sync")
    logger.info("[SYNC] Sync API routes mounted at /sync/* and /api/sync/*")
except ImportError as _sync_err:
    logger.warning("[SYNC] Sync routes unavailable: %s", _sync_err)

# =============================================================================
# RELIABILITY — /healthz and /readyz infrastructure probes
# =============================================================================
try:
    from backend.reliability.health_endpoints import health_router

    app.include_router(health_router)
    logger.info("[BOOT] Health probes registered: /healthz, /readyz")
except ImportError as _health_err:
    logger.warning("[BOOT] Health probes unavailable: %s", _health_err)

app.include_router(build_report_router(PROJECT_ROOT))
app.include_router(build_storage_router())

# =============================================================================
# OBSERVABILITY — per-request latency tracking middleware
# =============================================================================
try:
    from backend.observability.metrics import metrics_registry as _metrics

    @app.middleware("http")
    async def _latency_middleware(request: Request, call_next):
        _req_start = time.monotonic()
        response = await call_next(request)
        _req_ms = round((time.monotonic() - _req_start) * 1000, 2)
        _metrics.record("request_latency_ms", _req_ms)
        _metrics.increment("request_count")
        if response.status_code >= 500:
            _metrics.increment("error_count")
        response.headers["X-Request-Latency-Ms"] = str(_req_ms)
        return response

    @app.get("/metrics/snapshot")
    async def _metrics_snapshot(user=Depends(require_auth)):
        """Internal metrics snapshot for observability dashboards."""
        return _metrics.get_snapshot()

    logger.info("[BOOT] Observability middleware + /metrics/snapshot registered")
except ImportError as _obs_err:
    logger.warning("[BOOT] Observability module unavailable: %s", _obs_err)

# =============================================================================
# GLOBAL EXCEPTION HANDLER — sanitize internal errors from API responses
# =============================================================================
from starlette.responses import JSONResponse
from backend.api.exceptions import YGBError


@app.exception_handler(YGBError)
async def _ygb_error_handler(request: Request, exc: YGBError):
    """Handle typed YGB exceptions with proper status codes and correlation IDs."""
    exc.log()
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response(),
    )


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for unhandled exceptions. Returns a sanitized 500 response
    with a correlation ID for debugging. Raw traceback logged server-side only.
    """
    import traceback

    correlation_id = secrets.token_hex(8)
    logger.error(
        "Unhandled exception [%s] %s %s: %s\n%s",
        correlation_id,
        request.method,
        request.url.path,
        str(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected error occurred. Contact support with this ID.",
            "correlation_id": correlation_id,
        },
    )


# Voice pipeline router
try:
    from api.voice_routes import voice_router

    app.include_router(voice_router)
    logger.info("[BOOT] Voice pipeline routes registered")
except ImportError:
    logger.warning("[BOOT] Voice routes not available")

# Voice gateway (WebSocket streaming + REST transcribe/intent/execute/respond)
try:
    from api.voice_gateway import voice_gw_router

    app.include_router(voice_gw_router)
    logger.info("[BOOT] Voice gateway routes registered")
except ImportError as e:
    logger.warning(f"[BOOT] Voice gateway not available: {e}")

# Report Generator router (reports + video recording metadata)
try:
    from backend.api.report_generator import router as report_router

    app.include_router(report_router)
    logger.info("[BOOT] Report Generator routes registered")
except ImportError as e:
    logger.warning(f"[BOOT] Report Generator not available: {e}")

# Aggregated system status endpoint
try:
    from backend.api.system_status import system_status_router

    app.include_router(system_status_router)
    logger.info("[BOOT] System status endpoint registered: /api/system/status")
except ImportError as e:
    logger.warning(f"[BOOT] System status endpoint not available: {e}")

# Runtime API router (runtime status + auto-training endpoints)
try:
    from backend.api.runtime_api import router as runtime_api_router

    app.include_router(runtime_api_router)
    logger.info(
        "[BOOT] Runtime API endpoints registered: /api/v1/training/auto/status, /api/v1/training/auto/trigger"
    )
except ImportError as e:
    logger.warning(f"[BOOT] Runtime API router not available: {e}")

# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class StartWorkflowRequest(BaseModel):
    target: str
    mode: str = "READ_ONLY"  # READ_ONLY or REAL


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    report_id: Optional[str] = None
    status: str


class PhaseInfo(BaseModel):
    name: str
    number: int
    available: bool
    description: str


# =============================================================================
# PHASE-49 MODELS
# =============================================================================


class CreateDashboardRequest(BaseModel):
    user_id: str
    user_name: str


class ExecutionTransitionRequest(BaseModel):
    transition: str  # PLAN, SIMULATE, REQUEST_APPROVAL, HUMAN_APPROVE, HUMAN_DENY, COMPLETE, ABORT
    actor_id: str
    reason: str = ""


class ApprovalDecisionRequest(BaseModel):
    request_id: str
    approved: bool
    approver_id: str
    reason: str = ""


class TargetDiscoveryRequest(BaseModel):
    min_payout: str = "LOW"  # LOW, MEDIUM, HIGH
    max_density: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    public_only: bool = True


class VoiceParseRequest(BaseModel):
    text: str


class AutonomySessionRequest(BaseModel):
    mode: str  # READ_ONLY, AUTONOMOUS_FIND, REAL
    duration_hours: float = 0.0


# =============================================================================
# IN-MEMORY STATE (runtime state — persisted in-memory per server lifetime)
# =============================================================================

# Active WebSocket connections
hunter_connections: Dict[str, WebSocket] = {}
bounty_connections: Dict[str, WebSocket] = {}

# Active workflows
active_workflows: Dict[str, Dict[str, Any]] = {}

# Phase-49 State Stores
dashboard_states: Dict[str, Dict[str, Any]] = {}
execution_kernels: Dict[str, Dict[str, Any]] = {}
approval_requests: Dict[str, Dict[str, Any]] = {}
autonomy_sessions: Dict[str, Dict[str, Any]] = {}

# Cached static health metadata for fast /health responses.
_HEALTH_STATIC = {
    "python_phases": 0,
    "impl_phases": 0,
    "hunter_modules": 0,
}
_HEALTH_STORAGE_CACHE_SECONDS = max(
    1.0,
    float(os.getenv("YGB_HEALTH_STORAGE_CACHE_SECONDS", "15")),
)
_HEALTH_STORAGE_CACHE_LOCK = threading.Lock()
_HEALTH_STORAGE_CACHE: Dict[str, Any] = {
    "checked_at_monotonic": 0.0,
    "value": None,
}
_RUNTIME_STATUS_CACHE_SECONDS = max(
    1.0,
    float(os.getenv("YGB_RUNTIME_STATUS_CACHE_SECONDS", "3")),
)
_RUNTIME_STATUS_CACHE_LOCK = threading.Lock()
_RUNTIME_STATUS_CACHE: Dict[str, Any] = {
    "checked_at_monotonic": 0.0,
    "training_active": None,
    "telemetry_mtime": None,
    "value": None,
}


def _get_runtime_status_cached() -> Optional[Dict[str, Any]]:
    telemetry_path = PROJECT_ROOT / "reports" / "training_telemetry.json"
    telemetry_mtime = (
        telemetry_path.stat().st_mtime if telemetry_path.exists() else None
    )
    training_active = False
    if G38_AVAILABLE:
        try:
            training_active = bool(
                get_auto_trainer().get_status().get("is_training", False)
            )
        except Exception:
            training_active = False

    now = time.monotonic()
    with _RUNTIME_STATUS_CACHE_LOCK:
        cached = _RUNTIME_STATUS_CACHE.get("value")
        checked_at = float(_RUNTIME_STATUS_CACHE.get("checked_at_monotonic") or 0.0)
        same_training_state = (
            _RUNTIME_STATUS_CACHE.get("training_active") == training_active
        )
        same_telemetry_state = (
            _RUNTIME_STATUS_CACHE.get("telemetry_mtime") == telemetry_mtime
        )
        if (
            isinstance(cached, dict)
            and (now - checked_at) < _RUNTIME_STATUS_CACHE_SECONDS
            and same_training_state
            and same_telemetry_state
        ):
            return dict(cached)
    return None


def _store_runtime_status_cached(payload: Dict[str, Any]) -> Dict[str, Any]:
    telemetry_path = PROJECT_ROOT / "reports" / "training_telemetry.json"
    telemetry_mtime = (
        telemetry_path.stat().st_mtime if telemetry_path.exists() else None
    )
    training_active = False
    if G38_AVAILABLE:
        try:
            training_active = bool(
                get_auto_trainer().get_status().get("is_training", False)
            )
        except Exception:
            training_active = False
    with _RUNTIME_STATUS_CACHE_LOCK:
        _RUNTIME_STATUS_CACHE["checked_at_monotonic"] = time.monotonic()
        _RUNTIME_STATUS_CACHE["training_active"] = training_active
        _RUNTIME_STATUS_CACHE["telemetry_mtime"] = telemetry_mtime
        _RUNTIME_STATUS_CACHE["value"] = dict(payload)
    return payload


def _enforce_training_execution_control() -> None:
    enforce_governed_execution(
        action_name="training_core_entrypoint",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )


register_execution_validator(_enforce_training_execution_control)


def _get_cached_storage_health() -> Dict[str, Any]:
    """
    Best-effort storage snapshot for the unauthenticated liveness endpoint.

    `/api/health` is used as a fast connectivity probe by multiple frontend
    pages. Keep this path responsive by reusing a recent storage snapshot
    instead of probing storage topology and disk state on every request.
    """
    now = time.monotonic()
    with _HEALTH_STORAGE_CACHE_LOCK:
        cached = _HEALTH_STORAGE_CACHE["value"]
        checked_at = float(_HEALTH_STORAGE_CACHE["checked_at_monotonic"] or 0.0)
        if (
            isinstance(cached, dict)
            and (now - checked_at) < _HEALTH_STORAGE_CACHE_SECONDS
        ):
            return dict(cached)

    try:
        snapshot = get_storage_health()
    except Exception as e:
        logger.error("Storage health probe failed: %s", e)
        snapshot = {
            "status": "UNKNOWN",
            "storage_active": None,
            "db_active": None,
            "lifecycle_ok": None,
            "disk_monitor_ok": None,
            "reason": "Storage probe failed - check server logs",
            "checked_at": datetime.now(UTC).isoformat(),
        }

    snapshot = {
        **snapshot,
        "cached_for_health_seconds": _HEALTH_STORAGE_CACHE_SECONDS,
    }

    with _HEALTH_STORAGE_CACHE_LOCK:
        _HEALTH_STORAGE_CACHE["checked_at_monotonic"] = now
        _HEALTH_STORAGE_CACHE["value"] = dict(snapshot)

    return dict(snapshot)


# =============================================================================
# PHASE DISCOVERY
# =============================================================================


def discover_python_phases() -> List[Dict[str, Any]]:
    """Discover available Python phases."""
    phases = []

    # Phases 01-19 in python/
    python_dir = PROJECT_ROOT / "python"
    if python_dir.exists():
        for item in python_dir.iterdir():
            if item.is_dir() and item.name.startswith("phase"):
                try:
                    num = int(item.name.replace("phase", "").split("_")[0])
                    phases.append(
                        {
                            "name": item.name,
                            "number": num,
                            "path": str(item),
                            "available": True,
                            "description": f"Phase {num:02d} - {item.name.split('_', 1)[-1].replace('_', ' ').title()}",
                        }
                    )
                except ValueError:
                    logger.debug(
                        "Skipping unrecognized python phase directory: %s", item.name
                    )

    # Phases 20-49 in impl_v1/
    impl_dir = PROJECT_ROOT / "impl_v1"
    if impl_dir.exists():
        for item in impl_dir.iterdir():
            if item.is_dir() and item.name.startswith("phase"):
                try:
                    num = int(item.name.replace("phase", ""))
                    phases.append(
                        {
                            "name": item.name,
                            "number": num,
                            "path": str(item),
                            "available": True,
                            "description": f"Phase {num:02d} - Implementation Layer",
                        }
                    )
                except ValueError:
                    logger.debug(
                        "Skipping unrecognized implementation phase directory: %s",
                        item.name,
                    )

    return sorted(phases, key=lambda x: x["number"])


def discover_hunter_modules() -> Dict[str, bool]:
    """Discover available HUMANOID_HUNTER modules."""
    modules = {}
    hunter_dir = PROJECT_ROOT / "HUMANOID_HUNTER"

    if hunter_dir.exists():
        for item in hunter_dir.iterdir():
            if (
                item.is_dir()
                and not item.name.startswith("_")
                and not item.name.startswith(".")
            ):
                modules[item.name] = True

    return modules


# =============================================================================
# REST ENDPOINTS
# =============================================================================


@app.get("/api/health")
async def health_check():
    """Fast liveness probe used by frontend connectivity checks."""
    try:
        storage_health = _get_cached_storage_health()
    except Exception as e:
        logger.error("Storage health probe failed: %s", e)
        storage_health = {
            "status": "INACTIVE",
            "storage_active": False,
            "reason": "Storage probe failed — check server logs",
        }

    overall = "ok"
    return {
        "status": overall,
        "ygb_root": str(PROJECT_ROOT),
        "python_phases": _HEALTH_STATIC["python_phases"],
        "impl_phases": _HEALTH_STATIC["impl_phases"],
        "hunter_modules": _HEALTH_STATIC["hunter_modules"],
        "storage_engine_status": storage_health,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/api/storage/status")
async def get_storage_status(user=Depends(require_auth)):
    """Canonical storage/DB truth endpoint.

    Returns real check results — never fake active.
    Frontend must use this as single source of truth.
    """
    return get_storage_health()


def _get_dataset_readiness() -> Dict[str, Any]:
    """Get dataset readiness status for health endpoint."""
    try:
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity,
            YGB_MIN_REAL_SAMPLES,
        )

        ok, msg = validate_dataset_integrity()
        if ok:
            return {
                "status": "READY",
                "min_samples_required": YGB_MIN_REAL_SAMPLES,
                "reason": None,
            }
        else:
            return {
                "status": "BLOCKED_REAL_DATA",
                "min_samples_required": YGB_MIN_REAL_SAMPLES,
                "reason": msg,
            }
    except Exception:
        logger.exception("_get_dataset_readiness failed")
        return {
            "status": "UNKNOWN",
            "min_samples_required": None,
            "reason": "Cannot check dataset",
        }


def _get_integration_summary() -> Dict[str, Any]:
    """Get integration status summary."""
    if not ACTIVATION_PROFILES_AVAILABLE:
        return {"status": "UNKNOWN", "reason": "activation_profiles not available"}
    try:
        ok, errors, integrations = validate_startup()
        return {
            "profile": get_profile().value,
            "startup_ok": ok,
            "integrations": {
                i.name: {"state": i.state.value, "reason": i.reason}
                for i in integrations
            },
        }
    except Exception:
        logger.exception("_get_integration_summary failed")
        return {"status": "ERROR", "reason": "Internal error"}


@app.get("/api/readiness")
async def get_readiness(user=Depends(require_auth)):
    """Dataset readiness endpoint — shows sample counts, thresholds, and blocking reasons."""
    return _get_dataset_readiness()


@app.get("/api/integration/status")
async def get_integration_status(user=Depends(require_auth)):
    """Integration status per configured service."""
    return _get_integration_summary()


@app.get("/api/cve/status")
async def get_cve_status(user=Depends(require_auth)):
    """CVE pipeline status — sources, freshness, record counts."""
    try:
        from backend.cve.cve_pipeline import get_pipeline

        pipeline = get_pipeline()
        return pipeline.get_pipeline_status()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "CVE pipeline module not found"}
    except Exception:
        logger.exception("get_cve_status failed")
        return {"status": "ERROR", "reason": "Internal error"}


@app.get("/api/cve/scheduler/health")
async def get_cve_scheduler_health(user=Depends(require_auth)):
    """CVE scheduler SLO metrics and health status."""
    try:
        from backend.cve.cve_scheduler import get_scheduler

        scheduler = get_scheduler()
        return scheduler.get_health()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "Scheduler module not found"}
    except Exception:
        logger.exception("get_cve_scheduler_health failed")
        return {"status": "ERROR", "reason": "Internal error"}


@app.get("/api/cve/pipeline/status")
async def get_cve_pipeline_full_status(user=Depends(require_auth)):
    """Full CVE pipeline status with promotion, dedup/drift, and anti-hallucination."""
    try:
        from backend.cve.cve_pipeline import get_pipeline
        from backend.cve.promotion_policy import get_promotion_policy
        from backend.cve.dedup_drift import get_dedup_drift_engine
        from backend.cve.anti_hallucination import get_anti_hallucination_validator
        from backend.cve.cve_scheduler import get_scheduler

        result = {
            "pipeline": get_pipeline().get_pipeline_status(),
            "scheduler": get_scheduler().get_health(),
            "promotion": get_promotion_policy().get_counts(),
            "dedup_drift": get_dedup_drift_engine().get_status(),
            "anti_hallucination": get_anti_hallucination_validator().get_status(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Add bridge worker status
        try:
            from backend.cve.bridge_ingestion_worker import get_bridge_worker

            result["bridge_worker"] = get_bridge_worker().get_status()
        except Exception:
            result["bridge_worker"] = {"status": "NOT_AVAILABLE"}

        return result
    except Exception:
        logger.exception("get_cve_pipeline_full_status failed")
        return {"status": "ERROR", "reason": "Internal error"}


@app.post("/api/cve/backfill")
async def trigger_cve_backfill(
    request: Request, max_samples: int = 0, user=Depends(require_auth)
):
    """One-shot backfill: rapidly ingest all CVE pipeline records into training bridge.

    Used for fast ramp of internet-only AUTO mode.
    """
    try:
        from backend.cve.cve_pipeline import get_pipeline
        from backend.cve.bridge_ingestion_worker import get_bridge_worker

        pipeline = get_pipeline()
        worker = get_bridge_worker()

        if not worker.is_bridge_loaded:
            return {
                "success": False,
                "reason": "Bridge DLL not loaded — compile native/distributed/ingestion_bridge.cpp first",
                "active_ingestion": False,
            }

        await _abort_if_disconnected(request)
        result = await asyncio.to_thread(
            worker.backfill, pipeline, max_samples=max_samples
        )
        return {
            **result,
            "active_ingestion": True,
            "threshold": 125000,
            "go_no_go": "GO"
            if result.get("bridge_verified_count", 0) >= 125000
            else "NO_GO",
        }
    except Exception:
        logger.exception("trigger_cve_backfill failed")
        return {"success": False, "reason": "Internal error", "active_ingestion": False}


@app.get("/health")
async def health_alias():
    """Alias for /api/health — some frontend pages use /health."""
    return await health_check()


@app.get("/readyz")
async def readyz():
    """Kubernetes-style readiness probe. 200 = all subsystems ok, 503 = degraded."""
    checks = {}
    ready = True
    try:
        from api.database import get_db

        db = await get_db()
        checks["database"] = "ok" if db else "unavailable"
        if not db:
            ready = False
    except Exception:
        checks["database"] = "error"
        ready = False
    checks["storage"] = "ok" if _storage_bridge else "unavailable"
    if not _storage_bridge:
        ready = False
    checks["mode"] = runtime_state.get("runtime_mode", "IDLE")
    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={"ready": ready, "checks": checks},
    )


@app.get("/api/cve/summary")
async def get_cve_summary(user=Depends(require_auth)):
    """Quick CVE summary — total records, sources, freshness."""
    try:
        from backend.cve.cve_pipeline import get_pipeline

        pipeline = get_pipeline()
        status = pipeline.get_pipeline_status()
        return {
            "total_records": status.get("total_records", 0),
            "sources_connected": status.get("sources_connected", 0),
            "last_ingest": status.get("last_ingest_at"),
            "freshness": status.get("freshness", "UNKNOWN"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except ImportError:
        return {
            "total_records": 0,
            "sources_connected": 0,
            "freshness": "NOT_AVAILABLE",
        }
    except Exception:
        logger.exception("get_cve_summary failed")
        return {
            "total_records": 0,
            "sources_connected": 0,
            "freshness": "ERROR",
            "reason": "Internal error",
        }


@app.get("/api/cve/search")
async def search_cves(request: Request, q: str = "", user=Depends(require_auth)):
    """Search CVE records by ID or keyword."""
    if not q or len(q) < 3:
        return {
            "results": [],
            "query": q,
            "reason": "Query must be at least 3 characters",
        }
    try:
        from backend.cve.cve_pipeline import get_pipeline

        pipeline = get_pipeline()
        await _abort_if_disconnected(request)
        results = await asyncio.to_thread(pipeline.search, q)
        research = None
        if not results:
            from backend.assistant.voice_runtime import run_research_analysis

            await _abort_if_disconnected(request)
            research = await asyncio.to_thread(
                run_research_analysis,
                f"{q} CVE severity NVD Vulners VulDB latest advisory",
            )
        return {
            "results": results[:50],
            "query": q,
            "total": len(results),
            "research_corroboration": research,
        }
    except ImportError:
        return {"results": [], "query": q, "reason": "CVE pipeline not available"}
    except Exception:
        logger.exception("search_cves failed")
        return {"results": [], "query": q, "reason": "Internal error"}


@app.get("/api/training/readiness")
async def get_training_readiness(user=Depends(require_auth)):
    """Training readiness truth table — per-field status with exact block reasons."""
    try:
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity,
            YGB_MIN_REAL_SAMPLES,
            STRICT_REAL_MODE,
            get_per_field_report,
        )

        # Run blocking I/O in thread pool to avoid event loop stall
        ok, msg = await asyncio.to_thread(validate_dataset_integrity)

        # Build per-field readiness
        fields = {}
        storage_health = get_storage_health()

        fields["storage_engine"] = {
            "status": "READY" if storage_health.get("storage_active") else "BLOCKED",
            "reason": None
            if storage_health.get("storage_active")
            else "Storage engine not active",
        }
        fields["dataset_source"] = {
            "status": "READY" if ok else "BLOCKED",
            "reason": None if ok else msg,
        }
        fields["strict_real_mode"] = {
            "status": "READY" if STRICT_REAL_MODE else "PARTIAL",
            "reason": None if STRICT_REAL_MODE else "STRICT_REAL_MODE=false (lab mode)",
        }
        fields["min_samples"] = {
            "status": "READY" if ok else "BLOCKED",
            "threshold": YGB_MIN_REAL_SAMPLES,
            "reason": None if ok else msg,
        }

        # Per-field bridge report (bridge counters, deficit, manifest)
        try:
            bridge_report = await asyncio.to_thread(get_per_field_report)
            fields["ingestion_bridge"] = {
                "status": bridge_report["status"],
                "bridge_loaded": bridge_report["bridge_loaded"],
                "bridge_count": bridge_report["bridge_count"],
                "bridge_verified_count": bridge_report["bridge_verified_count"],
                "deficit": bridge_report["deficit"],
                "manifest_exists": bridge_report["manifest_exists"],
                "reason": bridge_report["reason"],
            }
        except Exception:
            logger.exception("get_per_field_report failed")
            fields["ingestion_bridge"] = {
                "status": "BLOCKED",
                "reason": "Bridge report failed",
            }

        # Overall readiness
        blocked = [f for f in fields.values() if f["status"] == "BLOCKED"]
        partial = [f for f in fields.values() if f["status"] == "PARTIAL"]

        if blocked:
            overall = "BLOCKED"
        elif partial:
            overall = "PARTIAL"
        else:
            overall = "READY"

        return {
            "overall": overall,
            "fields": fields,
            "training_allowed": overall == "READY",
            "go_no_go": "GO" if overall == "READY" else "NO_GO",
            "remediation": msg if not ok else None,
            "consistency_ok": bridge_report.get("consistency_ok", False)
            if "bridge_report" in locals()
            else None,
            "authoritative_source": "bridge_state.json",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception:
        logger.exception("get_training_readiness failed")
        return {
            "overall": "BLOCKED",
            "training_allowed": False,
            "go_no_go": "NO_GO",
            "reason": "Internal error",
        }


@app.get("/api/backup/status")
async def get_backup_status_endpoint(user=Depends(require_auth)):
    """Backup strategy status — local HDD, peer replication, Google Drive."""
    try:
        from backend.storage.backup_config import get_backup_status

        return get_backup_status()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "Backup config module not found"}
    except Exception:
        logger.exception("get_backup_status_endpoint failed")
        return {"status": "ERROR", "reason": "Internal error"}


@app.get("/api/bounty/phases")
async def get_bounty_phases(user=Depends(require_auth)):
    """Get all available bounty phases."""
    phases = discover_python_phases()
    return {
        p["name"]: {
            "number": p["number"],
            "available": p["available"],
            "description": p["description"],
        }
        for p in phases
    }


# =============================================================================
# FRONTEND-REQUIRED ROUTES (phases, hunter modules, field progression)
# =============================================================================


class RunPhaseRequest(BaseModel):
    phase: str
    target: str = ""
    mode: str = "READ_ONLY"


class RunHunterRequest(BaseModel):
    module: str
    target: str = ""
    mode: str = "READ_ONLY"


class FieldApprovalRequest(BaseModel):
    approver_id: str
    reason: str


@app.get("/api/phases")
async def get_phases(user=Depends(require_auth)):
    """Get all available governance phases — frontend phase picker."""
    phases = discover_python_phases()
    return {
        "phases": [
            {
                "name": p["name"],
                "number": p["number"],
                "available": p["available"],
                "description": p["description"],
            }
            for p in phases
        ],
        "count": len(phases),
    }


@app.get("/api/hunter-modules")
async def get_hunter_modules(user=Depends(require_auth)):
    """Get available HUMANOID_HUNTER modules — frontend module picker."""
    modules = discover_hunter_modules()
    return {
        "modules": [
            {"name": name, "available": available}
            for name, available in modules.items()
        ],
        "count": len(modules),
    }


@app.post("/api/run-phase")
async def run_phase(request: RunPhaseRequest, user=Depends(require_auth)):
    """Run a governance phase. Delegates to RealPhaseRunner."""
    enforce_governed_execution(
        action_name="run_phase",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    phases = discover_python_phases()
    phase_names = [p["name"] for p in phases]
    if request.phase not in phase_names:
        raise HTTPException(
            status_code=404, detail=f"Phase '{request.phase}' not found"
        )

    run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
    active_workflows[run_id] = {
        "type": "phase_run",
        "phase": request.phase,
        "target": request.target,
        "mode": request.mode,
        "status": "started",
        "started_at": datetime.now(UTC).isoformat(),
        "owner_id": user.get("sub", ""),
    }
    return {"run_id": run_id, "phase": request.phase, "status": "started"}


@app.post("/api/run-hunter")
async def run_hunter_module(request: RunHunterRequest, user=Depends(require_auth)):
    """Run a HUMANOID_HUNTER module. Delegates to RealPhaseRunner."""
    enforce_governed_execution(
        action_name="run_hunter_module",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    modules = discover_hunter_modules()
    if request.module not in modules:
        raise HTTPException(
            status_code=404, detail=f"Hunter module '{request.module}' not found"
        )

    run_id = f"HNT-{uuid.uuid4().hex[:12].upper()}"
    active_workflows[run_id] = {
        "type": "hunter_run",
        "module": request.module,
        "target": request.target,
        "mode": request.mode,
        "status": "started",
        "started_at": datetime.now(UTC).isoformat(),
        "owner_id": user.get("sub", ""),
    }
    return {"run_id": run_id, "module": request.module, "status": "started"}


@app.get("/fields/state")
async def fields_state_endpoint(user=Depends(require_auth)):
    """Field progression state — delegates to field_progression_api."""
    try:
        from backend.api.field_progression_api import get_fields_state

        return get_fields_state()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "field_progression_api not loaded"}
    except Exception:
        logger.exception("fields_state_endpoint failed")
        return {"status": "error", "message": "Internal error"}


@app.post("/fields/approve/{field_id}")
async def fields_approve_endpoint(
    field_id: int,
    request: FieldApprovalRequest,
    user=Depends(require_auth),
):
    """Approve a field — delegates to field_progression_api.
    SECURITY: approver_id bound to authenticated user, not client body.
    """
    # Override client-supplied approver_id with authenticated identity
    auth_approver_id = user.get("sub", "")
    try:
        from backend.api.field_progression_api import approve_field

        return approve_field(field_id, auth_approver_id, request.reason)
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "field_progression_api not loaded"}
    except Exception:
        logger.exception("fields_approve_endpoint failed")
        return {"status": "error", "message": "Internal error"}


@app.post("/api/hunter/start")
async def start_hunter(request: StartWorkflowRequest, user=Depends(require_auth)):
    """Start a V1 Hunter workflow."""
    if not request.target:
        raise HTTPException(status_code=400, detail="Target URL is required")
    target = enforce_governed_execution(
        action_name="start_hunter",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
        target_url=request.target,
        validate_target_url=validate_target_url,
    )

    workflow_id = f"HNT-{uuid.uuid4().hex[:12].upper()}"

    active_workflows[workflow_id] = {
        "type": "hunter",
        "target": target,
        "status": "started",
        "stopped": False,
        "started_at": datetime.now(UTC).isoformat(),
        "steps": [],
        "owner_id": user.get("sub", ""),
    }

    # Signal scan active so auto-training yields
    if G38_AVAILABLE:
        set_scan_active(True)

    return WorkflowStartResponse(workflow_id=workflow_id, status="started")


@app.post("/api/bounty/start")
@app.post("/api/workflow/bounty/start")  # Alias for frontend compatibility
async def start_bounty(request: StartWorkflowRequest, user=Depends(require_auth)):
    """Start a Bounty Finder workflow with REAL browser automation."""
    if not request.target:
        raise HTTPException(status_code=400, detail="Target URL is required")
    target = enforce_governed_execution(
        action_name="start_bounty",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
        target_url=request.target,
        validate_target_url=validate_target_url,
        normalize_target=True,
    )

    report_id = f"RPT-{uuid.uuid4().hex[:12].upper()}"

    # Store workflow with target URL
    active_workflows[report_id] = {
        "type": "bounty",
        "target": target,
        "mode": request.mode,  # READ_ONLY or REAL
        "status": "started",
        "stopped": False,
        "started_at": datetime.now(UTC).isoformat(),
        "steps": [],
        "findings": [],
        "owner_id": user.get("sub", ""),
    }

    # Signal scan active so auto-training yields
    if G38_AVAILABLE:
        set_scan_active(True)

    logger.info("NEW WORKFLOW: %s target=%s mode=%s", report_id, target, request.mode)

    return WorkflowStartResponse(
        workflow_id=report_id, report_id=report_id, status="started"
    )


# =============================================================================
# PHASE-49 ENDPOINTS
# =============================================================================


@app.post("/api/dashboard/create")
async def create_dashboard(request: CreateDashboardRequest, user=Depends(require_auth)):
    """Create a new dashboard for the authenticated user."""
    # SECURITY: Use authenticated identity, not client-supplied user_id
    auth_user_id = user.get("sub", "")
    auth_user_name = user.get("name", user.get("email", "user"))

    dashboard_id = f"DASH-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(UTC).isoformat()

    # Create execution kernel for this dashboard
    kernel_id = f"KERN-{uuid.uuid4().hex[:12].upper()}"
    execution_kernels[kernel_id] = {
        "session_id": kernel_id,
        "state": "IDLE",
        "human_approved": False,
        "deny_reason": None,
        "audit_log": [],
        "owner_id": auth_user_id,
    }

    dashboard_states[dashboard_id] = {
        "dashboard_id": dashboard_id,
        "user_id": auth_user_id,
        "user_name": auth_user_name,
        "owner_id": auth_user_id,
        "kernel_id": kernel_id,
        "created_at": now,
        "active_panel": "USER",
    }

    return {"dashboard_id": dashboard_id, "kernel_id": kernel_id, "status": "created"}


@app.get("/api/dashboard/state")
async def get_dashboard_state(
    dashboard_id: Optional[str] = None, user=Depends(require_auth)
):
    """Get current dashboard state. Ownership-checked."""
    if dashboard_id and dashboard_id in dashboard_states:
        dash = dashboard_states[dashboard_id]
        check_resource_owner(dash, user, "dashboard", dashboard_id)
        return dash

    # No dashboard found — return error
    return {
        "error": "No dashboard found",
        "dashboard_id": None,
        "state": "DISCONNECTED",
    }


@app.get("/api/execution/state")
async def get_execution_state(
    kernel_id: Optional[str] = None, user=Depends(require_auth)
):
    """Get execution kernel state. Ownership-checked."""
    if kernel_id and kernel_id in execution_kernels:
        kernel = execution_kernels[kernel_id]
        check_resource_owner(kernel, user, "execution_kernel", kernel_id)
        return kernel

    return {"state": "IDLE", "human_approved": False}


@app.post("/api/execution/transition")
async def execution_transition(
    request: ExecutionTransitionRequest, user=Depends(require_auth)
):
    """Request a state transition on the execution kernel."""
    # Valid transitions based on G01
    valid_transitions = {
        ("IDLE", "PLAN"): "PLANNED",
        ("PLANNED", "SIMULATE"): "SIMULATED",
        ("SIMULATED", "REQUEST_APPROVAL"): "AWAIT_HUMAN",
        ("AWAIT_HUMAN", "HUMAN_APPROVE"): "EXECUTING",
        ("AWAIT_HUMAN", "HUMAN_DENY"): "STOPPED",
        ("EXECUTING", "COMPLETE"): "STOPPED",
        ("EXECUTING", "ABORT"): "STOPPED",
        ("IDLE", "ABORT"): "STOPPED",
        ("PLANNED", "ABORT"): "STOPPED",
        ("SIMULATED", "ABORT"): "STOPPED",
        ("AWAIT_HUMAN", "ABORT"): "STOPPED",
    }

    # Find the caller's kernel (not the first one in memory)
    auth_user_id = user.get("sub", "")
    kernel = None
    for kid, k in execution_kernels.items():
        if k.get("owner_id") == auth_user_id:
            kernel = k
            break

    if not kernel:
        kernel = {
            "state": "IDLE",
            "human_approved": False,
            "deny_reason": None,
            "owner_id": auth_user_id,
        }

    current_state: str = kernel.get("state", "IDLE")  # type: ignore[assignment]
    transition = request.transition

    key = (current_state, transition)
    if key in valid_transitions:
        new_state = valid_transitions[key]
        kernel["state"] = new_state

        if transition == "HUMAN_APPROVE":
            kernel["human_approved"] = True
        if transition == "HUMAN_DENY":
            kernel["deny_reason"] = request.reason

        return {
            "result": "SUCCESS",
            "from_state": current_state,
            "to_state": new_state,
            "reason": request.reason,
        }

    return {
        "result": "INVALID",
        "from_state": current_state,
        "to_state": current_state,
        "reason": f"Invalid transition {transition} from {current_state}",
    }


@app.post("/api/approval/decision")
async def submit_approval_decision(
    request: ApprovalDecisionRequest, user=Depends(require_admin)
):
    """Submit an approval decision. approver_id bound to authenticated user."""
    now = datetime.now(UTC).isoformat()
    # SECURITY: Override client-supplied approver_id with authenticated identity
    auth_approver_id = user.get("sub", "")

    decision = {
        "decision_id": f"DEC-{uuid.uuid4().hex[:16].upper()}",
        "request_id": request.request_id,
        "approved": request.approved,
        "approver_id": auth_approver_id,
        "reason": request.reason,
        "timestamp": now,
    }

    # Update any matching approval request
    if request.request_id in approval_requests:
        approval_requests[request.request_id]["status"] = (
            "APPROVED" if request.approved else "REJECTED"
        )

    return decision


@app.post("/api/targets/discover")
async def discover_targets(request: TargetDiscoveryRequest, user=Depends(require_auth)):
    """Discover potential bug bounty targets from the database."""
    try:
        targets = get_all_targets() or []  # Defense-in-depth: guard against None
        candidates = []
        for t in targets:
            candidate = {
                "candidate_id": f"TGT-{t.get('id', uuid.uuid4().hex[:16].upper())}",
                "program_name": t.get("program_name", "Unknown"),
                "source": t.get("platform", "DATABASE"),
                "scope_summary": t.get("scope", ""),
                "payout_tier": t.get("payout_tier", "UNKNOWN"),
                "report_density": "UNKNOWN",
                "is_public": True,
                "requires_invite": False,
                "discovered_at": t.get("created_at", datetime.now(UTC).isoformat()),
            }
            candidates.append(candidate)

        # Filter based on request
        filtered = [c for c in candidates if c["is_public"] or not request.public_only]

        return {
            "result_id": f"DIS-{uuid.uuid4().hex[:16].upper()}",
            "candidates": filtered,
            "total_found": len(candidates),
            "filtered_count": len(candidates) - len(filtered),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.exception("Error discovering targets")
        return {
            "result_id": f"DIS-{uuid.uuid4().hex[:16].upper()}",
            "candidates": [],
            "total_found": 0,
            "filtered_count": 0,
            "error": "Internal error while discovering targets",
            "timestamp": datetime.now(UTC).isoformat(),
        }


# =============================================================================
# SCOPE VALIDATION & TARGET SESSION MANAGEMENT
# =============================================================================

# In-memory target session state
target_sessions: Dict[str, Dict[str, Any]] = {}
scope_violations: List[Dict[str, Any]] = []


@app.post("/scope/validate")
async def validate_scope(request: Request, user=Depends(require_auth)):
    """Validate a scope definition against security rules. Auth required."""
    data = await request.json()
    target_url = data.get("target_url", "")
    now = datetime.now(UTC).isoformat()

    # Use robust SSRF-safe validation from auth_guard
    is_valid, violations = validate_target_url(target_url)

    return {
        "valid": is_valid,
        "target_url": target_url,
        "violations": violations,
        "validated_at": now,
    }


@app.post("/target/start")
async def start_target_session(request: Request, user=Depends(require_auth)):
    """Start a target scanning session. Auth required. Scope validation enforced."""
    data = await request.json()
    target_url = data.get("target_url", "")
    scope_definition = data.get("scope_definition", {})
    mode = data.get("mode", "READ_ONLY")
    now = datetime.now(UTC).isoformat()

    # Enforce scope validation before starting session (SSRF protection)
    is_safe, violations = validate_target_url(target_url)
    if not is_safe:
        return {
            "error": "Scope validation failed",
            "started": False,
            "violations": violations,
        }

    session_id = f"TSESS-{uuid.uuid4().hex[:12].upper()}"
    target_sessions[session_id] = {
        "session_id": session_id,
        "target_url": target_url,
        "scope_definition": scope_definition,
        "mode": mode,
        "status": "ACTIVE",
        "started_at": now,
        "stopped_at": None,
        "violations": [],
        "findings_count": 0,
        "owner_id": user.get("sub", ""),
    }

    # Signal scan active so auto-training yields
    if G38_AVAILABLE:
        set_scan_active(True)

    return {
        "started": True,
        "session_id": session_id,
        "target_url": target_url,
        "mode": mode,
        "started_at": now,
    }


@app.post("/target/stop")
async def stop_target_session(request: Request, user=Depends(require_auth)):
    """Stop an active target scanning session."""
    data = await request.json()
    session_id = data.get("session_id", "")
    now = datetime.now(UTC).isoformat()

    # Guard: nonexistent session → structured error, not bare 404
    session = target_sessions.get(session_id)
    workflow = active_workflows.get(session_id)
    if session is None and workflow is None:
        return {
            "stopped": False,
            "error": f"Session {session_id!r} not found",
            "session_id": session_id,
        }

    if workflow is not None:
        check_resource_owner(workflow, user, "workflow", session_id)
        workflow["status"] = "STOPPED"
        workflow["stopped"] = True
        workflow["stopped_at"] = now

    if session is None:
        return {
            "stopped": True,
            "session_id": session_id,
            "stopped_at": now,
            "duration_seconds": 0,
        }

    # Ownership check: only owner or admin can stop a session
    check_resource_owner(session, user, "target_session", session_id)
    session["status"] = "STOPPED"
    session["stopped_at"] = now

    # Clear scan-active flag if no other sessions remain active
    if G38_AVAILABLE:
        still_active = any(s["status"] == "ACTIVE" for s in target_sessions.values())
        if not still_active:
            set_scan_active(False)

    # Compute real duration from timestamps
    duration = 0
    started_at = session.get("started_at")
    if started_at:
        try:
            start_dt = datetime.fromisoformat(started_at)
            stop_dt = datetime.fromisoformat(now)
            duration = int((stop_dt - start_dt).total_seconds())
        except (ValueError, TypeError):
            logger.warning(
                "Failed to parse session timestamps for %s",
                session_id,
                exc_info=True,
            )

    return {
        "stopped": True,
        "session_id": session_id,
        "stopped_at": now,
        "duration_seconds": duration,
    }


@app.get("/target/status")
async def get_target_status(user=Depends(require_auth)):
    """Get status of target sessions. Non-admin users see only their own."""
    is_admin = user.get("role") == "admin"
    uid = user.get("sub", "")

    if is_admin:
        active = [s for s in target_sessions.values() if s["status"] == "ACTIVE"]
        stopped = [s for s in target_sessions.values() if s["status"] == "STOPPED"]
    else:
        active = [
            s
            for s in target_sessions.values()
            if s["status"] == "ACTIVE" and s.get("owner_id") == uid
        ]
        stopped = [
            s
            for s in target_sessions.values()
            if s["status"] == "STOPPED" and s.get("owner_id") == uid
        ]

    return {
        "active_sessions": active,
        "stopped_sessions": stopped[-10:],  # Last 10 stopped
        "total_active": len(active),
        "total_stopped": len(stopped),
        "violations": scope_violations[-20:] if is_admin else [],
    }


# NOTE: /api/voice/parse is defined below under DUAL-MODE VOICE ENDPOINTS
# The duplicate simple route has been removed to avoid ambiguity.


@app.post("/api/autonomy/session")
async def create_autonomy_session(
    request: AutonomySessionRequest, user=Depends(require_auth)
):
    """Create an autonomy session."""
    now = datetime.now(UTC)
    session_id = f"AUT-{uuid.uuid4().hex[:16].upper()}"

    # Calculate expiry for AUTONOMOUS_FIND mode
    expires_at = None
    if request.mode == "AUTONOMOUS_FIND" and request.duration_hours > 0:
        max_hours = min(request.duration_hours, 12)  # Cap at 12 hours
        from datetime import timedelta

        expires_at = (now + timedelta(hours=max_hours)).isoformat()

    # Determine blocked actions based on mode
    blocked = []
    if request.mode == "AUTONOMOUS_FIND":
        blocked = ["EXPLOIT", "SUBMISSION", "STATE_CHANGE", "BROWSER_ACTION"]
    elif request.mode == "READ_ONLY":
        blocked = ["EXPLOIT", "SUBMISSION", "STATE_CHANGE", "BROWSER_ACTION"]
    elif request.mode == "MOCK":
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=400,
            content={
                "error": "MOCK mode is disabled. Use READ_ONLY, AUTONOMOUS_FIND, or REAL."
            },
        )

    session = {
        "session_id": session_id,
        "mode": request.mode,
        "status": "ACTIVE",
        "duration_hours": request.duration_hours,
        "started_at": now.isoformat(),
        "expires_at": expires_at,
        "human_enabled": request.mode == "REAL",
        "actions_blocked": blocked,
    }

    autonomy_sessions[session_id] = session
    return session


# =============================================================================
# G38 AUTO-TRAINING ENDPOINTS
# =============================================================================


@app.get("/api/g38/status")
async def get_g38_status():
    """Get G38 auto-training status."""
    if not G38_AVAILABLE:
        return {"available": False, "error": "G38 modules not loaded"}

    trainer = get_auto_trainer()
    status = trainer.get_status()

    # Add guard verification
    guards_ok, guards_msg = verify_all_guards()
    pretraining_ok, pretraining_msg = verify_pretraining_guards()
    mode_a_status, mode_a_msg = get_mode_a_status()

    return {
        "available": True,
        "auto_training": {
            "state": status["state"],
            "is_training": status["is_training"],
            "epoch": status["epoch"],
            "total_epochs": status.get("total_epochs", 0),
            "total_completed": status.get("total_completed", 0),
            "progress": status.get("progress", 0),
            "idle_seconds": status["idle_seconds"],
            "power_connected": status["power_connected"],
            "scan_active": status["scan_active"],
            "gpu_available": status["gpu_available"],
            "events_count": status["events_count"],
            "last_event": status["last_event"],
            # Real GPU + training metrics
            "gpu_mem_allocated_mb": status.get("gpu_mem_allocated_mb", 0),
            "gpu_mem_reserved_mb": status.get("gpu_mem_reserved_mb", 0),
            "last_loss": status.get("last_loss", 0),
            "last_accuracy": status.get("last_accuracy", 0),
            "samples_per_sec": status.get("samples_per_sec", 0),
            "dataset_size": status.get("dataset_size", 0),
            "training_mode": status.get("training_mode", "MANUAL"),
        },
        "guards": {
            "main_guards": len(ALL_GUARDS),
            "all_verified": guards_ok,
            "message": guards_msg,
        },
        "pretraining": {
            "verified": pretraining_ok,
            "message": pretraining_msg,
        },
        "mode": {
            "mode_a_status": mode_a_status.value,
            "message": mode_a_msg,
        },
        "training_summary": get_training_mode_summary() if G38_AVAILABLE else None,
    }


@app.get("/api/g38/events")
async def get_g38_events(limit: int = 50, user=Depends(require_auth)):
    """Get recent G38 training events."""
    if not G38_AVAILABLE:
        return {"events": [], "error": "G38 modules not loaded"}

    trainer = get_auto_trainer()
    events = trainer.events[-limit:] if trainer.events else []

    return {
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "timestamp": e.timestamp,
                "details": e.details,
                "idle_seconds": e.idle_seconds,
                "gpu_used": e.gpu_used,
                "epoch": e.epoch,
            }
            for e in events
        ],
        "total": len(trainer.events),
    }


@app.post("/api/g38/abort")
async def abort_g38_training(user=Depends(require_admin)):
    """Abort current G38 training."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}

    trainer = get_auto_trainer()
    if getattr(trainer, "_continuous_mode", False):
        result = stop_continuous_training()
        thread_alive = result.get("thread_alive", False)
        return {
            "success": result.get("stop_requested", False),
            "state": trainer.state.value,
            "message": (
                "Continuous training stop requested; worker thread still draining"
                if thread_alive
                else "Continuous training stopped"
            ),
        }
    result = trainer.abort_training()

    return {
        "success": result.get("aborted", False),
        "state": trainer.state.value,
        "message": "Training abort requested"
        if result.get("aborted")
        else result.get("reason", "No training in progress"),
    }


@app.post("/api/g38/start")
async def start_g38_training(epochs: int = 0, user=Depends(require_admin)):
    """Start G38 training in continuous mode (default infinite)."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}

    trainer = get_auto_trainer()

    # Check if already training
    if trainer.is_training:
        return {
            "success": False,
            "error": "Training already in progress",
            "state": trainer.state.value,
        }

    result = start_continuous_training(target_epochs=max(0, epochs))
    if not result.get("started", False):
        return {
            "success": False,
            "error": result.get("reason", "Failed to start training"),
            "state": result.get("state", "ERROR"),
        }
    target_msg = "infinite" if epochs <= 0 else str(epochs)
    return {
        "success": True,
        "message": (
            f"Continuous training started (target_epochs={target_msg}). "
            "Training continues even during user activity until stopped or target reached."
        ),
        "state": "TRAINING",
        "training_mode": "CONTINUOUS",
        "target_epochs": epochs if epochs > 0 else 0,
    }


# =============================================================================
# ADMIN PANEL TRAINING/GPU ROUTES
# (Canonical — single definition per route. No duplicates.)
# =============================================================================

_gpu_seq_id = 0


@app.get("/gpu/status")
async def gpu_status(user=Depends(require_auth)):
    """GPU status — real GPU info with nvidia-smi metrics.

    Returns null + error_reason for any field that cannot be read from
    real hardware at runtime. Never returns fake zeros.
    """
    seq_id = runtime_state.increment("gpu_seq_id")

    result: Dict[str, Any] = {
        "gpu_available": False,
        "device_name": None,
        "utilization_percent": None,
        "memory_allocated_mb": None,
        "memory_reserved_mb": None,
        "memory_total_mb": None,
        "temperature": None,
        "compute_capability": None,
        "cuda_version": None,
        "driver_version": None,
        "tensor_core_support": None,
        "error_reason": None,
        "sequence_id": _gpu_seq_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        import torch

        if not torch.cuda.is_available():
            result["error_reason"] = "CUDA not available on this system"
            return Response(
                content=json.dumps(result),
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )
        result["gpu_available"] = True
        result["device_name"] = torch.cuda.get_device_name(0)
        result["memory_allocated_mb"] = round(
            torch.cuda.memory_allocated() / 1024 / 1024, 2
        )
        result["memory_reserved_mb"] = round(
            torch.cuda.memory_reserved() / 1024 / 1024, 2
        )
        props = torch.cuda.get_device_properties(0)
        result["memory_total_mb"] = round(props.total_memory / 1024 / 1024, 2)
        cap = torch.cuda.get_device_capability(0)
        result["compute_capability"] = f"{cap[0]}.{cap[1]}"
        # Tensor cores available on compute capability >= 7.0
        result["tensor_core_support"] = cap[0] >= 7
        # CUDA runtime version
        result["cuda_version"] = torch.version.cuda
    except Exception as e:
        result["error_reason"] = f"torch GPU probe failed: {type(e).__name__}"

    # nvidia-smi for utilization, temperature, and driver version
    try:
        import subprocess

        smi_output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu,driver_version",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
            text=True,
        ).strip()
        parts = smi_output.split(",")
        if len(parts) >= 2:
            result["utilization_percent"] = float(parts[0].strip())
            result["temperature"] = float(parts[1].strip())
        if len(parts) >= 3:
            result["driver_version"] = parts[2].strip()
    except Exception as e:
        if result["error_reason"] is None:
            result["error_reason"] = f"nvidia-smi unavailable: {type(e).__name__}"

    return Response(
        content=json.dumps(result),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/training/status")
async def training_status(user=Depends(require_auth)):
    """Training status — full trainer state."""
    if not G38_AVAILABLE:
        return {"available": False, "is_training": False, "error": "G38 not available"}
    trainer = get_auto_trainer()
    return trainer.get_status()


@app.post("/training/start")
async def training_start(epochs: int = 0, user=Depends(require_admin)):
    """Start continuous GPU training (default infinite)."""
    enforce_governed_execution(
        action_name="training_start",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    trainer = get_auto_trainer()
    if trainer.is_training:
        return {
            "success": False,
            "error": "Training already in progress",
            "state": trainer.state.value,
        }
    result = start_continuous_training(target_epochs=max(0, epochs))
    if not result.get("started", False):
        return {
            "success": False,
            "error": result.get("reason", "Failed to start training"),
            "state": result.get("state", "ERROR"),
        }
    target_msg = "infinite" if epochs <= 0 else str(epochs)
    return {
        "success": True,
        "message": (
            f"Continuous training started (target_epochs={target_msg}). "
            "Training continues even during user activity until stopped or target reached."
        ),
        "state": "TRAINING",
        "training_mode": "CONTINUOUS",
        "target_epochs": epochs if epochs > 0 else 0,
    }


@app.post("/training/stop")
async def training_stop(user=Depends(require_admin)):
    """Stop training immediately."""
    enforce_governed_execution(
        action_name="training_stop",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    trainer = get_auto_trainer()
    if getattr(trainer, "_continuous_mode", False):
        result = stop_continuous_training()
        thread_alive = result.get("thread_alive", False)
        return {
            "success": result.get("stop_requested", False),
            "message": (
                "Continuous training stop requested; worker thread still draining"
                if thread_alive
                else "Continuous training stopped"
            ),
            "state": trainer.state.value,
        }
    result = trainer.abort_training()
    return {
        "success": result.get("aborted", False),
        "message": "Training stopped"
        if result.get("aborted")
        else "No training in progress",
        "state": trainer.state.value,
    }


@app.post("/training/continuous")
async def training_continuous(request: Request, user=Depends(require_admin)):
    """Toggle continuous training mode."""
    enforce_governed_execution(
        action_name="training_continuous",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    data = await request.json()
    enabled = data.get("enabled", False)
    target_epochs = data.get("target_epochs", 0)
    if enabled:
        start_continuous_training(target_epochs=target_epochs)
        return {"success": True, "message": "Continuous mode enabled"}
    else:
        stop_continuous_training()
        return {"success": True, "message": "Continuous mode disabled"}


@app.post("/training/interval")
async def training_interval(request: Request, user=Depends(require_admin)):
    """Set training check interval via admin panel."""
    enforce_governed_execution(
        action_name="training_interval",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    if not G38_AVAILABLE:
        raise HTTPException(status_code=503, detail="G38 not available")
    data = await request.json()
    interval = data.get("interval", 30)
    trainer = get_auto_trainer()
    trainer.CHECK_INTERVAL_SECONDS = max(10, min(interval, 3600))
    return {"success": True, "interval": trainer.CHECK_INTERVAL_SECONDS}


@app.get("/api/g38/guards")
async def get_g38_guards(user=Depends(require_auth)):
    """Get all G38 guard statuses."""
    if not G38_AVAILABLE:
        return {"guards": [], "error": "G38 modules not loaded"}

    guards = []
    for guard in ALL_GUARDS:
        result, msg = guard()
        guards.append(
            {
                "name": guard.__name__,
                "returns_false": not result,
                "message": msg,
            }
        )

    return {
        "guards": guards,
        "total": len(guards),
        "all_passing": all(not g["returns_false"] for g in guards),
    }


@app.get("/api/g38/reports")
async def get_g38_training_reports(user=Depends(require_auth)):
    """Get G38 training reports."""
    reports_dir = PROJECT_ROOT / "reports" / "g38_training"

    if not reports_dir.exists():
        return {"reports": [], "count": 0}

    reports = []

    # Find all summary files
    for summary_file in sorted(
        reports_dir.glob("training_summary_*.txt"), reverse=True
    ):
        session_id = summary_file.stem.replace("training_summary_", "")

        # Find corresponding learned and not_learned files
        learned_file = reports_dir / f"learned_features_{session_id}.json"
        not_learned_file = reports_dir / f"not_learned_yet_{session_id}.txt"

        report = {
            "session_id": session_id,
            "summary_file": summary_file.name,
            "summary_content": summary_file.read_text()[:500] + "..."
            if summary_file.exists()
            else None,
            "has_learned_features": learned_file.exists(),
            "has_not_learned": not_learned_file.exists(),
            "created_at": datetime.fromtimestamp(
                summary_file.stat().st_mtime
            ).isoformat(),
        }

        # Read learned features JSON if exists
        if learned_file.exists():
            import json

            try:
                report["learned_features"] = json.loads(learned_file.read_text())
            except Exception:
                logger.exception("Failed to parse learned features JSON")
                report["learned_features"] = None

        reports.append(report)

    return {
        "reports": reports[:20],  # Last 20 reports
        "count": len(reports),
    }


@app.get("/api/g38/reports/latest")
async def get_g38_latest_report(user=Depends(require_auth)):
    """Get the latest G38 training report."""
    reports_dir = PROJECT_ROOT / "reports" / "g38_training"

    if not reports_dir.exists():
        return {"available": False, "error": "No reports directory"}

    # Find latest summary
    summaries = sorted(reports_dir.glob("training_summary_*.txt"), reverse=True)

    if not summaries:
        return {"available": False, "error": "No reports found"}

    latest = summaries[0]
    session_id = latest.stem.replace("training_summary_", "")

    # Read all files for this session
    learned_file = reports_dir / f"learned_features_{session_id}.json"
    not_learned_file = reports_dir / f"not_learned_yet_{session_id}.txt"

    import json

    return {
        "available": True,
        "session_id": session_id,
        "summary": latest.read_text() if latest.exists() else None,
        "learned_features": json.loads(learned_file.read_text())
        if learned_file.exists()
        else None,
        "not_learned": not_learned_file.read_text()
        if not_learned_file.exists()
        else None,
        "created_at": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
    }


# =============================================================================
# ADDITIONAL TRAINING ENDPOINTS (non-duplicate)
# =============================================================================


@app.post("/training/continuous/stop")
async def stop_24_7_training(user=Depends(require_admin)):
    """Stop 24/7 continuous training."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    result = stop_continuous_training()
    return {"success": result.get("stop_requested", False), **result}


@app.get("/training/progress")
async def training_progress(user=Depends(require_auth)):
    """Get real-time training progress. Returns null if unavailable."""
    mgr = get_training_state_manager()
    metrics = mgr.get_training_progress()
    return metrics.to_dict()


# _stream_seq_id lives in runtime_state ("stream_seq_id"), initialized at import


@app.websocket("/training/stream")
async def training_stream(websocket: WebSocket):
    """Live training telemetry stream for frontend dashboard."""
    runtime_state.increment("stream_seq_id")
    user = await ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()

    if not G38_AVAILABLE:
        await websocket.send_json(
            {
                "error": "G38 modules not loaded",
                "stalled": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await websocket.close(code=1011, reason="G38 unavailable")
        return

    trainer = get_auto_trainer()
    mgr = get_training_state_manager()
    prev_samples_processed = -1
    unchanged_ticks = 0

    WS_SESSION_TIMEOUT = 14400  # 4 hours max per WS session
    _ws_start = time.monotonic()

    try:
        while True:
            if time.monotonic() - _ws_start > WS_SESSION_TIMEOUT:
                logger.info("Training stream session timeout (%ds)", WS_SESSION_TIMEOUT)
                await websocket.close(code=1000, reason="Session timeout")
                break
            seq = runtime_state.increment("stream_seq_id")
            status = trainer.get_status()
            gpu_metrics = mgr.get_gpu_metrics()

            is_training = bool(status.get("is_training", False))

            # Batch telemetry from real trainer internals (no synthetic values).
            total_batches = int(getattr(trainer, "_last_total_batches", 0) or 0)
            batch_index = int(getattr(trainer, "_last_batch_index", 0) or 0)
            epoch_samples = int(getattr(trainer, "_last_epoch_samples", 0) or 0)
            samples_processed = int(getattr(trainer, "_real_samples_processed", 0) or 0)
            total_samples = int(status.get("dataset_size", 0) or 0)

            if samples_processed == prev_samples_processed:
                unchanged_ticks += 1
            else:
                unchanged_ticks = 0
            prev_samples_processed = samples_processed

            stalled = is_training and unchanged_ticks >= 10

            # GPU utilization fraction expected by frontend [0,1].
            gpu_usage_percent = gpu_metrics.get("gpu_usage_percent")
            if gpu_usage_percent is not None:
                gpu_utilization = max(0.0, min(float(gpu_usage_percent) / 100.0, 1.0))
            else:
                gpu_memory_total = float(gpu_metrics.get("gpu_memory_total_mb") or 0.0)
                gpu_memory_used = float(
                    gpu_metrics.get("gpu_memory_used_mb")
                    or status.get("gpu_mem_reserved_mb")
                    or 0.0
                )
                gpu_utilization = (
                    max(0.0, min(gpu_memory_used / gpu_memory_total, 1.0))
                    if gpu_memory_total > 0
                    else None
                )

            # When idle, return null for telemetry — no fake progress.
            if is_training:
                samples_per_sec = float(status.get("samples_per_sec", 0.0) or 0.0)
                loss = float(status.get("last_loss", 0.0) or 0.0)
                accuracy = float(status.get("last_accuracy", 0.0) or 0.0)
                gpu_temp = float(gpu_metrics.get("temperature") or 0.0)
                gpu_mem = float(status.get("gpu_mem_allocated_mb", 0.0) or 0.0)
            else:
                samples_per_sec = None
                loss = None
                accuracy = None
                gpu_temp = (
                    float(gpu_metrics.get("temperature") or 0.0)
                    if gpu_metrics.get("temperature") is not None
                    else None
                )
                gpu_mem = None

            eta_seconds = None
            if is_training and total_samples > 0 and (samples_per_sec or 0) > 0:
                remaining = max(total_samples - epoch_samples, 0)
                eta_seconds = remaining / samples_per_sec

            lr = None
            if is_training:
                optimizer = getattr(trainer, "_gpu_optimizer", None)
                try:
                    if optimizer and optimizer.param_groups:
                        lr = float(optimizer.param_groups[0].get("lr", 0.0) or 0.0)
                except Exception:
                    lr = None

            frame = {
                "epoch": int(status.get("epoch", 0) or 0),
                "batch": batch_index,
                "total_batches": total_batches,
                "samples_processed": samples_processed,
                "total_samples": total_samples,
                "samples_per_sec": samples_per_sec,
                "gpu_utilization": gpu_utilization,
                "gpu_memory_mb": gpu_mem,
                "gpu_temp": gpu_temp,
                "loss": loss,
                "running_accuracy": accuracy,
                "learning_rate": lr,
                "eta_seconds": eta_seconds,
                "stalled": stalled,
                "sequence_id": seq,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await websocket.send_json(frame)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("Training stream websocket disconnected")
    except Exception:
        logger.exception("Training stream websocket error")
        try:
            await websocket.send_json(
                {
                    "error": "Training stream failed",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            logger.warning(
                "Training stream websocket error notification failed",
                exc_info=True,
            )


# _dashboard_seq_id lives in runtime_state ("dashboard_seq_id"), initialized at import


@app.websocket("/training/dashboard")
async def training_dashboard(websocket: WebSocket):
    """Live training dashboard stream for auto-training-dashboard.tsx.

    Emits DashboardFrame-shaped JSON at 1-second cadence.
    Auth: Sec-WebSocket-Protocol bearer.<jwt> only (no query tokens).
    Close 4001 on auth failure.
    """
    runtime_state.increment("dashboard_seq_id")
    user = await ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Accept with the bearer subprotocol so the browser sees the handshake
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    accept_proto = None
    for proto in protocols.split(","):
        proto = proto.strip()
        if proto.startswith("bearer."):
            accept_proto = proto
            break
    await websocket.accept(subprotocol=accept_proto)

    if not G38_AVAILABLE:
        await websocket.send_json(
            {
                "error": "G38 modules not loaded",
                "stalled": True,
                "mode": "idle",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await websocket.close(code=1011, reason="G38 unavailable")
        return

    trainer = get_auto_trainer()
    mgr = get_training_state_manager()
    prev_samples = -1
    unchanged_ticks = 0

    WS_SESSION_TIMEOUT = 14400  # 4 hours max
    _ws_start = time.monotonic()

    try:
        while True:
            if time.monotonic() - _ws_start > WS_SESSION_TIMEOUT:
                logger.info("Dashboard session timeout (%ds)", WS_SESSION_TIMEOUT)
                await websocket.close(code=1000, reason="Session timeout")
                break
            seq = runtime_state.increment("dashboard_seq_id")
            status = trainer.get_status()
            gpu_metrics = mgr.get_gpu_metrics()

            is_training = bool(status.get("is_training", False))

            # Stall detection
            samples_processed = int(getattr(trainer, "_real_samples_processed", 0) or 0)
            if samples_processed == prev_samples:
                unchanged_ticks += 1
            else:
                unchanged_ticks = 0
            prev_samples = samples_processed
            stalled = is_training and unchanged_ticks >= 10

            # GPU utilization [0,1]
            gpu_usage_percent = gpu_metrics.get("gpu_usage_percent")
            if gpu_usage_percent is not None:
                gpu_utilization = max(0.0, min(float(gpu_usage_percent) / 100.0, 1.0))
            else:
                mem_total = float(gpu_metrics.get("gpu_memory_total_mb") or 0.0)
                mem_used = float(
                    gpu_metrics.get("gpu_memory_used_mb")
                    or status.get("gpu_mem_reserved_mb")
                    or 0.0
                )
                gpu_utilization = (
                    max(0.0, min(mem_used / mem_total, 1.0)) if mem_total > 0 else None
                )

            total_samples = int(status.get("dataset_size", 0) or 0)
            epoch_samples = int(getattr(trainer, "_last_epoch_samples", 0) or 0)

            # When idle, return null for telemetry — no fake progress.
            if is_training:
                samples_per_sec = float(status.get("samples_per_sec", 0.0) or 0.0)
                loss_val = float(status.get("last_loss", 0.0) or 0.0)
                accuracy_val = float(status.get("last_accuracy", 0.0) or 0.0)
                gpu_temp = float(gpu_metrics.get("temperature") or 0.0)
                vram_used = float(
                    gpu_metrics.get("gpu_memory_used_mb")
                    or status.get("gpu_mem_allocated_mb")
                    or 0.0
                )
            else:
                samples_per_sec = None
                loss_val = None
                accuracy_val = None
                gpu_temp = (
                    float(gpu_metrics.get("temperature") or 0.0)
                    if gpu_metrics.get("temperature") is not None
                    else None
                )
                vram_used = None

            eta_seconds = None
            if is_training and total_samples > 0 and (samples_per_sec or 0) > 0:
                remaining = max(total_samples - epoch_samples, 0)
                eta_seconds = remaining / samples_per_sec

            epoch = int(status.get("epoch", 0) or 0)
            total_epochs = int(status.get("total_epochs", 0) or 0)

            # Active field and queue from trainer
            active_field = getattr(trainer, "_current_field", None) or "default"
            field_queue_raw = getattr(trainer, "_field_queue", None) or []
            queue = []
            for fq in field_queue_raw:
                if isinstance(fq, dict):
                    queue.append(
                        {
                            "field_name": fq.get("field_name", "unknown"),
                            "priority": fq.get("priority", 0),
                            "status": fq.get("status", "queued"),
                            "best_accuracy": float(fq.get("best_accuracy", 0.0) or 0.0),
                            "epochs_completed": int(fq.get("epochs_completed", 0) or 0),
                        }
                    )

            # Mode
            if is_training:
                mode = "training"
            elif stalled:
                mode = "monitoring"
            else:
                mode = "idle"

            frame = {
                "active_field": active_field,
                "queue": queue,
                "gpu_utilization": gpu_utilization,
                "gpu_temp": gpu_temp,
                "vram_used_mb": vram_used,
                "samples_per_sec": samples_per_sec,
                "eta_seconds": eta_seconds,
                "epoch": epoch,
                "total_epochs": total_epochs,
                "world_size": int(getattr(trainer, "_world_size", 1) or 1),
                "auto_mode": bool(getattr(trainer, "_continuous_mode", False)),
                "loss": loss_val,
                "accuracy": accuracy_val,
                "stalled": stalled,
                "mode": mode,
                "sequence_id": seq,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await websocket.send_json(frame)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("Training dashboard websocket disconnected")
    except Exception:
        logger.exception("Training dashboard websocket error")
        try:
            await websocket.send_json(
                {
                    "error": "Dashboard stream failed",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            logger.warning(
                "Training dashboard websocket error notification failed",
                exc_info=True,
            )


@app.get("/dataset/stats")
async def dataset_stats(user=Depends(require_auth)):
    """Get training dataset statistics."""
    if not G38_AVAILABLE:
        return {"available": False, "error": "G38 modules not loaded"}

    trainer = get_auto_trainer()
    if trainer._gpu_dataset_stats:
        return {
            "available": True,
            **trainer._gpu_dataset_stats,
        }

    # Try to get stats from dataset loader directly
    try:
        from impl_v1.training.data.real_dataset_loader import validate_dataset_integrity

        valid, msg = validate_dataset_integrity()
        return {
            "available": valid,
            "message": msg,
            "source": "real_dataset_loader",
        }
    except Exception as e:
        logger.exception("Error in dataset_stats")
        return {"available": False, "error": "Internal error"}


# =============================================================================


# =============================================================================
# HDD STORAGE ENGINE ENDPOINTS (NEW)
# =============================================================================


@app.get("/api/storage/stats")
def storage_stats_endpoint(user=Depends(require_auth)):
    """Get HDD storage engine statistics."""
    return get_storage_stats()


@app.get("/api/storage/lifecycle")
def lifecycle_status_endpoint(user=Depends(require_auth)):
    """Get lifecycle status and deletion preview."""
    return get_lifecycle_status()


@app.get("/api/storage/disk")
def disk_status_endpoint(user=Depends(require_auth)):
    """Get HDD disk usage, alerts, and health."""
    return get_disk_status()


@app.get("/api/storage/delete-preview")
def delete_preview_endpoint(
    entity_type: Optional[str] = None, user=Depends(require_admin)
):
    """Preview which entities would be auto-deleted."""
    return get_delete_preview(entity_type)


@app.get("/api/video/list")
def video_list_endpoint(user_id: Optional[str] = None, user=Depends(require_auth)):
    """List stored videos. Non-admin users can only see their own videos."""
    # IDOR: Force user_id to authenticated user for non-admins
    if user.get("role") != "admin":
        user_id = user.get("sub")
    return list_videos(user_id)


@app.post("/api/video/token")
async def video_token_endpoint(request: Request, user=Depends(require_auth)):
    """Generate a signed video streaming token. Auth required."""
    body = await request.json()
    # IDOR: Force user_id to authenticated user for non-admins
    requested_user_id = body.get("user_id", "")
    if user.get("role") != "admin":
        requested_user_id = user.get("sub", "")
    return get_video_stream_token(
        requested_user_id,
        body.get("session_id", ""),
        body.get("filename", "video.webm"),
    )


# =============================================================================
# AUTH / LOGIN / DEVICE TRACKING ENDPOINTS
# =============================================================================

_ALLOW_PASSWORD_LOGIN = os.getenv("ALLOW_PASSWORD_LOGIN", "false").lower() == "true"
_AUTH_COOKIE_MAX_AGE_SECONDS = int(os.getenv("AUTH_COOKIE_MAX_AGE_SECONDS", "3600"))
_ADMIN_SESSION_COOKIE_NAME = "ygb_admin_session"
_SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _temporary_auth_user(auth_via: str = "temporary_http") -> Dict[str, Any]:
    return build_temporary_auth_user(auth_via)


def _temporary_auth_me_payload(user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    temp_user = dict(user or _temporary_auth_user())
    return {
        "user_id": temp_user.get("sub"),
        "name": temp_user.get("name"),
        "email": temp_user.get("email"),
        "phone_number": None,
        "role": temp_user.get("role", "admin"),
        "github_login": None,
        "google_email": None,
        "google_picture": None,
        "avatar_url": None,
        "auth_provider": temp_user.get("auth_provider", "temporary_bypass"),
        "session_id": temp_user.get("session_id"),
        "timestamp": datetime.now(UTC).isoformat(),
        "temporary_bypass": True,
    }


def _temporary_auth_profile_payload(
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    temp_user = dict(user or _temporary_auth_user())
    return {
        "success": True,
        "user": {
            "id": temp_user.get("sub"),
            "name": temp_user.get("name"),
            "email": temp_user.get("email"),
            "phone_number": None,
            "role": temp_user.get("role", "admin"),
        },
        "session_id": temp_user.get("session_id"),
        "temporary_bypass": True,
    }


def _is_secure_request(req: Request) -> bool:
    frontend_url = _env_oauth_value("FRONTEND_URL", "http://localhost:3000")
    return req.url.scheme == "https" or frontend_url.startswith("https://")


def _set_auth_cookies(resp: Response, req: Request, token: str) -> None:
    secure = _is_secure_request(req)
    csrf_token = generate_csrf_token()
    # Legacy browser-readable cookie rule was: cookie_name not in ("ygb_profile", "ygb_token").
    # The active flow now issues HttpOnly auth via ygb_auth and a readable CSRF cookie via ygb_csrf.
    resp.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=_AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    resp.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=_AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )
    # Clear legacy browser-readable auth cookies as part of the migration.
    resp.delete_cookie(LEGACY_AUTH_COOKIE_NAME, path="/")
    resp.delete_cookie("ygb_session_id", path="/")
    resp.delete_cookie("ygb_profile", path="/")


def _set_cookies(resp: Response, req: Request, token: str) -> None:
    """Backward-compatible auth cookie helper name used by security tests."""
    _set_auth_cookies(resp, req, token)


def _clear_auth_cookies(resp: Response, req: Request) -> None:
    secure = _is_secure_request(req)
    for cookie_name in (
        AUTH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
        LEGACY_AUTH_COOKIE_NAME,
        "ygb_session_id",
        "ygb_profile",
    ):
        resp.delete_cookie(
            cookie_name,
            path="/",
            secure=secure,
            samesite="lax",
        )


def _allowed_cookie_origins() -> set[str]:
    frontend_url = _env_oauth_value("FRONTEND_URL", "http://localhost:3000")
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
    if frontend_url:
        origins.add(frontend_url.rstrip("/"))
    for value in os.getenv("YGB_ALLOWED_ORIGINS", "").split(","):
        value = value.strip().rstrip("/")
        if value:
            origins.add(value)
    return origins


@app.get("/api/auth/providers")
async def auth_provider_status(response: Response = None):
    """Public auth-provider status for the login page."""
    return build_auth_provider_status(
        allow_password_login=_ALLOW_PASSWORD_LOGIN,
        temporary_bypass_enabled=is_temporary_auth_bypass_enabled(),
        temporary_auth_user=_temporary_auth_user,
        get_github_oauth_config=_get_github_oauth_config,
        get_google_oauth_config=_get_google_oauth_config,
        shared_oauth_candidate_files=_shared_oauth_candidate_files,
        response=response,
    )


def _normalize_origin(origin: str) -> str:
    if not origin:
        return ""

    from urllib.parse import urlparse

    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _is_allowed_private_origin(origin: str, *, allowed_ports: set[int]) -> bool:
    normalized = _normalize_origin(origin)
    if not normalized:
        return False

    try:
        from urllib.parse import urlparse

        parsed = urlparse(normalized)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return (
            parsed.scheme in {"http", "https"}
            and port in allowed_ports
            and _is_private_ip(host)
        )
    except Exception:
        return False


def _enforce_cookie_csrf(req: Request) -> None:
    if req.method.upper() in _SAFE_HTTP_METHODS:
        return

    origin = req.headers.get("origin") or _normalize_origin(
        req.headers.get("referer", "")
    )
    normalized_origin = _normalize_origin(origin)
    if not normalized_origin or (
        normalized_origin not in _allowed_cookie_origins()
        and not _is_allowed_private_origin(
            normalized_origin, allowed_ports={3000, 8000}
        )
    ):
        raise HTTPException(status_code=403, detail="Request origin not allowed")

    csrf_cookie = req.cookies.get(CSRF_COOKIE_NAME, "")
    csrf_header = req.headers.get("x-csrf-token", "")
    if (
        not csrf_cookie
        or not csrf_header
        or not verify_csrf_token(csrf_header, csrf_cookie)
    ):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")


def _set_admin_auth_cookies(
    resp: Response, req: Request, session_token: str, auth_token: str
) -> None:
    secure = _is_secure_request(req)
    _set_auth_cookies(resp, req, auth_token)
    resp.set_cookie(
        key=_ADMIN_SESSION_COOKIE_NAME,
        value=session_token,
        max_age=_AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def _clear_admin_auth_cookies(resp: Response, req: Request) -> None:
    secure = _is_secure_request(req)
    _clear_auth_cookies(resp, req)
    resp.delete_cookie(
        _ADMIN_SESSION_COOKIE_NAME,
        path="/",
        secure=secure,
        samesite="lax",
    )


def _extract_admin_session_token(req: Request) -> tuple[Optional[str], bool]:
    if is_temporary_auth_bypass_enabled():
        return "temporary-admin-bypass", False

    auth_header = req.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:], False

    cookie_token = req.cookies.get(_ADMIN_SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token, True

    return None, False


# SECURITY: default to NOT trusting proxy headers — set TRUST_PROXY_HEADERS=true
# and TRUSTED_PROXY_CIDRS explicitly when behind a known reverse proxy.
_TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
_TRUSTED_PROXY_CIDRS_RAW = os.getenv(
    "TRUSTED_PROXY_CIDRS",
    "127.0.0.1/32,::1/128",
)
_ENABLE_G38_AUTO_TRAINING = os.getenv("ENABLE_G38_AUTO_TRAINING", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _parse_cidrs(raw: str) -> list:
    nets: list = []
    for token in (raw or "").split(","):
        cidr = token.strip()
        if not cidr:
            continue
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("Invalid TRUSTED_PROXY_CIDRS entry ignored: %s", cidr)
    return nets


_TRUSTED_PROXY_NETWORKS = _parse_cidrs(_TRUSTED_PROXY_CIDRS_RAW)


def _extract_client_ip(req: Request) -> str:
    """
    Extract the most trustworthy client IP.

    Preference order:
    1) Public IPs from common proxy headers (Cloudflare/ELB/Nginx/etc.)
    2) Any valid IP from those headers
    3) Socket peer IP as final fallback
    """

    def _normalize(candidate: str) -> str:
        if not candidate:
            return ""
        val = candidate.strip().strip('"').strip("'")
        if not val or val.lower() == "unknown":
            return ""
        # RFC7239 Forwarded header token, e.g. for=1.2.3.4 or for="[2001:db8::1]:443"
        if val.lower().startswith("for="):
            val = val[4:].strip().strip('"').strip("'")
        # Strip IPv6 brackets
        if val.startswith("[") and "]" in val:
            val = val[1 : val.index("]")]
        # Strip IPv4 :port suffix
        if "." in val and val.count(":") == 1:
            host, port = val.rsplit(":", 1)
            if port.isdigit():
                val = host
        try:
            return str(ipaddress.ip_address(val))
        except ValueError:
            return ""

    def _is_public(ip: str) -> bool:
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return parsed.is_global

    candidates: list[str] = []

    # Single-IP headers commonly set by trusted proxies/CDNs
    for h in ("cf-connecting-ip", "true-client-ip", "x-client-ip", "x-real-ip"):
        val = _normalize(req.headers.get(h, ""))
        if val:
            candidates.append(val)

    # Multi-hop list: left-most is original client in standard deployments
    xff = req.headers.get("x-forwarded-for", "")
    if xff:
        for part in xff.split(","):
            val = _normalize(part)
            if val:
                candidates.append(val)

    # RFC7239 Forwarded: for=...
    forwarded = req.headers.get("forwarded", "")
    if forwarded:
        for group in forwarded.split(","):
            for token in group.split(";"):
                token = token.strip()
                if token.lower().startswith("for="):
                    val = _normalize(token)
                    if val:
                        candidates.append(val)

    # Final fallback: peer socket IP
    peer_ip = _normalize(req.client.host if req.client else "")
    if peer_ip:
        candidates.append(peer_ip)

    peer_ip = _normalize(req.client.host if req.client else "")

    # If proxy headers are disabled or peer is not a trusted proxy, never trust forwarded headers.
    if not _TRUST_PROXY_HEADERS:
        return peer_ip or "unknown"

    if peer_ip:
        try:
            peer_obj = ipaddress.ip_address(peer_ip)
            trusted_peer = any(peer_obj in net for net in _TRUSTED_PROXY_NETWORKS)
        except ValueError:
            trusted_peer = False
    else:
        trusted_peer = False

    if not trusted_peer:
        return peer_ip or "unknown"

    # Prefer public routable IP from trusted proxy headers.
    for ip in candidates:
        if _is_public(ip):
            return ip

    # Otherwise return first valid candidate from trusted proxy chain.
    if candidates:
        return candidates[0]
    return peer_ip or "unknown"


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    # NOTE: 'role' field removed — all registrations are 'hunter'
    # Admin promotion requires existing admin via /api/db/users endpoint


@app.post("/auth/register")
async def register_user(request: RegisterRequest, req: Request, response: Response):
    """Register a new user with hashed password."""
    ip = _extract_client_ip(req)
    ua = req.headers.get("user-agent", "unknown")

    def _sync_register():
        existing = get_user_by_email(request.email)
        if existing:
            return None  # signal already exists
        pw_hash = hash_password(request.password)
        user = create_user(request.name, request.email, "hunter")
        update_user_password(user["id"], pw_hash)

        # Device + session tracking (same pattern as login)
        location = resolve_ip_geolocation(ip)
        dh = compute_device_hash(ua, ip)
        device = register_device(user["id"], dh, ip, ua, location=location)
        session = create_session(
            user["id"],
            "AUTHENTICATED",
            None,
            ip_address=ip,
            user_agent=ua,
            device_hash=dh,
            metadata={"auth_method": "password", "geolocation": location},
        )
        update_user_auth_profile(
            user["id"],
            auth_provider="password",
            ip_address=ip,
            geolocation=location,
        )
        log_activity(
            user["id"],
            "USER_REGISTERED",
            f"User {request.name} registered",
            ip_address=ip,
        )
        token = generate_jwt(
            user["id"],
            request.email,
            session_id=session["id"],
            role="hunter",
        )
        return {
            "user": user,
            "token": token,
            "session_id": session["id"],
            "device": {"hash": dh, "is_new": device.get("is_new", True)},
            "network": {"ip": ip, "geolocation": location},
        }

    result = await asyncio.to_thread(_sync_register)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "EMAIL_EXISTS", "detail": "Email already registered"},
        )
    _set_auth_cookies(response, req, result["token"])
    return {
        "success": True,
        "user": {
            "id": result["user"]["id"],
            "name": result["user"]["name"],
            "email": result["user"]["email"],
            "role": "hunter",
        },
        "session_id": result["session_id"],
        "device": result["device"],
        "network": result["network"],
        "auth_method": "password",
    }


@app.post("/auth/login")
async def login(request: LoginRequest, req: Request, response: Response):
    """Login with email/password. Captures IP, UA, device hash. Sends alerts."""
    if is_temporary_auth_bypass_enabled():
        temp_user = _temporary_auth_user()
        return {
            "success": True,
            "user": {
                "id": temp_user["sub"],
                "name": temp_user["name"],
                "email": temp_user["email"],
                "role": temp_user["role"],
            },
            "session_id": temp_user["session_id"],
            "device": {"hash": "temporary-bypass", "is_new": False},
            "network": {"ip": "0.0.0.0", "geolocation": "temporary-bypass"},
            "auth_method": "temporary_bypass",
            "temporary_bypass": True,
        }

    if not _ALLOW_PASSWORD_LOGIN:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "GITHUB_AUTH_REQUIRED",
                "detail": "Password login is disabled. Use /auth/github or /auth/google for authentication.",
            },
        )

    ip = _extract_client_ip(req)
    ua = req.headers.get("user-agent", "unknown")

    # Rate limiting (fast, no I/O)
    limiter = get_rate_limiter()
    if limiter.is_rate_limited(ip):
        alert_rate_limit_exceeded(ip, limiter.max_attempts)
        raise HTTPException(
            status_code=429, detail="Too many login attempts. Try again later."
        )
    limiter.record_attempt(ip)

    def _sync_login():
        """All blocking I/O (bcrypt, SQLite, SMTP alerts) runs in thread pool."""
        location = resolve_ip_geolocation(ip)

        user = get_user_by_email(request.email)
        if not user:
            log_activity(
                None, "LOGIN_FAILED", f"Unknown email: {request.email}", ip_address=ip
            )
            return {
                "error": 401,
                "detail": {
                    "error": "INVALID_CREDENTIALS",
                    "detail": "Invalid credentials",
                },
            }

        if not user.get("password_hash") or not verify_password(
            request.password, user["password_hash"]
        ):
            log_activity(user["id"], "LOGIN_FAILED", "Invalid password", ip_address=ip)
            try:
                alert_suspicious_activity(
                    f"Failed login attempt for {user['name']}",
                    ip_address=ip,
                    user_name=user["name"],
                    metadata={"email": request.email},
                )
            except Exception:
                logger.warning(
                    "Failed to emit suspicious activity alert for user %s",
                    user["id"],
                    exc_info=True,
                )
            return {
                "error": 401,
                "detail": {
                    "error": "INVALID_CREDENTIALS",
                    "detail": "Invalid credentials",
                },
            }

        limiter.reset(ip)

        if needs_rehash(user["password_hash"]):
            new_hash = hash_password(request.password)
            update_user_password(user["id"], new_hash)

        dh = compute_device_hash(ua, ip)
        device = register_device(user["id"], dh, ip, ua, location=location)
        session = create_session(
            user["id"],
            "AUTHENTICATED",
            None,
            ip_address=ip,
            user_agent=ua,
            device_hash=dh,
            metadata={
                "auth_method": "password",
                "geolocation": location,
            },
        )
        update_user_auth_profile(
            user["id"],
            auth_provider="password",
            ip_address=ip,
            geolocation=location,
        )
        log_activity(
            user["id"], "LOGIN_SUCCESS", f"Login from {ip} ({location})", ip_address=ip
        )

        try:
            alert_new_login(user["name"], ip, ua, location)
            if device.get("is_new"):
                alert_new_device(user["name"], dh, ip, ua, location)
            active_count = get_active_device_count(user["id"])
            if active_count > 1:
                devices = get_user_devices(user["id"])
                alert_multiple_devices(user["name"], active_count, devices)
        except Exception:
            logger.warning(
                "Failed to emit login/device alerts for user %s",
                user["id"],
                exc_info=True,
            )

        token = generate_jwt(
            user["id"],
            user.get("email"),
            session_id=session["id"],
            role=user.get("role", "hunter"),
        )
        return {
            "success": True,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user.get("email"),
                "role": user.get("role", "hunter"),
            },
            "token": token,
            "session_id": session["id"],
            "device": {"hash": dh, "is_new": device.get("is_new", False)},
            "network": {"ip": ip, "geolocation": location},
            "auth_method": "password",
        }

    result = await asyncio.to_thread(_sync_login)
    if "error" in result:
        raise HTTPException(status_code=result["error"], detail=result["detail"])
    _set_auth_cookies(response, req, result["token"])
    return {
        "success": result["success"],
        "user": result["user"],
        "session_id": result["session_id"],
        "device": result["device"],
        "network": result["network"],
        "auth_method": result["auth_method"],
    }


@app.post("/auth/logout")
async def logout(req: Request, response: Response, user=Depends(require_auth)):
    """End current session. Revokes token and invalidates session."""
    if is_temporary_auth_bypass_enabled():
        _clear_auth_cookies(response, req)
        return {
            "success": True,
            "message": "Temporary auth bypass is enabled; no session revocation was required",
            "temporary_bypass": True,
        }

    ip = _extract_client_ip(req)
    session_id = user.get("session_id")

    # Revoke server-side session state before token extraction so the logout
    # contract is visible and enforced even if downstream token parsing changes.
    # revoke_token(token) still runs below after bearer/cookie extraction.
    # end_session(session_id) still runs below for durable session invalidation.
    if session_id:
        revoke_session(session_id)
        try:
            end_session(session_id)
        except Exception:
            logger.warning(
                "Failed to persist logout session termination for %s",
                session_id,
                exc_info=True,
            )

    auth_header = req.headers.get("authorization", "")
    cookie_token = req.cookies.get(AUTH_COOKIE_NAME) or req.cookies.get(
        LEGACY_AUTH_COOKIE_NAME
    )
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif cookie_token:
        token = cookie_token
    if token:
        revoke_token(token)

    user_id = user.get("sub")
    log_activity(user_id, "LOGOUT", f"Logout from {ip}", ip_address=ip)
    _clear_auth_cookies(response, req)
    return {"success": True, "message": "Logged out — token and session revoked"}


@app.get("/auth/profile")
async def auth_profile(user=Depends(require_auth)):
    """Return authenticated profile. Sensitive auth intel is admin-only."""
    return build_auth_profile_payload(
        user=user,
        temporary_bypass_payload=_temporary_auth_profile_payload,
        get_user=get_user,
        get_user_devices=get_user_devices,
        get_recent_activity=get_recent_activity,
    )


@app.get("/auth/me")
async def auth_me(user=Depends(require_auth)):
    """Current authenticated user session — no-cache, always fresh."""
    # Cache-Control: no-store is applied inside build_auth_me_response().
    return build_auth_me_response(
        user=user,
        temporary_bypass_payload=_temporary_auth_me_payload,
        get_user=get_user,
    )


@app.get("/admin/auth/intel")
async def admin_auth_intel(req: Request, limit: int = 200):
    """
    Admin-only sensitive auth view:
      - username/email/role
      - password hash (never plaintext)
      - github id/login/profile details
      - last login IP + geolocation
    """
    token, _ = _extract_admin_session_token(req)
    if not token:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    try:
        from backend.api.admin_auth import (
            require_auth as admin_require_auth,
            ROLE_ADMIN,
        )

        admin_result = admin_require_auth(jwt_token=token, required_role=ROLE_ADMIN)
        if admin_result.get("status") != "ok":
            admin_result = admin_require_auth(
                session_token=token, required_role=ROLE_ADMIN
            )
        if admin_result.get("status") != "ok":
            raise HTTPException(status_code=403, detail="Admin role required")
    except HTTPException:
        raise
    except Exception:
        logger.exception("admin auth intel auth failure")
        raise HTTPException(status_code=401, detail="Invalid admin token")

    safe_limit = max(1, min(limit, 1000))
    users = get_admin_user_security_view(limit=safe_limit)

    return {
        "success": True,
        "total": len(users),
        "users": users,
        "note": "password values are one-way hashes only; plaintext passwords are never stored",
    }


@app.get("/api/storage/tiered")
async def storage_tiered_status(request: Request, user=Depends(require_auth)):
    """Get SSD/HDD storage tiering status."""
    if not TIERED_STORAGE_AVAILABLE:
        return {"available": False, "error": "Tiered storage not loaded"}
    await _abort_if_disconnected(request)
    report = await asyncio.to_thread(get_tiered_report)
    return {"available": True, **report}


@app.post("/api/storage/enforce")
# storage_enforce(user=Depends(require_admin))
async def storage_enforce(request: Request, user=Depends(require_admin)):
    """Manually trigger SSD cap enforcement (compress + migrate)."""
    if not TIERED_STORAGE_AVAILABLE:
        return {"available": False, "error": "Tiered storage not loaded"}
    await _abort_if_disconnected(request)
    result = await asyncio.to_thread(enforce_ssd_cap)
    return {"available": True, **result.to_dict()}


@app.get("/admin/active-devices")
def get_active_devices_endpoint(user=Depends(require_admin)):
    """Get all active devices. Admin only. HDD data only."""
    try:
        devices = get_all_active_devices()
        return {"devices": devices, "total": len(devices)}
    except Exception as e:
        logger.exception("Error listing active devices")
        return {"devices": [], "total": 0, "error": "Internal error"}


@app.get("/admin/active-sessions")
def get_active_sessions_endpoint(user=Depends(require_admin)):
    """Get all active sessions. Admin only. HDD data only."""
    try:
        sessions = get_active_sessions()
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        logger.exception("Error listing active sessions")
        return {"sessions": [], "total": 0, "error": "Internal error"}


# =============================================================================
# HUNTING ENDPOINTS (wired to hunting-control-panel.tsx + HuntingPanel.tsx)
# =============================================================================

# In-memory hunting auto-mode state
_hunting_auto_mode = {
    "enabled": False,
    "shadow_only": True,
    "integrity_score": 0,
    "conditions_met": False,
    "blocked_reasons": ["System not yet calibrated", "No verified fields"],
}


@app.get("/api/hunting/targets")
async def get_hunting_targets(user=Depends(require_auth)):
    """Get AI-suggested hunting targets from the database."""
    try:
        # Pull real targets from HDD storage
        db_targets = get_all_targets()
        suggestions = []
        for t in db_targets:
            suggestions.append(
                {
                    "domain": t.get("scope", "unknown"),
                    "program_name": t.get("program_name", "Unknown"),
                    "platform": t.get("platform", "Unknown"),
                    "scope_size": 1,
                    "api_endpoint_count": 0,
                    "wildcard_count": 1 if "*" in t.get("scope", "") else 0,
                    "likelihood_percent": 50,
                    "difficulty": "MEDIUM",
                    "bounty_range": {"min_usd": 100, "max_usd": 5000},
                    "analysis": f"Target from {t.get('platform', 'unknown')} program",
                }
            )
        return {"targets": suggestions, "total": len(suggestions)}
    except Exception as e:
        logger.exception("Error listing hunting targets")
        return {"targets": [], "total": 0, "error": "Internal error"}


@app.get("/api/hunting/auto-mode")
async def get_hunting_auto_mode(user=Depends(require_auth)):
    """Get current hunting auto-mode state with integrity score."""
    # Read integrity score from supervisor if available
    if INTEGRITY_AVAILABLE:
        try:
            supervisor = get_integrity_supervisor()
            probe = supervisor.probe_all()
            score = probe.get("overall_integrity", {}).get("score", 0)
            _hunting_auto_mode["integrity_score"] = score
            # Auto-mode can be enabled if integrity >= 80
            _hunting_auto_mode["conditions_met"] = score >= 80
            if score < 80:
                _hunting_auto_mode["blocked_reasons"] = [
                    f"Integrity score {score}% < 80% required"
                ]
            else:
                _hunting_auto_mode["blocked_reasons"] = []
        except Exception:
            logger.warning(
                "Failed to refresh hunting auto-mode integrity probe",
                exc_info=True,
            )
    return _hunting_auto_mode


# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================

# In-memory hunting WS connections
hunting_connections: Dict[str, WebSocket] = {}


@app.websocket("/ws/hunting")
async def hunting_websocket(websocket: WebSocket):
    """WebSocket endpoint for live hunting chat (HuntingPanel.tsx)."""
    # B8: Auth gating — verify token before accepting
    user = await ws_authenticate(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()
    conn_id = uuid.uuid4().hex[:8]
    hunting_connections[conn_id] = websocket

    WS_SESSION_TIMEOUT = 14400  # 4 hours max
    _ws_start = time.monotonic()

    try:
        while True:
            if time.monotonic() - _ws_start > WS_SESSION_TIMEOUT:
                logger.info("Hunting WS session timeout")
                break
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                # Echo back as assistant response
                user_text = data.get("content", "")
                await websocket.send_json(
                    {
                        "type": "response",
                        "content": f"Acknowledged: {user_text}. Hunting assistant is in shadow-only mode.",
                    }
                )
            elif msg_type == "detect":
                # Return a detection status
                await websocket.send_json(
                    {
                        "type": "detection",
                        "result": {
                            "exploit_type": "Awaiting scan",
                            "confidence": 0.0,
                            "field_name": "N/A",
                            "features": [],
                            "cvss_score": 0.0,
                            "severity": "INFO",
                            "reasoning": "No active scan in progress",
                            "poc": "",
                            "mitigation": "",
                        },
                    }
                )

    except WebSocketDisconnect:
        logger.info("Hunting websocket disconnected: %s", conn_id)
    except Exception:
        logger.exception("Hunting websocket error: %s", conn_id)
    finally:
        hunting_connections.pop(conn_id, None)


@app.websocket("/ws/hunter/{workflow_id}")
async def hunter_websocket(websocket: WebSocket, workflow_id: str):
    """WebSocket endpoint for Hunter workflow updates."""
    assert not can_ai_execute()[0], "GUARD: AI cannot execute"
    assert not can_ai_submit()[0], "GUARD: AI cannot submit"
    # B8: Auth gating — verify token before accepting
    user = await ws_authenticate(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Ownership check before accepting WebSocket
    workflow = active_workflows.get(workflow_id)
    if not check_ws_resource_owner(workflow, user, "workflow"):
        await websocket.close(code=4003, reason="Access denied — not workflow owner")
        return

    await websocket.accept()
    hunter_connections[workflow_id] = websocket
    workflow["stopped"] = bool(workflow.get("stopped", False))

    try:
        # Real Hunter module execution — no simulated success
        hunter_modules = discover_hunter_modules()
        module_names = list(hunter_modules.keys())

        successful_count = 0
        failed_count = 0
        step_hashes = []

        for idx, module_name in enumerate(module_names):
            if workflow.get("stopped"):
                workflow["status"] = "STOPPED"
                break
            # Execute module directly — fail-closed, no simulated success
            step_success = False
            step_output = {}
            try:
                module_path = (
                    PROJECT_ROOT / "HUMANOID_HUNTER" / module_name / "__init__.py"
                )
                if module_path.exists():
                    import importlib.util

                    spec = importlib.util.spec_from_file_location(
                        f"hunter.{module_name}", str(module_path)
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "execute"):
                        result_data = await asyncio.to_thread(
                            mod.execute, workflow.get("target", "")
                        )
                        step_success = bool(result_data and result_data.get("success"))
                        step_output = result_data or {}
                    else:
                        step_output = {"status": "no_execute_function"}
                else:
                    step_output = {"status": "module_not_found"}
            except Exception as exec_err:
                logger.error(
                    "Hunter module %s execution failed: %s", module_name, exec_err
                )
                step_success = False
                step_output = {"status": "execution_failed"}

            step = {
                "module_name": module_name,
                "function_name": f"execute_{module_name}",
                "success": step_success,
                "input_data": {
                    "target": workflow.get("target", ""),
                    "module_index": idx,
                },
                "output_data": step_output,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if step_success:
                successful_count += 1
            else:
                failed_count += 1

            step_hashes.append(
                hashlib.sha256(
                    json.dumps(step, sort_keys=True, default=str).encode()
                ).hexdigest()
            )

            await websocket.send_json({"type": "step", "step": step})
            workflow["steps"].append(step)

        # Send completion with real counts and content-derived hash
        chain_hash = hashlib.sha256("|".join(step_hashes).encode()).hexdigest()
        result = {
            "final_result": {
                "total_modules": len(module_names),
                "successful": successful_count,
                "failed": failed_count,
            },
            "evidence_chain_hash": chain_hash,
        }

        await websocket.send_json({"type": "complete", "result": result})

    except WebSocketDisconnect:
        workflow["status"] = "STOPPED"
        workflow["stopped"] = True
    finally:
        hunter_connections.pop(workflow_id, None)


@app.websocket("/ws/bounty/{report_id}")
async def bounty_websocket(websocket: WebSocket, report_id: str):
    """WebSocket endpoint for HTTP-based security analysis."""
    assert not can_ai_execute()[0], "GUARD: AI cannot execute"
    assert not can_ai_submit()[0], "GUARD: AI cannot submit"
    # B8: Auth gating — verify token before accepting
    user = await ws_authenticate(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Ownership check before accepting WebSocket
    workflow = active_workflows.get(report_id)
    if not check_ws_resource_owner(workflow, user, "report"):
        await websocket.close(code=4003, reason="Access denied — not report owner")
        return

    await websocket.accept()
    bounty_connections[report_id] = websocket
    ws_closed = False
    workflow["stopped"] = bool(workflow.get("stopped", False))

    try:
        target_url = workflow.get("target", "https://example.com")
        mode = workflow.get("mode", "READ_ONLY")  # READ_ONLY or REAL

        # Debug logging
        print(f"[WS] WEBSOCKET CONNECTED: {report_id}")
        print(f"   Target URL: {target_url}")
        print(f"   Mode: {mode}")

        # Create phase runner with WebSocket progress callback
        async def send_progress(update):
            nonlocal ws_closed
            if ws_closed or workflow.get("stopped"):
                ws_closed = True
                workflow["stopped"] = True
                return
            try:
                await websocket.send_json(update)
            except Exception:
                ws_closed = True
                workflow["stopped"] = True

        runner = RealPhaseRunner(
            on_progress=send_progress,
            should_stop=lambda: ws_closed or bool(workflow.get("stopped")),
        )

        # Run the HTTP-based workflow
        context = await runner.run_workflow(
            target_url=target_url, workflow_id=report_id, mode=mode
        )
        if context.stopped:
            workflow["status"] = "STOPPED"
            workflow["stopped"] = True
            return

        if ws_closed:
            return

        # Build summary from results
        successful = len([r for r in context.phase_results if r.status == "SUCCESS"])
        failed = len([r for r in context.phase_results if r.status == "FAILED"])
        total_duration = sum(r.duration_ms for r in context.phase_results)

        # Convert findings to dict
        findings_data = []
        for f in context.findings:
            if hasattr(f, "__dict__"):
                evidence = getattr(f, "evidence", {}) or {}
                findings_data.append(
                    {
                        "finding_id": f.finding_id,
                        "category": f.category,
                        "severity": f.severity,
                        "title": f.title,
                        "description": f.description,
                        "url": getattr(f, "url", ""),
                        "evidence": evidence,
                        "verification": evidence.get("verification", {}),
                        "identified_as": evidence.get("identified_as", []),
                        "auto_poc_steps": evidence.get("auto_poc_steps", []),
                    }
                )
            else:
                findings_data.append(f)

        # Final result
        result = {
            "summary": {
                "total_phases": len(context.phase_results),
                "successful_steps": successful,
                "failed_steps": failed,
                "findings_count": len(context.findings),
                "pages_visited": len(context.pages_visited),
                "technologies": context.technologies,
                "total_duration_ms": total_duration,
                "report_file": getattr(context, "report_file", None),
                "report_json_file": getattr(context, "report_json_file", None),
                "verification_summary": getattr(context, "verification_summary", {}),
            },
            "findings": findings_data,
            "pages_visited": context.pages_visited,
            "phases": [
                {
                    "number": r.phase_number,
                    "name": r.phase_name,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                }
                for r in context.phase_results
            ],
            "report_hash": hashlib.sha256(
                json.dumps(
                    [
                        {
                            "number": r.phase_number,
                            "name": r.phase_name,
                            "status": r.status,
                            "duration_ms": r.duration_ms,
                        }
                        for r in context.phase_results
                    ],
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest(),
        }

        try:
            await websocket.send_json({"type": "complete", "result": result})
        except Exception:
            logger.warning(
                "Failed to send bounty completion frame for %s",
                report_id,
                exc_info=True,
            )

    except WebSocketDisconnect:
        workflow["status"] = "STOPPED"
        workflow["stopped"] = True
        print(f"[WS] WebSocket disconnected: {report_id}")
    except Exception as e:
        logger.exception(f"WebSocket error: {report_id}")
        try:
            await websocket.send_json(
                {"type": "error", "message": "Internal server error"}
            )
        except Exception:
            logger.warning(
                "Failed to send bounty error frame for %s",
                report_id,
                exc_info=True,
            )
    finally:
        bounty_connections.pop(report_id, None)


# NOTE: Unified lifespan is defined at module top (line ~161) and passed
# directly to FastAPI(lifespan=lifespan). No override needed here.


# =============================================================================
# SYSTEM INTEGRITY ENDPOINT
# =============================================================================


@app.get("/system/integrity")
async def system_integrity(user=Depends(require_auth)):
    """Unified system integrity dashboard. Real data only — no mocks."""
    if not INTEGRITY_AVAILABLE:
        return {
            "error": "Integrity supervisor not available",
            "overall_integrity": {"score": 0, "status": "RED"},
            "shadow_allowed": False,
            "forced_mode": "MODE_A",
        }

    supervisor = get_integrity_supervisor()
    return supervisor.probe_all()


# =============================================================================
# DUAL-MODE VOICE ENDPOINTS
# =============================================================================

# Active voice mode state
_active_voice_mode = "SECURITY"


class VoiceParseRequest(BaseModel):
    text: str
    mode: Optional[str] = None  # "SECURITY" or "RESEARCH", auto-detect if None
    host_session_id: Optional[str] = None


@app.post("/api/voice/parse")
async def voice_parse(request: VoiceParseRequest, user=Depends(require_auth)):
    """Dual-mode voice parser."""
    from backend.assistant.voice_runtime import run_research_analysis
    from impl_v1.phase49.governors.g12_voice_input import extract_intent

    return parse_voice_request(
        text=request.text,
        requested_mode=request.mode,
        host_session_id=request.host_session_id,
        user=user,
        runtime_state=runtime_state,
        research_available=RESEARCH_AVAILABLE,
        query_router_cls=QueryRouter,
        isolation_guard_cls=IsolationGuard,
        run_research_analysis=run_research_analysis,
        extract_intent=extract_intent,
        get_voice_orchestrator=get_voice_orchestrator,
        cache_runtime_status=_store_runtime_status_cached,
        research_status_enum=ResearchStatus,
        logger=logger,
    )


@app.get("/api/voice/mode")
async def voice_mode(user=Depends(require_auth)):
    """Return current active voice mode."""
    return voice_mode_payload(
        runtime_state=runtime_state,
        research_available=RESEARCH_AVAILABLE,
    )


# =============================================================================
# RUNTIME STATUS & ACCURACY ENDPOINTS (for Control Panel)
# =============================================================================

# In-memory mode state (authoritative — mirrors C++ mode_mutex)
_runtime_mode: str = "IDLE"  # IDLE, TRAIN, HUNT


def _as_bool(value: Any) -> bool:
    """Convert telemetry values to strict booleans."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _load_telemetry_hmac_secret() -> str:
    """Load the telemetry HMAC secret from the environment only."""
    return get_required_secret("YGB_HMAC_SECRET", 32)


def _compute_telemetry_crc32(data: Dict[str, Any]) -> int:
    """Compute CRC32 using the exact native payload format."""
    payload = (
        f"v{int(data['schema_version'])}|"
        f"det:{1 if _as_bool(data['determinism_status']) else 0}|"
        f"frz:{1 if _as_bool(data['freeze_status']) else 0}|"
        f"prec:{float(data['precision']):.8f}|"
        f"rec:{float(data['recall']):.8f}|"
        f"kl:{float(data['kl_divergence']):.8f}|"
        f"ece:{float(data['ece']):.8f}|"
        f"loss:{float(data['loss']):.8f}|"
        f"temp:{float(data['gpu_temperature']):.8f}|"
        f"epoch:{int(data['epoch'])}|"
        f"batch:{int(data['batch_size'])}|"
        f"ts:{int(data['timestamp'])}|"
        f"mono:{int(data['monotonic_timestamp'])}|"
        f"start:{int(data['monotonic_start_time'])}|"
        f"wall:{int(data['wall_clock_unix'])}|"
        f"dur:{float(data['training_duration_seconds']):.8f}|"
        f"rate:{float(data['samples_per_second']):.8f}"
    )
    return zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF


def _validate_runtime_telemetry(data: Dict[str, Any]) -> tuple[bool, str]:
    """Validate schema, CRC32, and HMAC integrity for runtime telemetry."""
    required = (
        "schema_version",
        "determinism_status",
        "freeze_status",
        "precision",
        "recall",
        "kl_divergence",
        "ece",
        "loss",
        "gpu_temperature",
        "epoch",
        "batch_size",
        "timestamp",
        "monotonic_timestamp",
        "monotonic_start_time",
        "wall_clock_unix",
        "training_duration_seconds",
        "samples_per_second",
        "crc32",
        "hmac",
    )
    for field in required:
        if field not in data:
            return False, f"Missing field: {field}"

    try:
        schema_version = int(data["schema_version"])
        stored_crc = int(data["crc32"])
        timestamp = int(data["timestamp"])
    except (TypeError, ValueError):
        return False, "Invalid telemetry numeric fields"

    if schema_version != 1:
        return False, f"Unsupported schema_version: {schema_version}"

    try:
        computed_crc = _compute_telemetry_crc32(data)
    except (TypeError, ValueError):
        return False, "Invalid telemetry payload types"
    if stored_crc != computed_crc:
        return False, "CRC validation failed"

    secret = _load_telemetry_hmac_secret()
    if not secret:
        return False, "HMAC secret unavailable"

    stored_hmac = str(data.get("hmac", "")).strip().lower()
    if len(stored_hmac) != 64 or any(
        ch not in "0123456789abcdef" for ch in stored_hmac
    ):
        return False, "Invalid HMAC format"

    msg = f"{schema_version}|{stored_crc}|{timestamp}"
    expected_hmac = (
        hmac.new(
            secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        )
        .hexdigest()
        .lower()
    )
    if not hmac.compare_digest(stored_hmac, expected_hmac):
        return False, "HMAC validation failed"

    return True, ""


def _read_validated_telemetry(
    telemetry_path: Path,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read telemetry JSON and enforce integrity checks."""
    try:
        import json as _json

        raw = telemetry_path.read_text(encoding="utf-8")
        data = _json.loads(raw)
    except Exception:
        logger.exception("Failed to parse telemetry file: %s", telemetry_path)
        return None, "Telemetry parse failed"

    ok, reason = _validate_runtime_telemetry(data)
    if not ok:
        logger.warning("Telemetry integrity check failed: %s", reason)
        return None, reason

    return data, None


@app.get("/runtime/status")
async def runtime_status(user=Depends(require_auth)):
    return get_runtime_status_payload(
        project_root=PROJECT_ROOT,
        g38_available=G38_AVAILABLE,
        get_auto_trainer=get_auto_trainer,
        repair_runtime_artifacts_if_needed=repair_runtime_artifacts_if_needed,
        read_validated_telemetry=_read_validated_telemetry,
        get_runtime_status_cached=_get_runtime_status_cached,
        store_runtime_status_cached=_store_runtime_status_cached,
        logger=logger,
    )


@app.get("/api/accuracy/snapshot")
async def accuracy_snapshot(user=Depends(require_auth)):
    return get_accuracy_snapshot_payload(
        project_root=PROJECT_ROOT,
        g38_available=G38_AVAILABLE,
        get_auto_trainer=get_auto_trainer,
        read_validated_telemetry=_read_validated_telemetry,
        logger=logger,
    )


# =============================================================================
# TRAINING DATA SOURCE TRANSPARENCY
# =============================================================================


@app.get("/api/training/data-source")
async def training_data_source(user=Depends(require_auth)):
    """
    GET /api/training/data-source — Training pipeline source transparency.

    Reads secure_data/dataset_manifest.json to report:
    - Data source (INGESTION_PIPELINE / SYNTHETIC / NONE)
    - Dataset hash
    - Sample count
    - Source registry status
    """
    _api_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_api_dir)
    manifest_path = os.path.join(_project_root, "secure_data", "dataset_manifest.json")

    if not os.path.exists(manifest_path):
        return {
            "data_source": "NO_DATA",
            "dataset_hash": "",
            "sample_count": 0,
            "registry_status": "NO_MANIFEST",
            "strict_real_mode": True,
            "ingestion_manifest_hash": "",
        }

    try:
        import json as _json

        with open(manifest_path, "r", encoding="utf-8") as _f:
            data = _json.load(_f)
        source = data.get("dataset_source", "UNKNOWN")

        # Determine registry status
        if source == "INGESTION_PIPELINE":
            registry = "VERIFIED"
        elif source == "SYNTHETIC_GENERATOR":
            registry = "BLOCKED"
        else:
            registry = "UNKNOWN"

        # Bridge integrity check
        bridge_hash = ""
        dll_integrity = "UNKNOWN"
        try:
            import ctypes

            _bridge_path = os.path.join(
                _project_root, "native", "distributed", "ingestion_bridge.dll"
            )
            if os.path.exists(_bridge_path):
                _bridge = ctypes.CDLL(_bridge_path)
                _bridge.bridge_self_verify(_bridge_path.encode())
                hash_buf = ctypes.create_string_buffer(65)
                _bridge.bridge_get_self_hash(hash_buf, 65)
                bridge_hash = hash_buf.value.decode()
                dll_integrity = (
                    "VERIFIED" if _bridge.bridge_is_self_verified() else "FAILED"
                )
        except Exception:
            dll_integrity = "CHECK_FAILED"

        # Module guard status
        guard_status = "UNKNOWN"
        try:
            _guard_path = os.path.join(
                _project_root, "native", "security", "module_integrity_guard.dll"
            )
            guard_status = "ACTIVE" if os.path.exists(_guard_path) else "MISSING"
        except Exception:
            logger.warning("Integrity guard status inspection failed", exc_info=True)

        return {
            "data_source": source,
            "dataset_hash": data.get("dataset_hash", data.get("tensor_hash", "")),
            "sample_count": data.get("sample_count", 0),
            "registry_status": registry,
            "strict_real_mode": data.get("strict_real_mode", True),
            "ingestion_manifest_hash": data.get("ingestion_manifest_hash", ""),
            "bridge_hash": bridge_hash,
            "dll_integrity": dll_integrity,
            "integrity_guard": guard_status,
            "synthetic_status": "BLOCKED",
        }
    except Exception as e:
        return {
            "data_source": "ERROR",
            "dataset_hash": "",
            "sample_count": 0,
            "registry_status": "ERROR",
            "strict_real_mode": True,
            "ingestion_manifest_hash": "",
            "bridge_hash": "",
            "dll_integrity": "ERROR",
            "integrity_guard": "ERROR",
            "synthetic_status": "BLOCKED",
        }


# =============================================================================
# MODE CONTROL ENDPOINTS (TRAIN/HUNT mutual exclusion)
# =============================================================================


@app.post("/api/mode/train/start")
async def start_training_mode(user=Depends(require_admin)):
    """Start TRAIN mode. Blocked if HUNT is active."""
    enforce_governed_execution(
        action_name="start_training_mode",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    current_mode = runtime_state.get("runtime_mode", "IDLE")
    if current_mode == "HUNT":
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=409,
            content={
                "error": "MUTEX_BLOCKED",
                "reason": "Cannot enter TRAIN while HUNT is active",
                "current_mode": current_mode,
            },
        )
    if current_mode == "TRAIN":
        return {"mode": "TRAIN", "status": "already_active"}

    # Truthful behavior: start real training pipeline or fail.
    if not G38_AVAILABLE:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={
                "error": "TRAIN_UNAVAILABLE",
                "reason": "G38 modules not loaded",
                "mode": runtime_state.get("runtime_mode", "IDLE"),
            },
        )

    result = start_continuous_training(target_epochs=100)
    if not result.get("started", False):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={
                "error": "TRAIN_START_FAILED",
                "reason": result.get("reason", "Failed to start training"),
                "state": result.get("state", "ERROR"),
                "mode": runtime_state.get("runtime_mode", "IDLE"),
            },
        )

    runtime_state.set("runtime_mode", "TRAIN")
    return {
        "mode": "TRAIN",
        "status": "started",
        "training_mode": "CONTINUOUS",
        "target_epochs": 100,
    }


@app.post("/api/mode/train/stop")
async def stop_training_mode(user=Depends(require_admin)):
    """Stop TRAIN mode."""
    enforce_governed_execution(
        action_name="stop_training_mode",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    current_mode = runtime_state.get("runtime_mode", "IDLE")
    if current_mode != "TRAIN":
        return {"mode": current_mode, "status": "not_in_train"}

    if G38_AVAILABLE:
        trainer = get_auto_trainer()
        if getattr(trainer, "_continuous_mode", False):
            stop_continuous_training()
        else:
            trainer.abort_training()

    runtime_state.set("runtime_mode", "IDLE")
    return {"mode": "IDLE", "status": "stopped"}


@app.post("/api/mode/hunt/start")
async def start_hunt_mode(user=Depends(require_admin)):
    """Start HUNT mode. Blocked if TRAIN is active."""
    enforce_governed_execution(
        action_name="start_hunt_mode",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    current_mode = runtime_state.get("runtime_mode", "IDLE")
    if current_mode == "TRAIN":
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=409,
            content={
                "error": "MUTEX_BLOCKED",
                "reason": "Cannot enter HUNT while TRAIN is active",
                "current_mode": current_mode,
            },
        )
    if current_mode == "HUNT":
        return {"mode": "HUNT", "status": "already_active"}
    runtime_state.set("runtime_mode", "HUNT")
    return {"mode": "HUNT", "status": "started"}


@app.post("/api/mode/hunt/stop")
async def stop_hunt_mode(user=Depends(require_admin)):
    """Stop HUNT mode."""
    enforce_governed_execution(
        action_name="stop_hunt_mode",
        can_ai_execute=can_ai_execute,
        can_ai_submit=can_ai_submit,
    )
    current_mode = runtime_state.get("runtime_mode", "IDLE")
    if current_mode != "HUNT":
        return {"mode": current_mode, "status": "not_in_hunt"}
    runtime_state.set("runtime_mode", "IDLE")
    return {"mode": "IDLE", "status": "stopped"}


# =============================================================================
# GITHUB OAUTH LOGIN
# =============================================================================


def _env_oauth_value(key: str, default: str = "") -> str:
    raw = os.getenv(key, default).strip()
    if raw and _is_placeholder_env_value(key, raw):
        return default
    return raw


def _get_oauth_state_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("OAUTH_STATE_TTL_SECONDS", "600")))
    except Exception:
        return 600


def _get_oauth_state_secret() -> str:
    return get_required_secret("YGB_HMAC_SECRET", 32)


def _refresh_oauth_env(provider: str) -> None:
    keys = _oauth_provider_env_keys(provider)
    if _env_oauth_value(keys["client_id"], "") and _env_oauth_value(
        keys["client_secret"], ""
    ):
        return
    allowed_keys = {
        keys["client_id"],
        keys["client_secret"],
        keys["redirect_uri"],
        "FRONTEND_URL",
        "YGB_ALLOWED_ORIGINS",
    }
    _load_env_file(
        _ENV_ROOT / ".env", allow_placeholders=False, allowed_keys=allowed_keys
    )
    _load_env_file(
        _ENV_ROOT / ".env.connected",
        allow_placeholders=False,
        allowed_keys=allowed_keys,
    )
    _load_shared_oauth_env(provider)


def _oauth_provider_label(provider: str) -> str:
    return "Google" if (provider or "").strip().lower() == "google" else "GitHub"


def _oauth_state_cookie_name(provider: str) -> str:
    normalized = (provider or "github").strip().lower()
    if normalized == "github":
        return "ygb_oauth_state"
    return f"ygb_oauth_state_{normalized}"


def _get_github_oauth_config() -> Dict[str, Any]:
    _refresh_oauth_env("github")
    client_id = _env_oauth_value("GITHUB_CLIENT_ID", "")
    client_secret = _env_oauth_value("GITHUB_CLIENT_SECRET", "")
    frontend_url = _env_oauth_value("FRONTEND_URL", "http://localhost:3000")
    redirect_uri = _env_oauth_value(
        "GITHUB_REDIRECT_URI",
        "http://localhost:8000/auth/github/callback",
    )
    missing = []
    if not client_id:
        missing.append("GITHUB_CLIENT_ID")
    if not client_secret:
        missing.append("GITHUB_CLIENT_SECRET")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "frontend_url": frontend_url.rstrip("/"),
        "redirect_uri": redirect_uri,
        "missing": missing,
    }


def _get_google_oauth_config() -> Dict[str, Any]:
    _refresh_oauth_env("google")
    client_id = _env_oauth_value("GOOGLE_CLIENT_ID", "")
    client_secret = _env_oauth_value("GOOGLE_CLIENT_SECRET", "")
    frontend_url = _env_oauth_value("FRONTEND_URL", "http://localhost:3000")
    redirect_uri = _env_oauth_value(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    missing = []
    if not client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "frontend_url": frontend_url.rstrip("/"),
        "redirect_uri": redirect_uri,
        "missing": missing,
    }


def _oauth_not_configured_detail(provider: str = "github") -> Dict[str, Any]:
    normalized = (provider or "github").strip().lower()
    cfg = (
        _get_google_oauth_config()
        if normalized == "google"
        else _get_github_oauth_config()
    )
    label = _oauth_provider_label(normalized)
    return {
        "error": f"{normalized.upper()}_OAUTH_NOT_CONFIGURED",
        "detail": f"{label} OAuth is not fully configured",
        "missing": cfg["missing"],
        "redirect_uri": cfg["redirect_uri"],
        "frontend_url": cfg["frontend_url"],
        "checked_files": [".env", ".env.connected"],
        "shared_candidates": [
            str(path) for path in _shared_oauth_candidate_files(normalized)
        ],
    }


# --- HTTP session pool for OAuth provider APIs (connection reuse / keep-alive) ---
try:
    import requests as _http_lib

    _github_http = _http_lib.Session()
    _github_http.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "YGB-Server",
        }
    )
    _oauth_http = _github_http
    _HAVE_REQUESTS = True
except ImportError:
    _HAVE_REQUESTS = False
    _github_http = None
    _oauth_http = None


def _b64url_encode(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> str:
    padding = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii")).decode("utf-8")


def _oauth_state_sign(payload: str) -> str:
    secret = _get_oauth_state_secret()
    if not secret:
        return ""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _allowed_frontend_urls() -> set[str]:
    cfg = _get_github_oauth_config()
    urls = {
        cfg["frontend_url"],
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
    for value in os.getenv("YGB_ALLOWED_ORIGINS", "").split(","):
        value = value.strip().rstrip("/")
        if value:
            urls.add(value)
    return urls


def _is_private_ip(host: str) -> bool:
    """Check if a host is a private/local network address."""
    import re

    ip_part = host.split(":")[0]  # strip port
    if ip_part in ("localhost", "127.0.0.1"):
        return True
    if ip_part.startswith("192.168.") or ip_part.startswith("10."):
        return True
    if ip_part.startswith("100."):  # Tailscale CGNAT (100.64-127.*)
        return True
    # RFC 1918: only 172.16.0.0 – 172.31.255.255 is private
    if ip_part.startswith("172."):
        try:
            second_octet = int(ip_part.split(".")[1])
            if 16 <= second_octet <= 31:
                return True
        except (IndexError, ValueError):
            logger.debug(
                "Failed to parse private-range candidate host: %s",
                ip_part,
                exc_info=True,
            )
        return False
    # Treat all other bare IPs as potentially LAN (conservative for OAuth)
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip_part):
        return False  # Fixed: was returning True for ALL IPs including public
    return False


def _resolve_frontend_url(candidate: str = "") -> str:
    """Resolve frontend URL — accept any private-network-based URL on port 3000."""
    cfg = _get_github_oauth_config()
    val = (candidate or "").strip().rstrip("/")
    if not val:
        return cfg["frontend_url"]
    if val in _allowed_frontend_urls():
        return val
    if _is_allowed_private_origin(val, allowed_ports={3000}):
        return val
    return cfg["frontend_url"]


def _build_oauth_state(frontend_url: str) -> str:
    ts = str(int(datetime.now(UTC).timestamp()))
    nonce = secrets.token_hex(16)
    fe = _b64url_encode(frontend_url)
    payload = f"v1.{ts}.{nonce}.{fe}"
    return f"{payload}.{_oauth_state_sign(payload)}"


def _parse_oauth_state(state: str) -> tuple[bool, Optional[str]]:
    try:
        parts = state.split(".")
        if len(parts) != 5 or parts[0] != "v1":
            return False, None

        payload = ".".join(parts[:4])
        sig = parts[4]
        expected = _oauth_state_sign(payload)
        if not expected or not hmac.compare_digest(sig, expected):
            return False, None

        ts = int(parts[1])
        now = int(datetime.now(UTC).timestamp())
        if now - ts > _get_oauth_state_ttl_seconds():
            return False, None

        frontend_url = _resolve_frontend_url(_b64url_decode(parts[3]))
        return True, frontend_url
    except Exception:
        return False, None


def _perf_ms(start: float) -> int:
    """Milliseconds elapsed since *start* (time.monotonic)."""
    import time as _t

    return int((_t.monotonic() - start) * 1000)


def _resolve_or_create_github_user(
    github_id: str,
    github_login: str,
    effective_email: str,
) -> tuple[Dict[str, Any], bool]:
    """Resolve a local user for a GitHub account using stable identity first."""
    user = get_user_by_github_id(github_id)
    if user:
        return user, False

    user = get_user_by_email(effective_email) if effective_email else None
    if user:
        return user, False

    display_name = github_login or f"github-{github_id}"
    return create_user(display_name, effective_email, "hunter"), True


def _resolve_or_create_google_user(
    google_sub: str,
    effective_email: str,
    display_name: str,
) -> tuple[Dict[str, Any], bool]:
    """Resolve a local user for a Google account using stable identity first."""
    user = get_user_by_google_sub(google_sub)
    if user:
        return user, False

    user = get_user_by_email(effective_email) if effective_email else None
    if user:
        return user, False

    safe_name = (display_name or "").strip() or f"google-{google_sub}"
    return create_user(safe_name, effective_email, "hunter"), True


@app.get("/auth/github")
async def github_auth_redirect(req: Request, frontend_origin: str = ""):
    """Redirect to GitHub OAuth authorization page."""
    cfg = _get_github_oauth_config()
    _GITHUB_REDIRECT_URI = cfg["redirect_uri"]
    if not cfg["client_id"]:
        raise HTTPException(
            status_code=501,
            detail=_oauth_not_configured_detail(),
        )

    import urllib.parse

    # SECURITY: Use the configured callback URI — never derive from Host header
    # (Host header is attacker-controlled and can redirect OAuth codes off-site)
    logger.info("[OAuth] Using configured callback: %s", cfg["redirect_uri"])

    # Derive frontend URL from requester's IP
    if frontend_origin:
        frontend_url = _resolve_frontend_url(frontend_origin)
    elif _is_private_ip(req.headers.get("host", "")):
        host_ip = req.headers.get("host", "localhost:3000").split(":")[0]
        frontend_url = f"http://{host_ip}:3000"
    else:
        frontend_url = _resolve_frontend_url("")

    state = _build_oauth_state(frontend_url)
    params = urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "redirect_uri": _GITHUB_REDIRECT_URI,
            "scope": "user:email",
            "state": state,
        }
    )
    resp = RedirectResponse(
        url=f"https://github.com/login/oauth/authorize?{params}",
        status_code=302,
    )
    _oauth_secure = req.url.scheme == "https" or _GITHUB_REDIRECT_URI.startswith(
        "https://"
    )
    resp.set_cookie(
        key=_oauth_state_cookie_name("github"),
        value=state,
        max_age=_get_oauth_state_ttl_seconds(),
        httponly=True,
        samesite="lax",
        secure=_oauth_secure,
    )
    return resp


@app.get("/auth/github/callback")
async def github_auth_callback(
    req: Request, code: str = "", error: str = "", state: str = ""
):
    """Handle GitHub OAuth callback — exchange code → JWT → redirect to frontend."""
    cfg = _get_github_oauth_config()
    _GITHUB_REDIRECT_URI = cfg["redirect_uri"]
    state_cookie = _oauth_state_cookie_name("github")
    parsed_ok, parsed_frontend = _parse_oauth_state(state) if state else (False, None)
    frontend_url = parsed_frontend or cfg["frontend_url"]

    if error:
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error={error}&auth=github",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    if not code:
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error=no_code&auth=github",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    expected_state = req.cookies.get(state_cookie, "")
    cookie_ok = bool(state and expected_state and state == expected_state)
    if not parsed_ok:
        logger.warning("GitHub OAuth state HMAC validation failed")
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error=state_mismatch&auth=github",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp
    if not cookie_ok:
        logger.warning("GitHub OAuth state cookie missing or mismatched — rejecting")
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error=state_mismatch&auth=github",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(
            status_code=501,
            detail=_oauth_not_configured_detail(),
        )

    import urllib.parse
    import time as _time

    ip = _extract_client_ip(req)
    ua = req.headers.get("user-agent", "unknown")

    # ------------------------------------------------------------------
    # FAST PATH — runs in thread pool, returns JWT + redirect ASAP
    # Only does: token exchange → /user → DB upsert → JWT
    # ------------------------------------------------------------------
    def _sync_github_fast_path():
        """Critical-path GitHub exchange: token + user + DB + JWT."""
        t_total = _time.monotonic()
        timings: Dict[str, int] = {}

        # 1. Exchange code -> access token  (uses connection-pooled session)
        t0 = _time.monotonic()
        # Use the same configured redirect_uri that was sent in /auth/github
        callback_redirect = _GITHUB_REDIRECT_URI
        token_payload = {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "redirect_uri": callback_redirect,
        }

        if _HAVE_REQUESTS:
            token_resp_raw = _github_http.post(
                "https://github.com/login/oauth/access_token",
                data=token_payload,
                timeout=5,
            )
            token_resp = token_resp_raw.json()
        else:
            import urllib.request as _ureq

            _data = urllib.parse.urlencode(token_payload).encode()
            _req = _ureq.Request(
                "https://github.com/login/oauth/access_token",
                data=_data,
                headers={"Accept": "application/json"},
            )
            with _ureq.urlopen(_req, timeout=5) as _r:
                token_resp = json.loads(_r.read().decode())

        timings["token_exchange"] = _perf_ms(t0)

        access_token = token_resp.get("access_token")
        if not access_token:
            logger.error("GitHub token exchange failed: %s", token_resp)
            return {"error": "token_exchange_failed"}

        # 2. Fetch /user  (reuses same TCP+TLS connection via requests.Session)
        t0 = _time.monotonic()
        auth_hdr = {"Authorization": f"Bearer {access_token}"}

        if _HAVE_REQUESTS:
            user_resp = _github_http.get(
                "https://api.github.com/user",
                headers=auth_hdr,
                timeout=3,
            )
            user_data = user_resp.json()
        else:
            import urllib.request as _ureq

            _req = _ureq.Request(
                "https://api.github.com/user",
                headers={
                    **auth_hdr,
                    "Accept": "application/json",
                    "User-Agent": "YGB-Server",
                },
            )
            with _ureq.urlopen(_req, timeout=3) as _r:
                user_data = json.loads(_r.read().decode())

        timings["user_fetch"] = _perf_ms(t0)

        github_id = str(user_data.get("id", ""))
        if not github_id:
            logger.error("GitHub user payload missing id: %s", user_data)
            return {"error": "invalid_github_profile"}
        github_login = user_data.get("login", "")
        github_email = user_data.get("email", "")

        # Use public email or stable fallback — background will resolve private email later
        effective_email = github_email or f"github-{github_id}@users.noreply.local"
        github_profile_minimal = {
            "github_id": github_id,
            "github_login": github_login,
            "name": user_data.get("name") or github_login or "",
            "avatar_url": user_data.get("avatar_url", ""),
            "html_url": user_data.get("html_url", ""),
        }

        # 3. DB: lookup/create user → create session → issue JWT
        t0 = _time.monotonic()
        user, is_new_user = _resolve_or_create_github_user(
            github_id=github_id,
            github_login=github_login,
            effective_email=effective_email,
        )

        session = create_session(
            user["id"],
            "AUTHENTICATED",
            None,
            ip_address=ip,
            user_agent=ua,
            device_hash=compute_device_hash(ua, ip),
            metadata={
                "auth_method": "github",
                "github_login": github_login,
                "github_id": github_id,
            },
        )
        update_user_auth_profile(
            user["id"],
            auth_provider="github",
            ip_address=ip,
            geolocation=None,
            github_profile=github_profile_minimal,
        )
        timings["db_upsert"] = _perf_ms(t0)

        # 4. Issue JWT
        t0 = _time.monotonic()
        jwt_token = generate_jwt(
            user_id=user["id"],
            email=user.get("email"),
            session_id=session["id"],
            role=user.get("role", "hunter"),
        )
        timings["jwt"] = _perf_ms(t0)

        timings["total_fast_path"] = _perf_ms(t_total)
        logger.info(
            "oauth_perf fast_path: %s",
            " ".join(f"{k}={v}ms" for k, v in timings.items()),
        )

        # Build minimal profile for redirect URL (no GeoIP yet — background fills it)
        safe_user = urllib.parse.quote_plus(user.get("name", github_login or "user"))
        # Security: auth stays in cookies, not URL params.
        return {
            "redirect_url": (f"{frontend_url}/login?user={safe_user}&auth=github"),
            "_auth_token": jwt_token,
            # Pass context to background task (no secrets — only IDs/metadata)
            "_bg_ctx": {
                "user_id": user["id"],
                "user_name": user.get("name", github_login),
                "github_id": github_id,
                "github_login": github_login,
                "github_email": github_email,
                "effective_email": effective_email,
                "access_token": access_token,
                "user_data": user_data,
                "is_new_user": is_new_user,
            },
        }

    # ------------------------------------------------------------------
    # BACKGROUND TASK — non-critical, runs after redirect is sent
    # GeoIP, /user/emails, device registration, profile update, alerts
    # ------------------------------------------------------------------
    def _oauth_background_work(bg_ctx: dict):
        """Best-effort enrichment: runs AFTER the user has already been redirected."""
        import time as _t

        t_total = _t.monotonic()
        timings: Dict[str, int] = {}

        user_id = bg_ctx["user_id"]
        user_name = bg_ctx["user_name"]
        github_id = bg_ctx["github_id"]
        github_login = bg_ctx["github_login"]
        access_token = bg_ctx["access_token"]
        user_data = bg_ctx["user_data"]
        effective_email = bg_ctx["effective_email"]
        github_email = bg_ctx["github_email"]

        try:
            # 1. GeoIP (was blocking the entire flow before)
            t0 = _t.monotonic()
            location = resolve_ip_geolocation(ip)
            timings["geoip"] = _perf_ms(t0)

            # 2. Fetch private email if needed
            t0 = _t.monotonic()
            if not github_email:
                try:
                    if _HAVE_REQUESTS:
                        emails_resp = _github_http.get(
                            "https://api.github.com/user/emails",
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=3,
                        )
                        emails = emails_resp.json()
                    else:
                        import urllib.request as _ureq

                        _req = _ureq.Request(
                            "https://api.github.com/user/emails",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Accept": "application/json",
                                "User-Agent": "YGB-Server",
                            },
                        )
                        with _ureq.urlopen(_req, timeout=3) as _r:
                            emails = json.loads(_r.read().decode())

                    for em in emails:
                        if em.get("primary") and em.get("verified"):
                            github_email = em["email"]
                            break
                    if not github_email and emails:
                        github_email = emails[0].get("email", "")
                except Exception:
                    logger.debug("Background /user/emails fetch failed", exc_info=True)
            timings["emails_fetch"] = _perf_ms(t0)

            # 3. Build full profile for storage
            github_profile = {
                "github_id": github_id,
                "github_login": github_login,
                "name": user_data.get("name") or github_login or "",
                "email": github_email or effective_email,
                "avatar_url": user_data.get("avatar_url", ""),
                "html_url": user_data.get("html_url", ""),
                "company": user_data.get("company", ""),
                "blog": user_data.get("blog", ""),
                "location": user_data.get("location", ""),
                "bio": user_data.get("bio", ""),
                "public_repos": int(user_data.get("public_repos") or 0),
                "followers": int(user_data.get("followers") or 0),
                "following": int(user_data.get("following") or 0),
                "geoip_location": location,
                "ip_address": ip,
            }
            for key, value in list(github_profile.items()):
                if isinstance(value, str):
                    github_profile[key] = value.strip()[:512]

            # 4. Device registration + profile + audit log
            t0 = _t.monotonic()
            dh = compute_device_hash(ua, ip)
            device = register_device(user_id, dh, ip, ua, location=location)
            update_user_auth_profile(
                user_id,
                auth_provider="github",
                ip_address=ip,
                geolocation=location,
                github_profile=github_profile,
            )
            if bg_ctx.get("is_new_user"):
                log_activity(
                    user_id,
                    "USER_REGISTERED_GITHUB",
                    f"GitHub account linked: {github_login}",
                    ip_address=ip,
                )
            log_activity(
                user_id,
                "LOGIN_SUCCESS_GITHUB",
                f"GitHub login from {ip} ({location})",
                ip_address=ip,
                metadata={
                    "github_login": github_login,
                    "github_id": github_id,
                },
            )
            timings["db_writes"] = _perf_ms(t0)

            # 5. Email alerts (best-effort)
            t0 = _t.monotonic()
            try:
                alert_new_login(user_name, ip, ua, location)
                if device.get("is_new"):
                    alert_new_device(user_name, dh, ip, ua, location)
                active_count = get_active_device_count(user_id)
                if active_count > 1:
                    devices = get_user_devices(user_id)
                    alert_multiple_devices(user_name, active_count, devices)
            except Exception:
                logger.warning(
                    "Background OAuth alert emission failed for user %s",
                    user_id,
                    exc_info=True,
                )
            timings["alerts"] = _perf_ms(t0)

            timings["total_bg"] = _perf_ms(t_total)
            logger.info(
                "oauth_perf background: %s",
                " ".join(f"{k}={v}ms" for k, v in timings.items()),
            )
        except Exception:
            logger.exception("OAuth background enrichment error (non-fatal)")

    # ------------------------------------------------------------------
    # Execute: fast path → redirect immediately → background fires after
    # ------------------------------------------------------------------
    try:
        result = await asyncio.to_thread(_sync_github_fast_path)
    except Exception:
        logger.exception("GitHub OAuth callback error")
        result = {"error": "server_error"}

    if "error" in result:
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error={result['error']}&auth=github",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    # Fire background enrichment (non-blocking)
    bg_ctx = result.pop("_bg_ctx", None)
    if bg_ctx:
        asyncio.get_event_loop().run_in_executor(None, _oauth_background_work, bg_ctx)

    resp = RedirectResponse(url=result["redirect_url"], status_code=302)
    resp.delete_cookie(state_cookie)
    resp.delete_cookie("ygb_oauth_state")

    auth_token = result.get("_auth_token")
    if auth_token:
        _set_auth_cookies(resp, req, auth_token)
    return resp


# =============================================================================
# GOOGLE OAUTH LOGIN
# =============================================================================


@app.get("/auth/google")
async def google_auth_redirect(req: Request, frontend_origin: str = ""):
    """Redirect to Google OAuth authorization page."""
    cfg = _get_google_oauth_config()
    if not cfg["client_id"]:
        raise HTTPException(
            status_code=501,
            detail=_oauth_not_configured_detail("google"),
        )

    import urllib.parse

    logger.info("[OAuth] Using configured Google callback: %s", cfg["redirect_uri"])

    if frontend_origin:
        frontend_url = _resolve_frontend_url(frontend_origin)
    elif _is_private_ip(req.headers.get("host", "")):
        host_ip = req.headers.get("host", "localhost:3000").split(":")[0]
        frontend_url = f"http://{host_ip}:3000"
    else:
        frontend_url = _resolve_frontend_url("")

    state = _build_oauth_state(frontend_url)
    params = urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
            "include_granted_scopes": "true",
        }
    )
    resp = RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}",
        status_code=302,
    )
    _oauth_secure = req.url.scheme == "https" or cfg["redirect_uri"].startswith(
        "https://"
    )
    resp.set_cookie(
        key=_oauth_state_cookie_name("google"),
        value=state,
        max_age=_get_oauth_state_ttl_seconds(),
        httponly=True,
        samesite="lax",
        secure=_oauth_secure,
    )
    return resp


@app.get("/auth/google/callback")
async def google_auth_callback(
    req: Request, code: str = "", error: str = "", state: str = ""
):
    """Handle Google OAuth callback and establish a local session."""
    cfg = _get_google_oauth_config()
    state_cookie = _oauth_state_cookie_name("google")
    parsed_ok, parsed_frontend = _parse_oauth_state(state) if state else (False, None)
    frontend_url = parsed_frontend or cfg["frontend_url"]

    if error:
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error={error}&auth=google",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    if not code:
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error=no_code&auth=google",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    expected_state = req.cookies.get(state_cookie, "")
    cookie_ok = bool(state and expected_state and state == expected_state)
    if not parsed_ok:
        logger.warning("Google OAuth state HMAC validation failed")
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error=state_mismatch&auth=google",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp
    if not cookie_ok:
        logger.warning("Google OAuth state cookie missing or mismatched; rejecting")
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error=state_mismatch&auth=google",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(
            status_code=501,
            detail=_oauth_not_configured_detail("google"),
        )

    import urllib.parse

    ip = _extract_client_ip(req)
    ua = req.headers.get("user-agent", "unknown")

    def _sync_google_login():
        location = resolve_ip_geolocation(ip)
        token_payload = {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": cfg["redirect_uri"],
        }

        if _HAVE_REQUESTS:
            token_resp_raw = _oauth_http.post(
                "https://oauth2.googleapis.com/token",
                data=token_payload,
                timeout=5,
            )
            token_resp = token_resp_raw.json()
        else:
            import urllib.request as _ureq

            _data = urllib.parse.urlencode(token_payload).encode()
            _req = _ureq.Request(
                "https://oauth2.googleapis.com/token",
                data=_data,
                headers={"Accept": "application/json"},
            )
            with _ureq.urlopen(_req, timeout=5) as _r:
                token_resp = json.loads(_r.read().decode())

        access_token = token_resp.get("access_token")
        if not access_token:
            logger.error("Google token exchange failed: %s", token_resp)
            return {"error": "token_exchange_failed"}

        auth_hdr = {"Authorization": f"Bearer {access_token}"}
        if _HAVE_REQUESTS:
            user_resp = _oauth_http.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers=auth_hdr,
                timeout=5,
            )
            user_data = user_resp.json()
        else:
            import urllib.request as _ureq

            _req = _ureq.Request(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={
                    **auth_hdr,
                    "Accept": "application/json",
                    "User-Agent": "YGB-Server",
                },
            )
            with _ureq.urlopen(_req, timeout=5) as _r:
                user_data = json.loads(_r.read().decode())

        google_sub = str(user_data.get("sub", "")).strip()
        if not google_sub:
            logger.error("Google user payload missing sub: %s", user_data)
            return {"error": "invalid_google_profile"}

        google_email = str(user_data.get("email", "")).strip()
        email_verified = bool(user_data.get("email_verified"))
        effective_email = (
            google_email
            if (google_email and email_verified)
            else f"google-{google_sub}@users.noreply.local"
        )
        display_name = (
            str(user_data.get("name", "")).strip()
            or (google_email.split("@", 1)[0] if google_email else "")
            or f"google-{google_sub}"
        )
        google_profile = {
            "google_sub": google_sub,
            "google_email": google_email,
            "email_verified": email_verified,
            "name": user_data.get("name") or display_name,
            "given_name": user_data.get("given_name", ""),
            "family_name": user_data.get("family_name", ""),
            "google_picture": user_data.get("picture", ""),
            "picture": user_data.get("picture", ""),
            "locale": user_data.get("locale", ""),
            "hd": user_data.get("hd", ""),
            "ip_address": ip,
            "geoip_location": location,
        }
        for key, value in list(google_profile.items()):
            if isinstance(value, str):
                google_profile[key] = value.strip()[:512]

        user, is_new_user = _resolve_or_create_google_user(
            google_sub=google_sub,
            effective_email=effective_email,
            display_name=display_name,
        )

        dh = compute_device_hash(ua, ip)
        device = register_device(user["id"], dh, ip, ua, location=location)
        session = create_session(
            user["id"],
            "AUTHENTICATED",
            None,
            ip_address=ip,
            user_agent=ua,
            device_hash=dh,
            metadata={
                "auth_method": "google",
                "google_sub": google_sub,
                "google_email": google_email or effective_email,
                "geolocation": location,
            },
        )
        update_user_auth_profile(
            user["id"],
            auth_provider="google",
            ip_address=ip,
            geolocation=location,
            google_profile=google_profile,
        )

        user_name = user.get("name", display_name)
        if is_new_user:
            log_activity(
                user["id"],
                "USER_REGISTERED_GOOGLE",
                f"Google account linked: {google_email or google_sub}",
                ip_address=ip,
            )
        log_activity(
            user["id"],
            "LOGIN_SUCCESS_GOOGLE",
            f"Google login from {ip} ({location})",
            ip_address=ip,
            metadata={
                "google_sub": google_sub,
                "google_email": google_email or effective_email,
            },
        )

        try:
            alert_new_login(user_name, ip, ua, location)
            if device.get("is_new"):
                alert_new_device(user_name, dh, ip, ua, location)
            active_count = get_active_device_count(user["id"])
            if active_count > 1:
                devices = get_user_devices(user["id"])
                alert_multiple_devices(user_name, active_count, devices)
        except Exception:
            logger.warning(
                "Device tracking/alerting failed for user %s",
                user.get("name"),
                exc_info=True,
            )

        jwt_token = generate_jwt(
            user_id=user["id"],
            email=user.get("email"),
            session_id=session["id"],
            role=user.get("role", "hunter"),
        )
        safe_user = urllib.parse.quote_plus(user_name or "user")
        return {
            "redirect_url": f"{frontend_url}/login?user={safe_user}&auth=google",
            "_auth_token": jwt_token,
        }

    try:
        result = await asyncio.to_thread(_sync_google_login)
    except Exception:
        logger.exception("Google OAuth callback error")
        result = {"error": "server_error"}

    if "error" in result:
        resp = RedirectResponse(
            url=f"{frontend_url}/login?error={result['error']}&auth=google",
            status_code=302,
        )
        resp.delete_cookie(state_cookie)
        resp.delete_cookie("ygb_oauth_state")
        return resp

    resp = RedirectResponse(url=result["redirect_url"], status_code=302)
    resp.delete_cookie(state_cookie)
    resp.delete_cookie("ygb_oauth_state")

    auth_token = result.get("_auth_token")
    if auth_token:
        _set_auth_cookies(resp, req, auth_token)
    return resp


# =============================================================================
# ADMIN ROUTE COMPATIBILITY
# =============================================================================


class AdminLoginRequest(BaseModel):
    email: str
    totp_code: str = ""


@app.post("/admin/login")
async def admin_login(request: AdminLoginRequest, req: Request, response: Response):
    """Admin login — entry point for admin auth. No Depends(require_auth)."""
    try:
        from backend.api.admin_auth import login as admin_auth_login

        result = admin_auth_login(
            email=request.email,
            totp_code=request.totp_code,
            ip=_extract_client_ip(req),
        )
        if result.get("status") != "ok":
            raise HTTPException(
                status_code=401,
                detail=result.get("message", "Login failed"),
            )

        browser_token = generate_jwt(
            user_id=result["user_id"],
            email=request.email,
            session_id=f"admin:{result['session_token']}",
            role=result.get("role", "admin").lower(),
        )
        _set_admin_auth_cookies(response, req, result["session_token"], browser_token)
        return {
            "status": "ok",
            "user_id": result["user_id"],
            "role": result.get("role"),
        }
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=501, detail="Admin auth module not available")
    except Exception:
        logger.exception("Admin login error")
        raise HTTPException(status_code=500, detail="Internal error during login")


@app.get("/admin/verify")
async def admin_verify(req: Request):
    """Verify an admin session. Returns user info or 401."""
    token, _ = _extract_admin_session_token(req)
    if not token:
        raise HTTPException(status_code=401, detail="Admin authentication required")

    try:
        from backend.api.admin_auth import require_auth as admin_require_auth

        # Try as JWT first, then as session token
        result = admin_require_auth(jwt_token=token)
        if result.get("status") == "ok":
            return result

        result = admin_require_auth(session_token=token)
        if result.get("status") == "ok":
            return result

        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=501, detail="Admin auth module not available")
    except Exception:
        logger.exception("Admin verify error")
        raise HTTPException(status_code=500, detail="Verification failed")


class VaultUnlockRequest(BaseModel):
    vault_password: str


@app.post("/admin/vault-unlock")
async def admin_vault_unlock(request: VaultUnlockRequest, req: Request):
    """Unlock the vault. Requires an authenticated admin session."""
    token, via_cookie = _extract_admin_session_token(req)
    if not token:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    if via_cookie:
        _enforce_cookie_csrf(req)

    try:
        from backend.api.vault_session import vault_unlock

        result = vault_unlock(
            vault_password=request.vault_password,
            session_token=token,
            ip=req.client.host if req.client else "0.0.0.0",
        )
        if result.get("status") == "ok":
            return result
        elif result.get("status") == "unauthorized":
            raise HTTPException(
                status_code=401, detail=result.get("message", "Unauthorized")
            )
        else:
            raise HTTPException(
                status_code=400, detail=result.get("message", "Vault unlock failed")
            )
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=501, detail="Vault session module not available"
        )
    except Exception:
        logger.exception("Vault unlock error")
        raise HTTPException(status_code=500, detail="Vault unlock failed")


@app.post("/admin/logout")
async def admin_logout(req: Request, response: Response):
    """Terminate admin session cookies and revoke browser auth."""
    admin_session_token, _ = _extract_admin_session_token(req)
    browser_token = req.cookies.get(AUTH_COOKIE_NAME)

    try:
        if browser_token:
            revoke_token(browser_token)
            payload = verify_jwt(browser_token)
            if payload and payload.get("session_id"):
                revoke_session(payload["session_id"])
        if admin_session_token:
            from backend.api.admin_auth import logout as admin_auth_logout

            admin_auth_logout(admin_session_token)
    except ImportError:
        raise HTTPException(status_code=501, detail="Admin auth module not available")
    except Exception:
        logger.exception("Admin logout error")
        raise HTTPException(status_code=500, detail="Admin logout failed")

    _clear_admin_auth_cookies(response, req)
    return {"status": "ok"}


# =============================================================================
# ROLLOUT API COMPATIBILITY
# =============================================================================


@app.get("/api/rollout/status")
async def rollout_status(user=Depends(require_auth)):
    """Get current rollout governance status."""
    try:
        from governance.real_data_rollout_governor import get_current_status

        return get_current_status()
    except ImportError:
        return {
            "stage": None,
            "stage_label": None,
            "real_data_pct": None,
            "consecutive_stable": None,
            "frozen": None,
            "freeze_reasons": [],
            "total_cycles": None,
            "last_cycle_id": None,
            "last_updated": None,
            "promotion_history": [],
            "status_available": False,
            "status_unavailable_reason": "Rollout governance module not available",
        }
    except Exception:
        logger.exception("Rollout status error")
        raise HTTPException(status_code=500, detail="Failed to fetch rollout status")


@app.get("/api/rollout/metrics")
async def rollout_metrics(user=Depends(require_auth)):
    """Get rollout risk metrics. Returns RiskMetrics shape matching frontend contract.

    Uses ``null`` for metrics that have not been measured yet, so the frontend can
    distinguish "not measured" from a real zero value.
    """
    try:
        from governance.real_data_rollout_governor import load_state, ROLLOUT_STAGES

        state = load_state()
        real_pct = ROLLOUT_STAGES[state.current_stage]

        return {
            "current_stage": state.current_stage,
            "real_data_pct": real_pct,
            "label_quality": None,
            "class_imbalance_ratio": None,
            "js_divergence": None,
            "unknown_token_ratio": None,
            "feature_mismatch_ratio": None,
            "fpr_current": None,
            "fpr_baseline": None,
            "drift_guard_pass": None,
            "regression_gate_pass": None,
            "determinism_gate_pass": None,
            "backtest_gate_pass": None,
            "metrics_available": False,
            "metrics_unavailable_reason": "Governance module loaded but metrics not yet computed",
            "consecutive_stable": state.consecutive_stable_cycles,
            "frozen": state.is_frozen,
            "freeze_reasons": state.freeze_reasons,
            "total_cycles": state.total_cycles_evaluated,
            "last_updated": state.last_updated,
        }
    except ImportError:
        return {
            "current_stage": None,
            "real_data_pct": None,
            "label_quality": None,
            "class_imbalance_ratio": None,
            "js_divergence": None,
            "unknown_token_ratio": None,
            "feature_mismatch_ratio": None,
            "fpr_current": None,
            "fpr_baseline": None,
            "drift_guard_pass": None,
            "regression_gate_pass": None,
            "determinism_gate_pass": None,
            "backtest_gate_pass": None,
            "metrics_available": False,
            "metrics_unavailable_reason": "Rollout governance module not available",
            "consecutive_stable": None,
            "frozen": None,
            "freeze_reasons": [],
            "total_cycles": None,
            "last_updated": None,
        }
    except Exception:
        logger.exception("Rollout metrics error")
        raise HTTPException(status_code=500, detail="Failed to fetch rollout metrics")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    reload_enabled = os.getenv("API_RELOAD", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    uvicorn.run("server:app", host=host, port=port, reload=reload_enabled)
