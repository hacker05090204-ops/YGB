"""
intent_router.py — Voice Intent Router

Routes voice commands to appropriate mode:
  - Clarification mode: "what is...", "explain...", "define..."
  - Research mode: "find...", "search...", "look up..."
  - Status mode: "status", "progress", "how is..."

Blocked intents:
  - Hunt trigger: ALWAYS blocked from voice
  - Submit: ALWAYS blocked from voice
  - Auto-mode: ALWAYS blocked from voice

NO auto-hunt from voice. NO submission from voice.
"""

from typing import Optional
from backend.voice.language_detector import LanguageDetector


class VoiceIntent:
    """Represents a classified voice intent."""

    def __init__(self, mode: str, action: str, allowed: bool, reason: str):
        self.mode = mode
        self.action = action
        self.allowed = allowed
        self.reason = reason

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "action": self.action,
            "allowed": self.allowed,
            "reason": self.reason
        }


class IntentRouter:
    """Routes voice input to appropriate modes."""

    ALLOW_VOICE_HUNT = False
    ALLOW_VOICE_SUBMIT = False
    ALLOW_VOICE_AUTO_MODE = False

    CLARIFICATION_KEYWORDS = {
        "en": {"what", "explain", "define", "describe", "meaning", "how does"},
        "hi": {"kya", "samjhao", "batao", "matlab"},
        "mr": {"kay", "samja", "sanga", "arth"}
    }

    RESEARCH_KEYWORDS = {
        "en": {"find", "search", "look", "discover", "scan", "analyze"},
        "hi": {"dhundho", "khojo", "dekho"},
        "mr": {"shodha", "bagha", "shodhun"}
    }

    STATUS_KEYWORDS = {
        "en": {"status", "progress", "report", "metrics", "how is"},
        "hi": {"sthiti", "pragati"},
        "mr": {"sthiti", "pragati"}
    }

    BLOCKED_KEYWORDS = {
        "hunt", "submit", "send", "report", "auto", "execute",
        "attack", "exploit", "target", "bhejo", "pathva"
    }

    def __init__(self):
        self._detector = LanguageDetector()
        self._total_routed = 0
        self._total_blocked = 0

    def route(self, text: str) -> VoiceIntent:
        """
        Route a voice command to the appropriate intent.

        Returns VoiceIntent with mode, action, allowed flag.
        """
        if not text or not text.strip():
            return VoiceIntent("idle", "none", False, "EMPTY_INPUT")

        text_lower = text.lower().strip()
        lang_result = self._detector.detect(text)
        lang = lang_result["language"]

        # Check blocked intents FIRST
        for kw in self.BLOCKED_KEYWORDS:
            if kw in text_lower:
                self._total_blocked += 1
                return VoiceIntent(
                    "blocked", kw, False,
                    f"VOICE_BLOCKED: '{kw}' cannot be triggered by voice"
                )

        words = set(text_lower.split())

        # Clarification mode
        clarify = self.CLARIFICATION_KEYWORDS.get(lang, set())
        if words & clarify:
            self._total_routed += 1
            return VoiceIntent("clarification", "explain", True,
                             f"CLARIFY_MODE: lang={lang}")

        # Research mode
        research = self.RESEARCH_KEYWORDS.get(lang, set())
        if words & research:
            self._total_routed += 1
            return VoiceIntent("research", "search", True,
                             f"RESEARCH_MODE: lang={lang}")

        # Status mode
        status = self.STATUS_KEYWORDS.get(lang, set())
        if words & status:
            self._total_routed += 1
            return VoiceIntent("status", "query", True,
                             f"STATUS_MODE: lang={lang}")

        # Default: clarification (safe fallback)
        self._total_routed += 1
        return VoiceIntent("clarification", "general", True,
                         f"DEFAULT_CLARIFY: lang={lang}")

    @property
    def total_routed(self) -> int:
        return self._total_routed

    @property
    def total_blocked(self) -> int:
        return self._total_blocked
