"""
Real voice/chat runtime helpers shared by voice routes and gateways.

These helpers make the voice stack truthful:
  - Capability reporting reflects actual local/browser readiness
  - Research/chat queries use the isolated Edge/HTTP pipeline
  - Execution dispatch returns real backend data for supported commands
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from backend.api.field_progression_api import get_active_progress
from backend.api.runtime_api import get_runtime_status
from backend.api.runtime_state import runtime_state
from backend.api.training_progress import get_training_progress
from backend.assistant.isolation_guard import IsolationGuard
from backend.assistant.query_router import ResearchSearchPipeline, ResearchStatus
from backend.training.state_manager import get_training_state_manager
from native.research_assistant.source_consensus import (
    SourceConfidence,
    SourceRecord,
    get_domain_trust,
    verify_claim,
)

logger = logging.getLogger(__name__)


@dataclass
class VoiceSession:
    """Tracks an active voice/assistant runtime session."""

    session_id: str
    started_at: str
    ended_at: Optional[str] = None
    turn_count: int = 0
    last_error: Optional[str] = None


_active_sessions: Dict[str, VoiceSession] = {}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _start_voice_session(turn_count: int = 1) -> VoiceSession:
    session = VoiceSession(
        session_id=f"VRT-{uuid4().hex[:12].upper()}",
        started_at=_utc_timestamp(),
        turn_count=max(0, turn_count),
    )
    _active_sessions[session.session_id] = session
    return session


def _close_voice_session(session_id: str, *, last_error: Optional[str] = None) -> None:
    session = _active_sessions.get(session_id)
    if session is None:
        return
    session.ended_at = _utc_timestamp()
    session.last_error = last_error
    _active_sessions.pop(session_id, None)


def get_active_sessions() -> Dict[str, Dict[str, Any]]:
    """Return a snapshot of currently active voice sessions."""
    return {
        session_id: asdict(session)
        for session_id, session in _active_sessions.items()
    }

_SEARCH_ENGINE_DOMAINS = {
    "bing.com",
    "www.bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
}

_SUPPORTED_COMMANDS = {
    "QUERY_STATUS",
    "QUERY_PROGRESS",
    "QUERY_GPU",
    "QUERY_TRAINING",
    "RESEARCH_QUERY",
    "OBJECTIVE_STATUS",
    "SET_OBJECTIVE",
    "COMPLETE_OBJECTIVE",
    "LAUNCH_APP",
    "OPEN_APP",
    "OPEN_URL",
    "RUN_APPROVED_TASK",
}

_GOVERNANCE_BLOCKED_COMMANDS = {
    "SET_TARGET": "Voice/chat execution for target-setting remains dashboard-governed.",
    "SET_SCOPE": "Voice/chat execution for scope changes remains dashboard-governed.",
    "FIND_TARGETS": "Target discovery remains under security governance, not assistant execution.",
    "SCREEN_TAKEOVER": "Screen takeover is not available through the assistant runtime.",
    "REPORT_HELP": "Report help is advisory only and not an executable task.",
    "START_TRAINING": "Training control is not exposed through assistant execution.",
    "STOP_TRAINING": "Training control is not exposed through assistant execution.",
    "START_SCAN": "Scanning is not exposed through assistant execution.",
    "STOP_SCAN": "Scanning is not exposed through assistant execution.",
    "EXPORT_REPORT": "Report export is not yet wired to a trusted backend exporter.",
}


def _normalize_mode(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return "SECURITY"


def probe_microphone_capabilities() -> Dict[str, Any]:
    """Probe local microphone support without faking availability."""
    browser_relay_available = True
    local_capture_available = False
    local_capture_backend = None
    input_device_count = 0
    reason = "No local audio capture backend detected"

    try:
        import sounddevice  # type: ignore

        devices = sounddevice.query_devices()
        input_devices = [
            device for device in devices
            if float(device.get("max_input_channels", 0)) > 0
        ]
        input_device_count = len(input_devices)
        if input_devices:
            local_capture_available = True
            local_capture_backend = "sounddevice"
            reason = "Local capture available via sounddevice"
    except Exception as exc:
        logger.warning(
            "Microphone probe via sounddevice failed: %s: %s",
            type(exc).__name__,
            exc,
        )

    if not local_capture_available:
        try:
            import pyaudio  # type: ignore

            audio = pyaudio.PyAudio()
            try:
                count = 0
                for idx in range(audio.get_device_count()):
                    info = audio.get_device_info_by_index(idx)
                    if int(info.get("maxInputChannels", 0)) > 0:
                        count += 1
                input_device_count = max(input_device_count, count)
                if count > 0:
                    local_capture_available = True
                    local_capture_backend = "pyaudio"
                    reason = "Local capture available via PyAudio"
            finally:
                audio.terminate()
        except Exception as exc:
            logger.warning(
                "Microphone probe via PyAudio failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    if not local_capture_available and browser_relay_available:
        reason = "Local capture unavailable; browser transcript relay remains available"

    return {
        "browser_relay_available": browser_relay_available,
        "local_capture_available": local_capture_available,
        "local_capture_backend": local_capture_backend,
        "input_device_count": input_device_count,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_gpu_status_snapshot() -> Dict[str, Any]:
    """Read real GPU status without importing the entire API server."""
    mgr = get_training_state_manager()
    gpu = mgr.get_gpu_metrics()
    result: Dict[str, Any] = {
        "gpu_available": bool(gpu.get("gpu_available")),
        "device_name": None,
        "utilization_percent": gpu.get("gpu_usage_percent"),
        "memory_allocated_mb": gpu.get("gpu_memory_used_mb"),
        "memory_total_mb": gpu.get("gpu_memory_total_mb"),
        "temperature": gpu.get("temperature"),
        "compute_capability": None,
        "cuda_version": None,
        "error_reason": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        import torch

        if torch.cuda.is_available():
            result["device_name"] = torch.cuda.get_device_name(0)
            cap = torch.cuda.get_device_capability(0)
            result["compute_capability"] = f"{cap[0]}.{cap[1]}"
            result["cuda_version"] = torch.version.cuda
        elif not result["gpu_available"]:
            result["error_reason"] = "CUDA not available on this system"
    except Exception as exc:
        result["error_reason"] = f"torch probe failed: {type(exc).__name__}"

    return result


def collect_status_snapshot(query_type: str) -> Dict[str, Any]:
    """Collect real backend status for assistant responses."""
    query = query_type.upper()

    if query in {"QUERY_GPU", "LIST_DEVICES"}:
        return {
            "query_type": query,
            "gpu": get_gpu_status_snapshot(),
        }

    if query in {"QUERY_TRAINING", "TRAINING_STATUS"}:
        training_mgr = get_training_state_manager().get_training_progress().to_dict()
        telemetry = get_training_progress()
        return {
            "query_type": query,
            "training_manager": training_mgr,
            "training_progress": telemetry,
        }

    if query == "QUERY_PROGRESS":
        return {
            "query_type": query,
            "field_progress": get_active_progress(),
        }

    return {
        "query_type": query,
        "runtime": get_runtime_status(),
        "training_manager": get_training_state_manager().get_training_progress().to_dict(),
        "training_progress": get_training_progress(),
        "gpu": get_gpu_status_snapshot(),
        "field_progress": get_active_progress(),
    }


def _extract_candidate_sources(raw_html: str) -> List[SourceRecord]:
    """Extract distinct candidate source URLs from search-result HTML."""
    urls = re.findall(r"https?://[^\"'<>\\s)]+", raw_html or "")
    sources: List[SourceRecord] = []
    seen_domains = set()

    for raw_url in urls:
        url = html.unescape(raw_url.rstrip(".,;:"))
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if not domain or domain in _SEARCH_ENGINE_DOMAINS:
            continue
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        sources.append(
            SourceRecord(
                source_url=url,
                source_name=domain,
                trust_score=get_domain_trust(url),
            )
        )
        if len(sources) >= 5:
            break

    return sources


def run_research_analysis(query: str) -> Dict[str, Any]:
    """Run isolated research mode and return summary + verification metadata."""
    guard = IsolationGuard()
    isolation_check = guard.pre_query_check(query)
    if not isolation_check.allowed:
        audit = guard.log_research_query(
            query=query,
            result_status=ResearchStatus.BLOCKED.value,
            checks_passed=0,
            checks_failed=1,
            violations=[isolation_check.reason],
        )
        return {
            "status": "blocked",
            "message": isolation_check.reason,
            "query": query,
            "audit": {
                "entry_id": audit.entry_id,
                "timestamp": audit.timestamp,
            },
        }

    pipeline = ResearchSearchPipeline()
    result = pipeline.search(query)

    raw_html = ""
    search_backend = result.source
    try:
        raw_html, search_backend = pipeline._fetch_search_html(query)
    except Exception as exc:
        logger.warning("Research corroboration fetch failed: %s", exc)

    sources = _extract_candidate_sources(raw_html)
    if not sources and result.source:
        fallback_url = f"https://{result.source}"
        sources.append(
            SourceRecord(
                source_url=fallback_url,
                source_name=result.source,
                trust_score=get_domain_trust(fallback_url),
            )
        )

    verification = verify_claim(result.summary or query, sources)
    verification_confidence = verification.confidence
    verification_reason = verification.reason

    # Search result corroboration is useful, but we should not overstate it as
    # fully verified unless source pages were independently fetched and checked.
    if verification_confidence == SourceConfidence.VERIFIED:
        verification_confidence = SourceConfidence.LIKELY
        verification_reason = (
            "Multiple search-result domains agree, but underlying source pages "
            "were not independently fetched for full verification"
        )

    if result.status != ResearchStatus.SUCCESS:
        verification_confidence = SourceConfidence.UNVERIFIED
        if not verification_reason:
            verification_reason = result.summary

    audit = guard.log_research_query(
        query=query,
        result_status=result.status.value,
        checks_passed=5,
        checks_failed=0,
        violations=[],
    )

    return {
        "status": "ok" if result.status == ResearchStatus.SUCCESS else "degraded",
        "query": query,
        "mode": "RESEARCH",
        "research": {
            "status": result.status.value,
            "title": result.title,
            "summary": result.summary,
            "source": result.source,
            "search_backend": search_backend or result.source,
            "key_terms": list(result.key_terms),
            "word_count": result.word_count,
            "elapsed_ms": result.elapsed_ms,
        },
        "verification": {
            "confidence": verification_confidence,
            "reason": verification_reason,
            "independent_count": len(sources),
            "sources": [source.to_dict() for source in sources],
        },
        "audit": {
            "entry_id": audit.entry_id,
            "timestamp": audit.timestamp,
        },
    }


def build_voice_pipeline_status() -> Dict[str, Any]:
    """Build a truthful snapshot for the voice/chat pipeline."""
    from impl_v1.training.voice.stt_adapter import get_stt_status
    from impl_v1.training.voice.tts_streaming import TTSEngine
    from impl_v1.training.voice.voice_metrics import get_voice_health

    stt = get_stt_status()
    tts = TTSEngine()
    tts_stats = tts.get_stats()
    tts_health = tts_stats.get("provider_health", {})
    mic = probe_microphone_capabilities()
    metrics = get_voice_health()
    active_mode = _normalize_mode(runtime_state.get("active_voice_mode", "SECURITY"))

    stt_ready = bool(stt.get("browser_relay_available")) or stt.get("stt_status") == "STT_READY"
    tts_ready = bool(tts_health.get("reachable"))

    if stt_ready and tts_ready:
        pipeline_status = "ONLINE"
    elif stt_ready or tts_ready:
        pipeline_status = "DEGRADED"
    else:
        pipeline_status = "OFFLINE"

    active_host_session = runtime_state.get("active_host_action_session")
    try:
        from backend.governance.host_action_governor import HostActionGovernor

        host_governance = HostActionGovernor().status_snapshot(active_host_session)
    except Exception as exc:
        logger.warning(
            "Host governance status snapshot failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        host_governance = {
            "ledger_entries": 0,
            "chain_valid": False,
            "active_session_id": active_host_session,
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        from backend.assistant.task_focus import TaskFocusManager

        focus_status = TaskFocusManager().status_snapshot()
    except Exception as exc:
        logger.warning(
            "Task focus status snapshot failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        focus_status = {
            "has_active_objective": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "pipeline_status": pipeline_status,
        "mode": active_mode,
        "stt_status": stt.get("stt_status", "DEGRADED"),
        "tts_status": "TTS_READY" if tts_ready else "DEGRADED",
        "local_only": stt.get("local_only", True),
        "external_deps": [],
        "no_whisper_dependency": True,
        "no_google_stt_dependency": True,
        "microphone": mic,
        "stt": stt,
        "tts": {
            **tts_stats,
            "health": tts_health,
        },
        "metrics_summary": {
            "total_commands": metrics.get("total_commands"),
            "success_rate": metrics.get("success_rate"),
            "slo_met": metrics.get("slo_met"),
        },
        "task_focus": focus_status,
        "host_action_governance": host_governance,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def dispatch_supported_command(
    command_type: str,
    args: Dict[str, str],
    transcript_text: str,
    *,
    voice_session: Optional[VoiceSession] = None,
) -> Dict[str, Any]:
    """Dispatch a supported assistant command and return a structured result."""
    query = command_type.upper()
    owns_session = voice_session is None
    session = voice_session or _start_voice_session()
    session_error: Optional[str] = None

    try:
        if query in {"QUERY_STATUS", "QUERY_PROGRESS", "QUERY_GPU", "QUERY_TRAINING", "LIST_DEVICES"}:
            payload = collect_status_snapshot(query)
            return {
                "status": "ok",
                "command_type": query,
                "output": json.dumps(payload, indent=2, sort_keys=True, default=str),
                "data": payload,
            }

        if query == "RESEARCH_QUERY":
            return dispatch_supported_command(
                "RESEARCH_QUERY_INTERNAL",
                {"query": args.get("query") or transcript_text},
                transcript_text,
                voice_session=session,
            )

        if query == "RESEARCH_QUERY_INTERNAL":
            return run_research_analysis(args.get("query") or transcript_text)

        if query == "OBJECTIVE_STATUS":
            from backend.assistant.task_focus import TaskFocusManager

            payload = TaskFocusManager().status_snapshot()
            return {
                "status": "ok",
                "command_type": query,
                "output": json.dumps(payload, indent=2, sort_keys=True, default=str),
                "data": payload,
            }

        if query == "SET_OBJECTIVE":
            from backend.assistant.task_focus import TaskFocusManager

            result = TaskFocusManager().start_objective(
                title=args.get("title", ""),
                requested_by=args.get("requested_by", "unknown"),
                summary=args.get("summary", ""),
                force_switch=str(args.get("force_switch", "")).strip().lower() in {"1", "true", "yes", "force"},
            )
            return {
                "status": "ok" if result.get("status") == "ok" else result.get("status", "blocked").lower(),
                "command_type": query,
                "output": json.dumps(result, indent=2, sort_keys=True, default=str),
                "data": result,
                "message": result.get("message"),
            }

        if query == "COMPLETE_OBJECTIVE":
            from backend.assistant.task_focus import TaskFocusManager

            result = TaskFocusManager().complete_active_objective(args.get("summary", ""))
            return {
                "status": "ok" if result.get("status") == "ok" else result.get("status", "blocked").lower(),
                "command_type": query,
                "output": json.dumps(result, indent=2, sort_keys=True, default=str),
                "data": result,
                "message": result.get("message"),
            }

        if query in {"LAUNCH_APP", "OPEN_APP", "OPEN_URL", "RUN_APPROVED_TASK"}:
            from impl_v1.training.voice.voice_executors import (
                AppRunnerExecutor,
                ApprovedTaskExecutor,
                BrowserExecutor,
                ExecStatus,
            )

            try:
                from backend.governance.host_action_governor import HostActionGovernor

                governor = HostActionGovernor()
                approval = governor.validate_request(
                    args.get("host_session_id", ""),
                    query,
                    args,
                )
            except Exception as exc:
                logger.warning(
                    "Host governance validation failed for command %s: %s: %s",
                    query,
                    type(exc).__name__,
                    exc,
                )
                return {
                    "status": "blocked",
                    "message": f"Host governance unavailable: {type(exc).__name__}",
                    "command_type": query,
                }
            if not approval["allowed"]:
                return {
                    "status": "blocked",
                    "message": approval["reason"],
                    "command_type": query,
                }

            intent_id = args.get("_intent_id", "INT-UNKNOWN")

            if query in {"LAUNCH_APP", "OPEN_APP"}:
                result = AppRunnerExecutor().execute(
                    intent_id,
                    "launch",
                    approval["canonical_app"],
                    launch_command=approval["command"],
                )
            elif query == "OPEN_URL":
                result = BrowserExecutor().execute(
                    intent_id,
                    args.get("url", ""),
                    launch_command=approval["command"],
                )
            else:
                result = ApprovedTaskExecutor().execute(
                    intent_id,
                    approval["canonical_task"],
                    command=approval["command"],
                    workdir=approval.get("cwd"),
                )

            if result.status == ExecStatus.SUCCESS:
                return {
                    "status": "ok",
                    "command_type": query,
                    "output": result.output,
                    "executor": result.executor,
                    "audit_hash": result.audit_hash,
                    "execution_ms": result.execution_ms,
                }

            result_status = "blocked" if result.status == ExecStatus.BLOCKED else "failed"
            return {
                "status": result_status,
                "command_type": query,
                "message": result.output,
                "executor": result.executor,
                "audit_hash": result.audit_hash,
            }

        if query in _GOVERNANCE_BLOCKED_COMMANDS:
            return {
                "status": "blocked",
                "message": _GOVERNANCE_BLOCKED_COMMANDS[query],
                "command_type": query,
            }

        return {
            "status": "blocked",
            "message": f"Unsupported assistant command: {query}",
            "command_type": query,
        }
    except Exception as exc:
        session_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Voice runtime command failed for session %s and command %s: %s",
            session.session_id,
            query,
            session_error,
        )
        raise
    finally:
        if owns_session:
            _close_voice_session(session.session_id, last_error=session_error)


def record_objective_progress(intent: Any, result: Dict[str, Any]) -> None:
    """Persist grounded command outcomes against the active objective."""
    try:
        from backend.assistant.task_focus import TaskFocusManager
    except Exception as exc:
        logger.warning(
            "Task focus manager unavailable while recording objective progress: %s: %s",
            type(exc).__name__,
            exc,
        )
        return

    query = str(intent.command_type).upper()
    if query in {"OBJECTIVE_STATUS", "SET_OBJECTIVE"}:
        return

    summary = (
        result.get("message")
        or result.get("output")
        or result.get("research", {}).get("summary")
        or result.get("status")
        or "Action processed"
    )

    if isinstance(summary, str) and len(summary) > 800:
        summary = summary[:800]

    metadata = {
        "command_type": intent.command_type,
        "mode": getattr(intent, "route_mode", None),
        "status": result.get("status"),
    }

    if result.get("research"):
        metadata["source"] = result["research"].get("source")
    if result.get("audit_hash"):
        metadata["audit_hash"] = result.get("audit_hash")

    TaskFocusManager().append_step(
        kind=intent.command_type,
        summary=str(summary),
        grounded=result.get("status") == "ok",
        metadata=metadata,
    )


def execute_orchestrated_intent(
    orchestrator: Any,
    intent_id: str,
    confirmer_id: Optional[str],
    *,
    policy: Optional[Any] = None,
    audit: Optional[Any] = None,
    user_id: str = "unknown",
    device_id: str = "browser",
) -> Dict[str, Any]:
    """Execute a previously parsed intent if it is supported and allowed."""
    session = _start_voice_session()
    session_error: Optional[str] = None

    try:
        intent = orchestrator.get_intent(intent_id)
        if intent is None:
            session_error = "INTENT_NOT_FOUND"
            return {
                "status": "error",
                "message": "INTENT_NOT_FOUND",
            }

        if intent.error and not intent.executed:
            session_error = intent.error
            return {
                "status": "blocked",
                "message": intent.error,
                "intent_id": intent_id,
                "command_type": intent.command_type,
            }

        if intent.requires_confirmation and not intent.confirmed:
            if not confirmer_id:
                session_error = "Confirmation required before execution"
                return {
                    "status": "blocked",
                    "gate": "CONFIRMATION",
                    "message": "Confirmation required before execution",
                    "intent_id": intent_id,
                    "command_type": intent.command_type,
                }
            if not orchestrator.confirm_intent(intent_id, confirmer_id):
                session_error = "Intent not confirmable"
                return {
                    "status": "blocked",
                    "gate": "CONFIRMATION",
                    "message": "Intent not confirmable",
                    "intent_id": intent_id,
                    "command_type": intent.command_type,
                }
            intent = orchestrator.get_intent(intent_id)

        if not orchestrator.is_ready_to_execute(intent_id):
            session_error = "Intent is not ready to execute"
            return {
                "status": "blocked",
                "gate": "READINESS",
                "message": "Intent is not ready to execute",
                "intent_id": intent_id,
                "command_type": intent.command_type,
            }

        if policy is not None:
            decision = policy.evaluate(intent.command_type, intent.args)
            if decision.verdict.value != "ALLOWED":
                if audit is not None:
                    audit.log(
                        user_id=user_id,
                        device_id=device_id,
                        transcript=intent.transcript_text,
                        intent=intent.command_type,
                        action="BLOCKED",
                        policy=decision.verdict.value,
                        result=decision.reason,
                    )
                orchestrator.mark_failed(intent_id, decision.reason)
                session_error = decision.reason
                return {
                    "status": "blocked",
                    "gate": "POLICY",
                    "message": decision.reason,
                    "intent_id": intent_id,
                    "command_type": intent.command_type,
                    "policy_verdict": decision.verdict.value,
                }

        dispatch_args = dict(intent.args)
        dispatch_args["_intent_id"] = intent.intent_id
        dispatch_args.setdefault("requested_by", getattr(intent, "user_id", user_id))

        result = dispatch_supported_command(
            intent.command_type,
            dispatch_args,
            intent.transcript_text,
            voice_session=session,
        )

        if result.get("status") == "ok":
            result_text = result.get("output")
            if not result_text and "research" in result:
                result_text = result["research"].get("summary")
            if not result_text and "data" in result:
                result_text = json.dumps(result["data"], sort_keys=True, default=str)
            orchestrator.mark_executed(intent_id, result_text or "OK")
            record_objective_progress(intent, result)
            if audit is not None:
                audit.log(
                    user_id=user_id,
                    device_id=device_id,
                    transcript=intent.transcript_text,
                    intent=intent.command_type,
                    action="EXECUTED",
                    policy="ALLOWED",
                    result="OK",
                )
            return {
                "status": "ok",
                "executed": True,
                "intent_id": intent_id,
                "command_type": intent.command_type,
                "mode": intent.route_mode,
                **result,
            }

        error_message = result.get("message", "Execution blocked")
        session_error = error_message
        orchestrator.mark_failed(intent_id, error_message)
        if audit is not None:
            audit.log(
                user_id=user_id,
                device_id=device_id,
                transcript=intent.transcript_text,
                intent=intent.command_type,
                action="BLOCKED",
                policy="ALLOWED",
                result=error_message,
            )
        return {
            "status": result.get("status", "blocked"),
            "executed": False,
            "intent_id": intent_id,
            "command_type": intent.command_type,
            "mode": intent.route_mode,
            **result,
        }
    except Exception as exc:
        session_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Voice session %s failed for intent %s: %s",
            session.session_id,
            intent_id,
            session_error,
        )
        raise
    finally:
        _close_voice_session(session.session_id, last_error=session_error)
