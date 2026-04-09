# G17: Advanced Voice Reporting
"""
Voice output for progress narration, report explanation, and suggestions.

SUPPORTS:
- Live progress narration
- Final report explanation
- High impact tips ("is report me aur kya add kare jisse payout badhe")
- Follow-up answers

VOICE NEVER:
- Executes
- Submits
- Approves
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import logging
from typing import Dict, Optional
import uuid


logger = logging.getLogger(__name__)
VALID_DELIVERY_STATUSES = frozenset({"QUEUED", "DELIVERED", "FAILED"})
VOICE_REPORTING_BACKEND_MESSAGE = (
    "Voice reporting requires a provisioned TTS backend. "
    "Provide a real TTS adapter exposing availability and delivery methods before generating voice reports."
)


class RealBackendNotConfiguredError(RuntimeError):
    """Raised when the required real TTS backend is not provisioned."""


class VoiceReportType(Enum):
    """CLOSED ENUM - 5 report types"""

    PROGRESS_NARRATION = "PROGRESS_NARRATION"
    FINAL_EXPLANATION = "FINAL_EXPLANATION"
    HIGH_IMPACT_TIPS = "HIGH_IMPACT_TIPS"
    FOLLOW_UP_ANSWER = "FOLLOW_UP_ANSWER"
    ERROR_EXPLANATION = "ERROR_EXPLANATION"


class ReportLanguage(Enum):
    """CLOSED ENUM - 2 languages"""

    ENGLISH = "ENGLISH"
    HINDI = "HINDI"


@dataclass(frozen=True)
class VoiceReport:
    """Voice report with delivery metadata."""

    report_id: str
    content: str
    generated_at: str
    delivery_status: str
    tts_ready: bool
    report_type: Optional[VoiceReportType] = None
    content_en: str = ""
    content_hi: str = ""
    suggestions: tuple[str, ...] = ()
    context: Optional[str] = None

    def __post_init__(self) -> None:
        if self.delivery_status not in VALID_DELIVERY_STATUSES:
            raise ValueError(f"Unsupported delivery status: {self.delivery_status}")


@dataclass(frozen=True)
class ProgressNarration:
    """Live progress update for voice output."""

    narration_id: str
    phase: str
    percentage: int
    message_en: str
    message_hi: str
    timestamp: str


class ReportQueue:
    """Bounded queue for pending voice reports."""

    def __init__(self, max_pending: int = 100) -> None:
        self.max_pending = max_pending
        self._pending: deque[VoiceReport] = deque()

    def enqueue(self, report: VoiceReport) -> VoiceReport:
        if report.delivery_status != "QUEUED":
            return report

        if len(self._pending) >= self.max_pending:
            dropped = self._pending.popleft()
            logger.warning("Dropping oldest queued voice report: %s", dropped.report_id)

        self._pending.append(report)
        return report

    @property
    def pending(self) -> list[VoiceReport]:
        return list(self._pending)

    def get_pending(self) -> list[VoiceReport]:
        return list(self._pending)

    def clear(self) -> None:
        self._pending.clear()


class VoiceReporter:
    """Voice report generator backed by a confirmed TTS delivery path."""

    def __init__(
        self,
        tts_backend: Optional[object] = None,
        report_queue: Optional[ReportQueue] = None,
    ) -> None:
        self._tts_backend = tts_backend
        self.report_queue = report_queue or ReportQueue()

    def generate_report(self, content: str) -> VoiceReport:
        return self._build_report(content=content)

    def _build_report(
        self,
        content: str,
        report_type: Optional[VoiceReportType] = None,
        content_en: Optional[str] = None,
        content_hi: Optional[str] = None,
        suggestions: tuple[str, ...] = (),
        context: Optional[str] = None,
    ) -> VoiceReport:
        delivery_status, tts_ready = self._deliver(content)
        report = VoiceReport(
            report_id=f"RPT-{uuid.uuid4().hex[:16].upper()}",
            content=content,
            generated_at=_utc_now(),
            delivery_status=delivery_status,
            tts_ready=tts_ready,
            report_type=report_type,
            content_en=content_en or content,
            content_hi=content_hi or content,
            suggestions=suggestions,
            context=context,
        )

        _reports.append(report)
        return report

    def _deliver(self, content: str) -> tuple[str, bool]:
        delivery_method = self._resolve_delivery_method()
        if delivery_method is None:
            raise RealBackendNotConfiguredError(VOICE_REPORTING_BACKEND_MESSAGE)

        try:
            delivered = bool(delivery_method(content))
        except Exception as exc:
            logger.warning("Voice report delivery failed: %s", exc)
            return "FAILED", False

        if delivered:
            return "DELIVERED", True
        return "FAILED", False

    def _resolve_delivery_method(self):
        backend = self._tts_backend
        if backend is None:
            return None

        availability_check = getattr(backend, "is_available", None)
        if callable(availability_check):
            if not bool(availability_check()):
                return None
        elif hasattr(backend, "available"):
            if not bool(getattr(backend, "available")):
                return None
        else:
            return None

        for method_name in ("deliver", "speak", "generate_audio"):
            delivery_method = getattr(backend, method_name, None)
            if callable(delivery_method):
                return delivery_method

        return None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _build_degraded_default_report(
    *,
    content: str,
    report_type: Optional[VoiceReportType] = None,
    content_en: Optional[str] = None,
    content_hi: Optional[str] = None,
    suggestions: tuple[str, ...] = (),
    context: Optional[str] = None,
) -> VoiceReport:
    report = VoiceReport(
        report_id=f"RPT-{uuid.uuid4().hex[:16].upper()}",
        content=content,
        generated_at=_utc_now(),
        delivery_status="FAILED",
        tts_ready=False,
        report_type=report_type,
        content_en=content_en or content,
        content_hi=content_hi or content,
        suggestions=suggestions,
        context=context,
    )
    _reports.append(report)
    return report


def _build_default_report(
    *,
    content: str,
    report_type: Optional[VoiceReportType] = None,
    content_en: Optional[str] = None,
    content_hi: Optional[str] = None,
    suggestions: tuple[str, ...] = (),
    context: Optional[str] = None,
) -> VoiceReport:
    try:
        return _default_voice_reporter._build_report(
            content=content,
            report_type=report_type,
            content_en=content_en,
            content_hi=content_hi,
            suggestions=suggestions,
            context=context,
        )
    except RealBackendNotConfiguredError as exc:
        logger.warning(
            "Voice reporting backend unavailable; returning undelivered report instead: %s",
            exc,
        )
        return _build_degraded_default_report(
            content=content,
            report_type=report_type,
            content_en=content_en,
            content_hi=content_hi,
            suggestions=suggestions,
            context=context,
        )


# High impact suggestions templates
HIGH_IMPACT_SUGGESTIONS = {
    "xss": [
        ("Try chained XSS with session hijacking", "XSS ke saath session hijack ka chain banao"),
        ("Demonstrate data exfiltration impact", "Data exfiltration ka impact dikhao"),
        ("Show account takeover possibility", "Account takeover ho sakta hai ye dikhao"),
    ],
    "sqli": [
        ("Extract sensitive data to prove impact", "Sensitive data nikalo impact prove karne ke liye"),
        ("Demonstrate database access", "Database access dikha do"),
        ("Show authentication bypass", "Authentication bypass dikhao"),
    ],
    "idor": [
        ("Access admin data if possible", "Admin data access karo agar ho sake"),
        ("Show mass data exposure risk", "Mass data exposure ka risk dikhao"),
        ("Demonstrate PII access", "PII access prove karo"),
    ],
    "rce": [
        ("Document full chain of exploitation", "Full exploitation chain document karo"),
        ("Show potential for lateral movement", "Lateral movement possible hai ye dikhao"),
        ("Demonstrate server compromise scope", "Server compromise ka scope batao"),
    ],
    "default": [
        ("Add detailed reproduction steps", "Detailed reproduction steps add karo"),
        ("Include impact assessment", "Impact assessment include karo"),
        ("Show business logic impact", "Business logic impact dikhao"),
    ],
}

# In-memory report store
_reports: list[VoiceReport] = []
_narrations: list[ProgressNarration] = []
_default_voice_reporter = VoiceReporter()
REPORT_QUEUE = _default_voice_reporter.report_queue


def clear_reports():
    """Clear report store (for testing)."""

    _reports.clear()
    _narrations.clear()
    _default_voice_reporter.report_queue.clear()


def create_progress_narration(
    phase: str,
    percentage: int,
    message_en: str,
    message_hi: str,
) -> ProgressNarration:
    """Create a progress narration update."""

    narration = ProgressNarration(
        narration_id=f"NAR-{uuid.uuid4().hex[:16].upper()}",
        phase=phase,
        percentage=min(100, max(0, percentage)),
        message_en=message_en,
        message_hi=message_hi,
        timestamp=_utc_now(),
    )
    _narrations.append(narration)
    return narration


def generate_high_impact_tips(bug_type: str) -> VoiceReport:
    """
    Generate high impact tips for a bug type.

    Responds to: "is report me aur kya add kar sakte hain high impact ke liye"
    """

    suggestions_data = HIGH_IMPACT_SUGGESTIONS.get(
        bug_type.lower(),
        HIGH_IMPACT_SUGGESTIONS["default"],
    )

    tips_en = [item[0] for item in suggestions_data]
    tips_hi = [item[1] for item in suggestions_data]

    content_en = f"To increase impact for your {bug_type} report:\n" + "\n".join(f"- {tip}" for tip in tips_en)
    content_hi = f"Aapke {bug_type} report ka impact badhane ke liye:\n" + "\n".join(f"- {tip}" for tip in tips_hi)

    return _build_default_report(
        content=content_en,
        report_type=VoiceReportType.HIGH_IMPACT_TIPS,
        content_en=content_en,
        content_hi=content_hi,
        suggestions=tuple(tips_en),
        context=f"bug_type:{bug_type}",
    )


def explain_report(
    report_summary: str,
    bug_type: str,
    severity: str,
) -> VoiceReport:
    """Generate final report explanation."""

    content_en = f"Your report describes a {severity} {bug_type} vulnerability. {report_summary}"
    content_hi = f"Aapka report ek {severity} {bug_type} vulnerability describe karta hai. {report_summary}"

    return _build_default_report(
        content=content_en,
        report_type=VoiceReportType.FINAL_EXPLANATION,
        content_en=content_en,
        content_hi=content_hi,
        suggestions=tuple(),
        context=f"bug:{bug_type},severity:{severity}",
    )


def answer_follow_up(question: str, context: Dict) -> VoiceReport:
    """Answer a follow-up question about the report."""

    if "payout" in question.lower() or "badhao" in question.lower():
        return generate_high_impact_tips(context.get("bug_type", "default"))

    content_en = "Based on your current progress, I recommend focusing on demonstrating clear impact."
    content_hi = "Aapke current progress ke hisaab se, clear impact demonstrate karna important hai."

    return _build_default_report(
        content=content_en,
        report_type=VoiceReportType.FOLLOW_UP_ANSWER,
        content_en=content_en,
        content_hi=content_hi,
        suggestions=tuple(),
        context=question[:100],
    )


def get_voice_text(report: VoiceReport, language: ReportLanguage = ReportLanguage.ENGLISH) -> str:
    """Get voice text in specified language."""

    if language == ReportLanguage.HINDI and report.content_hi:
        return report.content_hi
    if report.content_en:
        return report.content_en
    return report.content


def can_voice_execute() -> tuple:
    """Check if voice can execute. Returns (can_execute, reason)."""

    return False, "Voice reporting is OUTPUT ONLY - cannot execute, submit, or approve"


def get_all_narrations() -> list[ProgressNarration]:
    """Get all progress narrations (for testing/audit)."""

    return list(_narrations)


def get_all_reports() -> list[VoiceReport]:
    """Get all reports (for testing/audit)."""

    return list(_reports)


def get_pending_reports() -> list[VoiceReport]:
    """Get pending queued voice reports."""

    return _default_voice_reporter.report_queue.get_pending()
