"""Read/parse-oriented voice service helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Optional


def parse_voice_request(
    *,
    text: str,
    requested_mode: Optional[str],
    host_session_id: Optional[str],
    user: Dict[str, Any],
    runtime_state,
    research_available: bool,
    query_router_cls,
    isolation_guard_cls,
    run_research_analysis,
    extract_intent,
    get_voice_orchestrator,
    cache_runtime_status,
    research_status_enum,
    logger,
) -> Dict[str, Any]:
    active_voice_mode = runtime_state.get("active_voice_mode", "SECURITY")
    clean_text = text.strip()
    if not clean_text:
        return {
            "intent_id": "VOC-EMPTY",
            "intent_type": "UNKNOWN",
            "raw_text": "",
            "extracted_value": None,
            "confidence": 0.0,
            "status": "INVALID",
            "block_reason": "Empty voice input",
            "active_mode": active_voice_mode,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    mode = requested_mode
    route_decision = None
    active_host_session = host_session_id or runtime_state.get(
        "active_host_action_session"
    )

    if research_available and mode is None:
        router = query_router_cls()
        route_decision = router.classify(clean_text)
        mode = route_decision.mode.value
    elif mode is None:
        mode = "SECURITY"

    runtime_state.set("active_voice_mode", mode)

    if active_host_session:
        try:
            orchestrator = get_voice_orchestrator()
            user_id = (
                user.get("sub", "unknown") if isinstance(user, dict) else "unknown"
            )
            host_intent = orchestrator.process_transcript(
                text=clean_text,
                user_id=user_id,
                device_id="browser",
                confidence=0.8,
                context_args={"host_session_id": active_host_session},
            )
            if host_intent.command_type in {
                "LAUNCH_APP",
                "OPEN_APP",
                "OPEN_URL",
                "RUN_APPROVED_TASK",
            }:
                runtime_state.set("active_voice_mode", host_intent.route_mode)
                runtime_state.set("active_host_action_session", active_host_session)
                return cache_runtime_status(
                    {
                        "intent_id": host_intent.intent_id,
                        "intent_type": host_intent.command_type,
                        "raw_text": clean_text,
                        "extracted_value": host_intent.args.get("app")
                        or host_intent.args.get("url")
                        or host_intent.args.get("task"),
                        "confidence": host_intent.confidence,
                        "status": "PARSED" if not host_intent.error else "BLOCKED",
                        "block_reason": host_intent.error,
                        "active_mode": host_intent.route_mode,
                        "args": host_intent.args,
                        "timestamp": host_intent.timestamp,
                    }
                )
        except Exception:
            logger.exception("Host-action parse failed")

    if mode == "RESEARCH" and research_available:
        guard = isolation_guard_cls()
        isolation_check = guard.pre_query_check(clean_text)
        if not isolation_check.allowed:
            return {
                "intent_id": "VOC-BLOCKED",
                "intent_type": "RESEARCH_QUERY",
                "raw_text": clean_text,
                "extracted_value": None,
                "confidence": 0.0,
                "status": "BLOCKED",
                "block_reason": isolation_check.reason,
                "active_mode": "RESEARCH",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        analysis = run_research_analysis(clean_text)
        research = analysis.get("research", {})
        verification = analysis.get("verification", {})
        audit = analysis.get("audit", {})
        success = research.get("status") == research_status_enum.SUCCESS.value
        return cache_runtime_status(
            {
                "intent_id": "VOC-RESEARCH",
                "intent_type": "RESEARCH_QUERY",
                "raw_text": clean_text,
                "extracted_value": research.get("summary"),
                "confidence": 0.9 if success else 0.3,
                "status": "PARSED" if success else "INVALID",
                "block_reason": None if success else research.get("summary"),
                "active_mode": "RESEARCH",
                "research_result": {
                    "title": research.get("title"),
                    "summary": research.get("summary"),
                    "source": research.get("source"),
                    "search_backend": research.get("search_backend"),
                    "key_terms": research.get("key_terms", []),
                    "word_count": research.get("word_count", 0),
                    "elapsed_ms": research.get("elapsed_ms", 0),
                },
                "verification": verification,
                "audit": audit,
                "route_decision": {
                    "confidence": route_decision.confidence if route_decision else 1.0,
                    "reason": route_decision.reason
                    if route_decision
                    else "Manual mode selection",
                }
                if route_decision or mode == "RESEARCH"
                else None,
                "timestamp": analysis.get("audit", {}).get(
                    "timestamp", datetime.now(UTC).isoformat()
                ),
            }
        )

    try:
        intent = extract_intent(clean_text)
        return {
            "intent_id": intent.intent_id,
            "intent_type": intent.intent_type.value,
            "raw_text": intent.raw_text,
            "extracted_value": intent.extracted_value,
            "confidence": intent.confidence,
            "status": intent.status.value,
            "block_reason": intent.block_reason,
            "active_mode": "SECURITY",
            "timestamp": intent.timestamp,
        }
    except ImportError:
        return {
            "intent_id": "VOC-ERROR",
            "intent_type": "UNKNOWN",
            "raw_text": clean_text,
            "extracted_value": None,
            "confidence": 0.0,
            "status": "INVALID",
            "block_reason": "Voice parser not available",
            "active_mode": "SECURITY",
            "timestamp": datetime.now(UTC).isoformat(),
        }


def voice_mode_payload(*, runtime_state, research_available: bool) -> Dict[str, Any]:
    return {
        "mode": runtime_state.get("active_voice_mode", "SECURITY"),
        "research_available": research_available,
    }
