"""
Real voice/chat runtime helpers shared by voice routes and gateways.

These helpers make the voice stack truthful:
  - Capability reporting reflects actual local/browser readiness
  - Research/chat queries use the isolated Edge/HTTP pipeline
  - Execution dispatch returns real backend data for supported commands
"""

from __future__ import annotations

import html
import importlib
import importlib.util
import json
import logging
import os
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from backend.api.runtime_state import runtime_state
from backend.assistant.isolation_guard import IsolationGuard
from backend.assistant.query_router import ResearchSearchPipeline, ResearchStatus
from native.research_assistant.source_consensus import (
    SourceConfidence,
    SourceRecord,
    get_domain_trust,
    verify_claim,
)

logger = logging.getLogger(__name__)

_DEFAULT_WHISPER_MODEL = "base"


def _safe_get_runtime_status() -> Dict[str, Any]:
    try:
        from backend.api.runtime_api import get_runtime_status

        return get_runtime_status()
    except Exception as exc:
        logger.warning(
            "Runtime status snapshot unavailable: %s: %s",
            type(exc).__name__,
            exc,
        )
        return {
            "status": "UNAVAILABLE",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _safe_get_active_progress() -> Dict[str, Any]:
    try:
        from backend.api.field_progression_api import get_active_progress

        return get_active_progress()
    except Exception as exc:
        logger.warning(
            "Field progression snapshot unavailable: %s: %s",
            type(exc).__name__,
            exc,
        )
        return {
            "status": "UNAVAILABLE",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _safe_get_training_progress() -> Dict[str, Any]:
    try:
        from backend.api.training_progress import get_training_progress

        return get_training_progress()
    except Exception as exc:
        logger.warning(
            "Training progress snapshot unavailable: %s: %s",
            type(exc).__name__,
            exc,
        )
        return {
            "status": "UNAVAILABLE",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _safe_get_training_manager() -> Optional[Any]:
    try:
        from backend.training.state_manager import get_training_state_manager

        return get_training_state_manager()
    except Exception as exc:
        logger.warning(
            "Training state manager unavailable: %s: %s",
            type(exc).__name__,
            exc,
        )
        return None


def _safe_get_training_manager_progress() -> Dict[str, Any]:
    manager = _safe_get_training_manager()
    if manager is None:
        return {
            "status": "UNAVAILABLE",
            "error": "training state manager unavailable",
        }

    try:
        return manager.get_training_progress().to_dict()
    except Exception as exc:
        logger.warning(
            "Training manager progress snapshot unavailable: %s: %s",
            type(exc).__name__,
            exc,
        )
        return {
            "status": "UNAVAILABLE",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _import_optional_dependency(module_name: str) -> Optional[Any]:
    """Import an optional dependency without crashing startup."""
    try:
        if importlib.util.find_spec(module_name) is None:
            return None
    except Exception as exc:
        logger.warning(
            "Optional dependency probe failed for %s: %s: %s",
            module_name,
            type(exc).__name__,
            exc,
        )
        return None

    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        logger.warning(
            "Optional dependency import failed for %s: %s: %s",
            module_name,
            type(exc).__name__,
            exc,
        )
        return None


def _fallback_microphone_capabilities(error_message: Optional[str] = None) -> Dict[str, Any]:
    reason = error_message or "No local audio capture backend detected"
    return {
        "browser_relay_available": False,
        "browser_runtime": str(os.environ.get("YGB_BROWSER_RUNTIME", "")).strip().lower() or None,
        "playwright_available": False,
        "local_capture_available": False,
        "local_capture_backend": None,
        "input_device_count": 0,
        "sounddevice_available": False,
        "pyaudio_available": False,
        "whisper_available": False,
        "tts_available": False,
        "dependency_status": {
            "sounddevice": False,
            "pyaudio": False,
            "whisper": False,
            "pyttsx3": False,
            "playwright": False,
        },
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **({"error": error_message} if error_message else {}),
    }


def _fallback_stt_status(error_message: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "stt_status": "DEGRADED",
        "active_provider": "UNAVAILABLE",
        "local_only": True,
        "external_deps": [],
        "local_provider_status": "BLOCKED",
        "local_model_loaded": False,
        "local_service": {},
        "browser_relay_available": False,
        "provider_count": 0,
        "provider_status": {},
        "total_transcriptions": 0,
        "avg_confidence": 0.0,
        "circuit_breaker_state": {},
        "no_whisper_dependency": True,
        "no_google_stt_dependency": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if error_message:
        payload["error"] = error_message
    return payload


def _fallback_tts_stats(error_message: Optional[str] = None) -> Dict[str, Any]:
    reason = error_message or "TTS runtime unavailable"
    return {
        "status": "ERROR",
        "active_provider": "UNAVAILABLE",
        "privacy_mode": False,
        "total_spoken": 0,
        "total_interrupted": 0,
        "total_errors": 0,
        "provider_health": {
            "provider": "UNAVAILABLE",
            "reachable": False,
            "reason": reason,
        },
        "stream_health": {},
    }


class WhisperSTT:
    """Optional offline Whisper runtime that degrades safely when unavailable."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = _DEFAULT_WHISPER_MODEL
        self.dependency_available = False
        self.warning: Optional[str] = None
        self.model_path: Optional[str] = None
        self._whisper_module: Optional[Any] = None
        self._model: Optional[Any] = None
        self._initialize()

    @property
    def available(self) -> bool:
        return self.dependency_available

    def _mark_unavailable(self, message: str, exc: Optional[Exception] = None) -> None:
        warning = message if exc is None else f"{message}: {type(exc).__name__}: {exc}"
        self.warning = warning
        self._model = None
        logger.warning("Whisper STT unavailable: %s", warning)

    def _initialize(self) -> None:
        whisper_module = _import_optional_dependency("whisper")
        if whisper_module is None:
            self._mark_unavailable("whisper package is not installed")
            return

        self._whisper_module = whisper_module
        self.dependency_available = True
        self.warning = None

    def _load_model(self) -> Optional[Any]:
        if self._model is not None:
            return self._model
        if self._whisper_module is None:
            return None

        try:
            self._model = self._whisper_module.load_model(self.model_name)
            self.warning = None
            return self._model
        except Exception as exc:
            self._mark_unavailable("failed to load whisper base model", exc)
            return None

    def is_available(self) -> bool:
        return self.available

    def transcribe(self, audio_source: str) -> str:
        normalized_source = str(audio_source or "").strip()
        if not normalized_source:
            logger.warning("Whisper STT rejected empty audio path")
            return ""

        model = self._load_model()
        if model is None:
            return ""

        try:
            result = model.transcribe(normalized_source, fp16=False)
        except Exception as exc:
            logger.warning(
                "Whisper STT transcription failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            self.warning = f"{type(exc).__name__}: {exc}"
            return ""

        if not isinstance(result, dict):
            logger.warning(
                "Whisper STT returned unexpected payload type: %s",
                type(result).__name__,
            )
            return ""

        return str(result.get("text", "")).strip()

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "dependency_available": self.dependency_available,
            "model_name": self.model_name,
            "model_path": self.model_path,
            "model_loaded": self._model is not None,
            "reason": self.warning
            or ("offline whisper ready" if self._model is not None else "whisper dependency available"),
        }


class PyttsxTTS:
    """Optional offline pyttsx3 runtime that degrades without crashing."""

    def __init__(self):
        self.available = False
        self.dependency_available = False
        self.warning: Optional[str] = None
        self._pyttsx3_module: Optional[Any] = None
        self._engine: Optional[Any] = None
        self._initialize()

    def _mark_unavailable(self, message: str, exc: Optional[Exception] = None) -> None:
        self.warning = message if exc is None else f"{message}: {type(exc).__name__}: {exc}"
        self.available = False
        self._engine = None
        logger.warning("Local pyttsx3 TTS unavailable: %s", self.warning)

    def _initialize(self) -> None:
        pyttsx3_module = _import_optional_dependency("pyttsx3")
        if pyttsx3_module is None:
            self._mark_unavailable("pyttsx3 package is not installed")
            return

        self.dependency_available = True
        self._pyttsx3_module = pyttsx3_module
        self._ensure_engine()

    def _ensure_engine(self) -> Optional[Any]:
        if self._engine is not None:
            self.available = True
            return self._engine
        if self._pyttsx3_module is None:
            return None

        try:
            self._engine = self._pyttsx3_module.init()
            self.available = True
            self.warning = None
            return self._engine
        except Exception as exc:
            self._mark_unavailable("failed to initialize pyttsx3 engine", exc)
            return None

    def is_available(self) -> bool:
        return self.available

    def speak(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            logger.warning("Local pyttsx3 TTS rejected empty text payload")
            return False

        engine = self._ensure_engine()
        if engine is None:
            logger.warning(
                "Local pyttsx3 TTS unavailable during delivery: %s",
                self.warning or "engine not initialized",
            )
            return False

        try:
            engine.say(normalized)
            engine.runAndWait()
            return True
        except Exception as exc:
            logger.warning(
                "Local pyttsx3 TTS delivery failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            self.warning = f"{type(exc).__name__}: {exc}"
            self.available = False
            self._engine = None
            return False

    def deliver(self, text: str) -> bool:
        return self.speak(text)

    def save_to_file(self, text: str, path: Any) -> bool:
        normalized = str(text or "").strip()
        normalized_path = str(path or "").strip()
        if not normalized:
            logger.warning("Local pyttsx3 TTS rejected empty text payload for file output")
            return False
        if not normalized_path:
            logger.warning("Local pyttsx3 TTS rejected empty output path")
            return False

        engine = self._ensure_engine()
        if engine is None:
            logger.warning(
                "Local pyttsx3 TTS unavailable during file output: %s",
                self.warning or "engine not initialized",
            )
            return False

        try:
            engine.save_to_file(normalized, normalized_path)
            engine.runAndWait()
            return True
        except Exception as exc:
            logger.warning(
                "Local pyttsx3 TTS file output failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            self.warning = f"{type(exc).__name__}: {exc}"
            self.available = False
            self._engine = None
            return False

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "dependency_available": self.dependency_available,
            "engine_initialized": self._engine is not None,
            "reason": self.warning or "pyttsx3 ready",
        }


PyttxsTTS = PyttsxTTS


@dataclass
class VoiceSession:
    """Tracks an active voice/assistant runtime session."""

    session_id: str
    started_at: str
    ended_at: Optional[str] = None
    turn_count: int = 0
    last_error: Optional[str] = None


_COMMAND_REQUEST_STATUSES = frozenset(
    {"PENDING_APPROVAL", "APPROVED", "DENIED", "BLOCKED"}
)


@dataclass(frozen=True)
class AssistantCommandRequest:
    """Human-reviewable command request record for governance-blocked actions."""

    request_id: str
    command: str
    requested_by: str
    requested_at: str
    approval_status: str

    def __post_init__(self) -> None:
        if not self.command.strip():
            raise ValueError("Assistant command request rejected: command required")
        if not self.requested_by.strip():
            raise ValueError("Assistant command request rejected: requested_by required")
        if self.approval_status not in _COMMAND_REQUEST_STATUSES:
            raise ValueError(
                "Assistant command request rejected: unsupported approval status "
                f"{self.approval_status}"
            )


class CommandRequestLog:
    """Append-only bounded request ledger for assistant command approval review."""

    def __init__(self, *, max_entries: int = 1000):
        if max_entries <= 0:
            raise ValueError("Command request log rejected: max_entries must be positive")
        self._entries: deque[AssistantCommandRequest] = deque(maxlen=max_entries)

    def append(self, request: AssistantCommandRequest) -> AssistantCommandRequest:
        self._entries.append(request)
        return request

    def entries(self) -> List[AssistantCommandRequest]:
        return list(self._entries)

    def pending(self) -> List[AssistantCommandRequest]:
        return [
            request
            for request in self._entries
            if request.approval_status == "PENDING_APPROVAL"
        ]


_active_sessions: Dict[str, VoiceSession] = {}
_command_request_log = CommandRequestLog(max_entries=1000)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_requested_by(requested_by: Any) -> str:
    normalized = str(requested_by or "").strip()
    return normalized or "unknown"


def _build_command_request(
    command: str,
    requested_by: str,
    approval_status: str,
) -> AssistantCommandRequest:
    return AssistantCommandRequest(
        request_id=f"ACR-{uuid4().hex[:12].upper()}",
        command=command,
        requested_by=_normalize_requested_by(requested_by),
        requested_at=_utc_timestamp(),
        approval_status=approval_status,
    )


def _latest_active_session() -> Optional[VoiceSession]:
    if not _active_sessions:
        return None
    latest_session_id = next(reversed(_active_sessions))
    return _active_sessions.get(latest_session_id)


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


def get_pending_command_requests() -> List[AssistantCommandRequest]:
    """Return governance-blocked requests awaiting human approval."""
    return _command_request_log.pending()


def request_command(command: str, requested_by: str) -> AssistantCommandRequest:
    """Queue governance-blocked commands for review or execute approved commands in-session."""
    normalized_command = str(command or "").strip().upper()
    if not normalized_command:
        raise ValueError("Assistant command request rejected: command required")

    normalized_requested_by = _normalize_requested_by(requested_by)
    if normalized_command in _GOVERNANCE_BLOCKED_COMMANDS:
        request = _build_command_request(
            normalized_command,
            normalized_requested_by,
            "PENDING_APPROVAL",
        )
        _command_request_log.append(request)
        logger.warning(
            "Assistant command queued for human approval: command=%s requested_by=%s reason=%s",
            normalized_command,
            normalized_requested_by,
            _GOVERNANCE_BLOCKED_COMMANDS[normalized_command],
        )
        return request

    active_session = _latest_active_session()
    if active_session is None:
        request = _build_command_request(
            normalized_command,
            normalized_requested_by,
            "BLOCKED",
        )
        _command_request_log.append(request)
        logger.warning(
            "Assistant command request blocked because no active session exists: command=%s requested_by=%s",
            normalized_command,
            normalized_requested_by,
        )
        return request

    active_session.turn_count += 1
    result = dispatch_supported_command(
        normalized_command,
        {"requested_by": normalized_requested_by},
        normalized_command,
        voice_session=active_session,
    )
    approval_status = "APPROVED" if result.get("status") == "ok" else "BLOCKED"
    request = _build_command_request(
        normalized_command,
        normalized_requested_by,
        approval_status,
    )
    _command_request_log.append(request)
    return request

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
    browser_runtime = str(os.environ.get("YGB_BROWSER_RUNTIME", "")).strip().lower()
    playwright_module = _import_optional_dependency("playwright")
    sounddevice_module = _import_optional_dependency("sounddevice")
    pyaudio_module = _import_optional_dependency("pyaudio")
    whisper_module = _import_optional_dependency("whisper")
    pyttsx3_module = _import_optional_dependency("pyttsx3")
    sounddevice_available = sounddevice_module is not None
    pyaudio_available = pyaudio_module is not None
    whisper_available = whisper_module is not None
    tts_available = pyttsx3_module is not None
    dependency_status = {
        "sounddevice": sounddevice_available,
        "pyaudio": pyaudio_available,
        "whisper": whisper_available,
        "pyttsx3": tts_available,
        "playwright": playwright_module is not None,
    }

    browser_relay_available = bool(playwright_module is not None and browser_runtime == "playwright")
    local_capture_available = bool(sounddevice_available or pyaudio_available)
    local_capture_backend = "sounddevice" if sounddevice_available else ("pyaudio" if pyaudio_available else None)
    input_device_count = 0
    reason = "No local audio capture backend detected"

    if sounddevice_available:
        try:
            devices = sounddevice_module.query_devices()
            input_devices = [
                device for device in devices
                if float(device.get("max_input_channels", 0)) > 0
            ]
            input_device_count = len(input_devices)
            reason = (
                "Local capture backend available via sounddevice"
                if input_devices
                else "sounddevice installed but no input devices were reported"
            )
        except Exception as exc:
            logger.warning(
                "Microphone probe via sounddevice failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            reason = "sounddevice installed but device enumeration failed"

    if pyaudio_available:
        try:
            audio = pyaudio_module.PyAudio()
            try:
                count = 0
                for idx in range(audio.get_device_count()):
                    info = audio.get_device_info_by_index(idx)
                    if int(info.get("maxInputChannels", 0)) > 0:
                        count += 1
                input_device_count = max(input_device_count, count)
                if not sounddevice_available:
                    reason = (
                        "Local capture backend available via PyAudio"
                        if count > 0
                        else "PyAudio installed but no input devices were reported"
                    )
            finally:
                audio.terminate()
        except Exception as exc:
            logger.warning(
                "Microphone probe via PyAudio failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            if not sounddevice_available:
                reason = "PyAudio installed but device enumeration failed"

    if not local_capture_available:
        if browser_relay_available:
            reason = "Local capture unavailable; browser transcript relay available via Playwright"
        elif browser_runtime and browser_runtime != "playwright":
            reason = (
                "Local capture unavailable; browser relay disabled because "
                f"YGB_BROWSER_RUNTIME={browser_runtime}"
            )
        elif dependency_status["playwright"]:
            reason = (
                "Local capture unavailable; Playwright is installed but browser relay is disabled "
                "because YGB_BROWSER_RUNTIME is not set to playwright"
            )
        else:
            reason = (
                "Local capture unavailable; Playwright browser relay is not installed and "
                "no local audio backend was detected"
            )

    return {
        "browser_relay_available": browser_relay_available,
        "browser_runtime": browser_runtime or None,
        "playwright_available": dependency_status["playwright"],
        "local_capture_available": local_capture_available,
        "local_capture_backend": local_capture_backend,
        "input_device_count": input_device_count,
        "sounddevice_available": sounddevice_available,
        "pyaudio_available": pyaudio_available,
        "whisper_available": whisper_available,
        "tts_available": tts_available,
        "dependency_status": dependency_status,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_gpu_status_snapshot() -> Dict[str, Any]:
    """Read real GPU status without importing the entire API server."""
    mgr = _safe_get_training_manager()
    gpu = mgr.get_gpu_metrics() if mgr is not None else {}
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
        training_mgr = _safe_get_training_manager_progress()
        telemetry = _safe_get_training_progress()
        return {
            "query_type": query,
            "training_manager": training_mgr,
            "training_progress": telemetry,
        }

    if query == "QUERY_PROGRESS":
        return {
            "query_type": query,
            "field_progress": _safe_get_active_progress(),
        }

    return {
        "query_type": query,
        "runtime": _safe_get_runtime_status(),
        "training_manager": _safe_get_training_manager_progress(),
        "training_progress": _safe_get_training_progress(),
        "gpu": get_gpu_status_snapshot(),
        "field_progress": _safe_get_active_progress(),
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
            "query_result": asdict(result.query_result) if result.query_result is not None else None,
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
    try:
        from impl_v1.training.voice.stt_adapter import get_stt_status

        stt = get_stt_status()
    except Exception as exc:
        logger.warning(
            "STT status snapshot failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        stt = _fallback_stt_status(f"{type(exc).__name__}: {exc}")

    try:
        from impl_v1.training.voice.tts_streaming import TTSEngine

        tts = TTSEngine()
        tts_stats = tts.get_stats()
    except Exception as exc:
        logger.warning(
            "TTS status snapshot failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        tts_stats = _fallback_tts_stats(f"{type(exc).__name__}: {exc}")

    tts_health = tts_stats.get("provider_health", {}) or {}

    try:
        mic = probe_microphone_capabilities()
    except Exception as exc:
        logger.warning(
            "Microphone capability probe failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        mic = _fallback_microphone_capabilities(f"{type(exc).__name__}: {exc}")

    try:
        from impl_v1.training.voice.voice_metrics import get_voice_health

        metrics = get_voice_health()
    except Exception as exc:
        logger.warning(
            "Voice metrics snapshot failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        metrics = {
            "total_commands": 0,
            "success_rate": 0.0,
            "slo_met": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    whisper_runtime = WhisperSTT()
    local_tts_runtime = PyttsxTTS()
    stt = {
        **stt,
        "browser_relay_available": bool(mic.get("browser_relay_available")),
        "local_capture_available": bool(mic.get("local_capture_available")),
        "whisper_available": whisper_runtime.available,
    }
    active_mode = _normalize_mode(runtime_state.get("active_voice_mode", "SECURITY"))

    stt_ready = bool(
        stt.get("stt_status") == "STT_READY"
        or mic.get("browser_relay_available")
        or mic.get("local_capture_available")
        or whisper_runtime.available
    )
    tts_ready = bool(tts_health.get("reachable")) or local_tts_runtime.available

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
        "external_deps": [
            name
            for name, available in {
                "playwright": bool(mic.get("dependency_status", {}).get("playwright")),
                "sounddevice": bool(mic.get("dependency_status", {}).get("sounddevice")),
                "pyaudio": bool(mic.get("dependency_status", {}).get("pyaudio")),
                "whisper": whisper_runtime.dependency_available,
                "pyttsx3": local_tts_runtime.dependency_available,
            }.items()
            if available
        ],
        "no_whisper_dependency": not whisper_runtime.dependency_available,
        "no_google_stt_dependency": True,
        "microphone": mic,
        "stt": {
            **stt,
            "runtime": whisper_runtime.status(),
        },
        "tts": {
            **tts_stats,
            "health": tts_health,
            "runtime": local_tts_runtime.status(),
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
            approval_request = request_command(query, args.get("requested_by", "unknown"))
            return {
                "status": "blocked",
                "message": _GOVERNANCE_BLOCKED_COMMANDS[query],
                "command_type": query,
                "approval_request": asdict(approval_request),
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
