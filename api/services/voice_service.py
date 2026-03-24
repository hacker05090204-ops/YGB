"""Shared voice service helpers.

Centralizes singleton ownership for voice orchestration, policy, audit, rate
limiting, STT, and TTS so voice modules do not duplicate bootstrap logic.
"""

from __future__ import annotations

from typing import Optional

from fastapi import WebSocket

from backend.auth.auth_guard import (
    get_allowed_origins,
    is_allowed_origin,
    ws_authenticate,
)

VOICE_WS_ALLOWED_ORIGINS = frozenset(
    {
        "http://localhost:3000",
        "https://ygb-nas.tail7521c4.ts.net",
    }
)


def get_voice_orchestrator():
    from impl_v1.training.voice.voice_intent_orchestrator import VoiceIntentOrchestrator

    if not hasattr(get_voice_orchestrator, "_inst"):
        get_voice_orchestrator._inst = VoiceIntentOrchestrator()
    return get_voice_orchestrator._inst


def get_voice_policy():
    from impl_v1.training.voice.voice_policy_engine import VoicePolicyEngine

    if not hasattr(get_voice_policy, "_inst"):
        get_voice_policy._inst = VoicePolicyEngine()
    return get_voice_policy._inst


def get_voice_audit():
    from impl_v1.training.voice.voice_security import VoiceAuditLog

    if not hasattr(get_voice_audit, "_inst"):
        get_voice_audit._inst = VoiceAuditLog()
    return get_voice_audit._inst


def get_voice_rate_limiter():
    from impl_v1.training.voice.voice_security import VoiceRateLimiter

    if not hasattr(get_voice_rate_limiter, "_inst"):
        get_voice_rate_limiter._inst = VoiceRateLimiter()
    return get_voice_rate_limiter._inst


def get_voice_stt_chain():
    from impl_v1.training.voice.stt_adapter import get_stt_chain

    return get_stt_chain()


def get_voice_tts_engine():
    from impl_v1.training.voice.tts_streaming import TTSEngine

    if not hasattr(get_voice_tts_engine, "_inst"):
        get_voice_tts_engine._inst = TTSEngine()
    return get_voice_tts_engine._inst


def voice_ws_origins() -> set[str]:
    return set(get_allowed_origins()) | set(VOICE_WS_ALLOWED_ORIGINS)


def voice_ws_origin_is_allowed(origin: str) -> bool:
    normalized = (origin or "").strip().rstrip("/")
    return normalized in voice_ws_origins() or is_allowed_origin(origin)


def select_bearer_subprotocol(ws: WebSocket) -> Optional[str]:
    protocols = ws.headers.get("sec-websocket-protocol", "")
    for proto in protocols.split(","):
        candidate = proto.strip()
        if candidate.startswith("bearer."):
            return candidate
    return None


async def accept_authenticated_voice_ws(ws: WebSocket, logger) -> dict:
    origin = ws.headers.get("origin", "")
    if origin and not voice_ws_origin_is_allowed(origin):
        logger.warning("[VOICE_GW] WebSocket origin rejected: %s", origin)
        await ws.close(code=4403, reason="Origin not allowed")
        return {}

    user = await ws_authenticate(ws)
    if user is None:
        await ws.close(code=4401, reason="Authentication required")
        return {}

    subprotocol = select_bearer_subprotocol(ws)
    if subprotocol:
        await ws.accept(subprotocol=subprotocol)
    else:
        await ws.accept()
    return user
