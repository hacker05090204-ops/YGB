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

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
from datetime import datetime, UTC


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
    """Voice report with bilingual content."""
    report_id: str
    report_type: VoiceReportType
    content_en: str
    content_hi: str
    suggestions: tuple  # Tuple[str, ...]
    context: Optional[str]
    timestamp: str


@dataclass(frozen=True)
class ProgressNarration:
    """Live progress update for voice output."""
    narration_id: str
    phase: str
    percentage: int
    message_en: str
    message_hi: str
    timestamp: str


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
_reports: List[VoiceReport] = []
_narrations: List[ProgressNarration] = []


def clear_reports():
    """Clear report store (for testing)."""
    _reports.clear()
    _narrations.clear()


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
        timestamp=datetime.now(UTC).isoformat(),
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
    
    tips_en = [s[0] for s in suggestions_data]
    tips_hi = [s[1] for s in suggestions_data]
    
    content_en = f"To increase impact for your {bug_type} report:\n" + "\n".join(f"- {t}" for t in tips_en)
    content_hi = f"Aapke {bug_type} report ka impact badhane ke liye:\n" + "\n".join(f"- {t}" for t in tips_hi)
    
    report = VoiceReport(
        report_id=f"RPT-{uuid.uuid4().hex[:16].upper()}",
        report_type=VoiceReportType.HIGH_IMPACT_TIPS,
        content_en=content_en,
        content_hi=content_hi,
        suggestions=tuple(tips_en),
        context=f"bug_type:{bug_type}",
        timestamp=datetime.now(UTC).isoformat(),
    )
    _reports.append(report)
    return report


def explain_report(
    report_summary: str,
    bug_type: str,
    severity: str,
) -> VoiceReport:
    """Generate final report explanation."""
    content_en = f"Your report describes a {severity} {bug_type} vulnerability. {report_summary}"
    content_hi = f"Aapka report ek {severity} {bug_type} vulnerability describe karta hai. {report_summary}"
    
    report = VoiceReport(
        report_id=f"RPT-{uuid.uuid4().hex[:16].upper()}",
        report_type=VoiceReportType.FINAL_EXPLANATION,
        content_en=content_en,
        content_hi=content_hi,
        suggestions=tuple(),
        context=f"bug:{bug_type},severity:{severity}",
        timestamp=datetime.now(UTC).isoformat(),
    )
    _reports.append(report)
    return report


def answer_follow_up(question: str, context: Dict) -> VoiceReport:
    """Answer a follow-up question about the report."""
    # Simple response generation based on question keywords
    if "payout" in question.lower() or "badhao" in question.lower():
        return generate_high_impact_tips(context.get("bug_type", "default"))
    
    content_en = f"Based on your current progress, I recommend focusing on demonstrating clear impact."
    content_hi = f"Aapke current progress ke hisaab se, clear impact demonstrate karna important hai."
    
    report = VoiceReport(
        report_id=f"RPT-{uuid.uuid4().hex[:16].upper()}",
        report_type=VoiceReportType.FOLLOW_UP_ANSWER,
        content_en=content_en,
        content_hi=content_hi,
        suggestions=tuple(),
        context=question[:100],
        timestamp=datetime.now(UTC).isoformat(),
    )
    _reports.append(report)
    return report


def get_voice_text(report: VoiceReport, language: ReportLanguage = ReportLanguage.ENGLISH) -> str:
    """Get voice text in specified language."""
    if language == ReportLanguage.HINDI:
        return report.content_hi
    return report.content_en


def can_voice_execute() -> tuple:
    """Check if voice can execute. Returns (can_execute, reason)."""
    # Voice can NEVER execute
    return False, "Voice reporting is OUTPUT ONLY - cannot execute, submit, or approve"


def get_all_narrations() -> List[ProgressNarration]:
    """Get all progress narrations (for testing/audit)."""
    return list(_narrations)


def get_all_reports() -> List[VoiceReport]:
    """Get all reports (for testing/audit)."""
    return list(_reports)
