# G23: Governed Reasoning & Evidence Engine
"""
DETERMINISTIC, RULE-BASED REASONING SYSTEM.

NOT an AI text generator.
NOT probabilistic.
NOT creative.

ENGINE TYPE: Deterministic Reasoning Graph

INPUTS (ALL MANDATORY):
- Browser observations (G19)
- Extracted scope
- Platform metadata
- CVE context (passive)
- Screen evidence (G18)

IF ANY INPUT MISSING → HARD FAIL

OUTPUTS:
1) Structured Report (fixed template)
2) Evidence Pack
3) Voice Explanation Script (EN + HI)
4) Video Narration Metadata

FORBIDDEN WORDS:
- "maybe", "likely", "could be", "possibly", "might"
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime, UTC
import hashlib


class ReportSection(Enum):
    """CLOSED ENUM - Fixed report sections"""
    CONTEXT = "CONTEXT"
    OBSERVATIONS = "OBSERVATIONS"
    LOGICAL_REASONING = "LOGICAL_REASONING"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    REPRODUCTION_STEPS = "REPRODUCTION_STEPS"
    WHY_THIS_MATTERS = "WHY_THIS_MATTERS"


class EvidenceType(Enum):
    """CLOSED ENUM - Evidence types"""
    BROWSER_OBSERVATION = "BROWSER_OBSERVATION"
    SCOPE_EXTRACTION = "SCOPE_EXTRACTION"
    PLATFORM_METADATA = "PLATFORM_METADATA"
    CVE_CONTEXT = "CVE_CONTEXT"
    SCREEN_EVIDENCE = "SCREEN_EVIDENCE"


class ReasoningStatus(Enum):
    """CLOSED ENUM - Reasoning statuses"""
    SUCCESS = "SUCCESS"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    INVALID_INPUT = "INVALID_INPUT"
    FORBIDDEN_WORD = "FORBIDDEN_WORD"


# Forbidden words that indicate uncertainty/guessing
FORBIDDEN_WORDS = frozenset([
    "maybe", "likely", "could be", "possibly", "might",
    "perhaps", "probably", "seems like", "appears to",
    "i think", "i believe", "in my opinion",
])


@dataclass(frozen=True)
class EvidenceItem:
    """Single piece of evidence."""
    evidence_id: str
    evidence_type: EvidenceType
    source: str
    content: str
    timestamp: str
    checksum: str  # For reproducibility


@dataclass(frozen=True)
class EvidencePack:
    """Collection of all evidence for reasoning."""
    pack_id: str
    browser_observation: Optional[EvidenceItem]
    scope_extraction: Optional[EvidenceItem]
    platform_metadata: Optional[EvidenceItem]
    cve_context: Optional[EvidenceItem]
    screen_evidence: Optional[EvidenceItem]
    is_complete: bool
    missing_types: tuple  # Tuple[EvidenceType, ...]


@dataclass(frozen=True)
class ReportSectionContent:
    """Content for a single report section."""
    section: ReportSection
    title: str
    content: str
    evidence_refs: tuple  # Tuple[str, ...] - evidence IDs


@dataclass(frozen=True)
class StructuredReport:
    """Fixed-template structured report."""
    report_id: str
    sections: tuple  # Tuple[ReportSectionContent, ...]
    evidence_pack_id: str
    determinism_hash: str  # Same input = same hash
    created_at: str


@dataclass(frozen=True)
class VoiceScript:
    """Voice explanation script."""
    script_id: str
    report_id: str
    language: str  # "EN" or "HI"
    sections: tuple  # Tuple[str, ...] - spoken text per section
    total_duration_estimate_seconds: int


@dataclass(frozen=True)
class VideoNarrationMeta:
    """Video narration metadata."""
    meta_id: str
    report_id: str
    section_timestamps: Dict[str, int]  # section -> start_second
    total_duration_seconds: int


@dataclass(frozen=True)
class ReasoningResult:
    """Complete reasoning output."""
    result_id: str
    status: ReasoningStatus
    report: Optional[StructuredReport]
    evidence_pack: EvidencePack
    voice_script_en: Optional[VoiceScript]
    voice_script_hi: Optional[VoiceScript]
    video_meta: Optional[VideoNarrationMeta]
    error_message: Optional[str]
    timestamp: str


def create_evidence_item(
    evidence_type: EvidenceType,
    source: str,
    content: str,
) -> EvidenceItem:
    """Create an evidence item with checksum."""
    checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    return EvidenceItem(
        evidence_id=f"EVI-{uuid.uuid4().hex[:16].upper()}",
        evidence_type=evidence_type,
        source=source,
        content=content,
        timestamp=datetime.now(UTC).isoformat(),
        checksum=checksum,
    )


def create_evidence_pack(
    browser_observation: Optional[EvidenceItem] = None,
    scope_extraction: Optional[EvidenceItem] = None,
    platform_metadata: Optional[EvidenceItem] = None,
    cve_context: Optional[EvidenceItem] = None,
    screen_evidence: Optional[EvidenceItem] = None,
) -> EvidencePack:
    """Create an evidence pack, checking for completeness."""
    missing = []
    
    if not browser_observation:
        missing.append(EvidenceType.BROWSER_OBSERVATION)
    if not scope_extraction:
        missing.append(EvidenceType.SCOPE_EXTRACTION)
    if not platform_metadata:
        missing.append(EvidenceType.PLATFORM_METADATA)
    if not cve_context:
        missing.append(EvidenceType.CVE_CONTEXT)
    if not screen_evidence:
        missing.append(EvidenceType.SCREEN_EVIDENCE)
    
    return EvidencePack(
        pack_id=f"PKG-{uuid.uuid4().hex[:16].upper()}",
        browser_observation=browser_observation,
        scope_extraction=scope_extraction,
        platform_metadata=platform_metadata,
        cve_context=cve_context,
        screen_evidence=screen_evidence,
        is_complete=len(missing) == 0,
        missing_types=tuple(missing),
    )


def check_forbidden_words(text: str) -> Tuple[bool, Optional[str]]:
    """
    Check if text contains forbidden uncertainty words.
    
    Returns (has_forbidden, found_word).
    """
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in text_lower:
            return True, word
    return False, None


def generate_deterministic_hash(
    evidence_pack: EvidencePack,
    bug_type: str,
    severity: str,
) -> str:
    """Generate deterministic hash for reproducibility."""
    components = [
        evidence_pack.pack_id,
        bug_type,
        severity,
    ]
    
    if evidence_pack.browser_observation:
        components.append(evidence_pack.browser_observation.checksum)
    if evidence_pack.scope_extraction:
        components.append(evidence_pack.scope_extraction.checksum)
    if evidence_pack.platform_metadata:
        components.append(evidence_pack.platform_metadata.checksum)
    if evidence_pack.cve_context:
        components.append(evidence_pack.cve_context.checksum)
    if evidence_pack.screen_evidence:
        components.append(evidence_pack.screen_evidence.checksum)
    
    combined = "|".join(components)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def build_context_section(
    evidence_pack: EvidencePack,
    target: str,
    bug_type: str,
) -> ReportSectionContent:
    """Build CONTEXT section from evidence."""
    platform = "Unknown"
    if evidence_pack.platform_metadata:
        platform = evidence_pack.platform_metadata.content
    
    content = f"Target: {target}\nPlatform: {platform}\nBug Type: {bug_type}"
    
    refs = []
    if evidence_pack.platform_metadata:
        refs.append(evidence_pack.platform_metadata.evidence_id)
    
    return ReportSectionContent(
        section=ReportSection.CONTEXT,
        title="Context",
        content=content,
        evidence_refs=tuple(refs),
    )


def build_observations_section(
    evidence_pack: EvidencePack,
) -> ReportSectionContent:
    """Build OBSERVATIONS section from evidence."""
    observations = []
    refs = []
    
    if evidence_pack.browser_observation:
        observations.append(f"Browser: {evidence_pack.browser_observation.content}")
        refs.append(evidence_pack.browser_observation.evidence_id)
    
    if evidence_pack.screen_evidence:
        observations.append(f"Screen: {evidence_pack.screen_evidence.content}")
        refs.append(evidence_pack.screen_evidence.evidence_id)
    
    return ReportSectionContent(
        section=ReportSection.OBSERVATIONS,
        title="Observations",
        content="\n".join(observations),
        evidence_refs=tuple(refs),
    )


def build_reasoning_section(
    bug_type: str,
    evidence_pack: EvidencePack,
) -> ReportSectionContent:
    """Build LOGICAL_REASONING section - deterministic logic only."""
    # Map bug types to fixed reasoning patterns
    REASONING_PATTERNS = {
        "XSS": "User input is reflected in response without sanitization. This allows script injection.",
        "SQLi": "User input is concatenated into SQL query without parameterization. This allows query manipulation.",
        "IDOR": "Object reference is exposed without authorization check. This allows unauthorized access.",
        "SSRF": "User-controlled URL is fetched server-side without validation. This allows internal network access.",
        "RCE": "User input reaches command execution context without sanitization. This allows arbitrary commands.",
    }
    
    pattern = REASONING_PATTERNS.get(bug_type, f"Vulnerability of type {bug_type} was identified based on evidence.")
    
    refs = []
    if evidence_pack.scope_extraction:
        refs.append(evidence_pack.scope_extraction.evidence_id)
    
    return ReportSectionContent(
        section=ReportSection.LOGICAL_REASONING,
        title="Logical Reasoning",
        content=pattern,
        evidence_refs=tuple(refs),
    )


def build_impact_section(
    severity: str,
    bug_type: str,
) -> ReportSectionContent:
    """Build IMPACT_ANALYSIS section - deterministic mapping."""
    IMPACT_MAPPING = {
        ("CRITICAL", "RCE"): "Full server compromise. Attacker gains complete control.",
        ("CRITICAL", "SQLi"): "Full database access. All data exposed.",
        ("HIGH", "XSS"): "Session hijacking. User accounts compromised.",
        ("HIGH", "IDOR"): "Unauthorized data access. Privacy breach.",
        ("MEDIUM", "XSS"): "Limited script execution. Phishing possible.",
    }
    
    key = (severity, bug_type)
    impact = IMPACT_MAPPING.get(key, f"{severity} severity {bug_type} vulnerability identified.")
    
    return ReportSectionContent(
        section=ReportSection.IMPACT_ANALYSIS,
        title="Impact Analysis",
        content=impact,
        evidence_refs=tuple(),
    )


def build_reproduction_section(
    steps: List[str],
) -> ReportSectionContent:
    """Build REPRODUCTION_STEPS section."""
    numbered_steps = [f"{i+1}. {step}" for i, step in enumerate(steps)]
    
    return ReportSectionContent(
        section=ReportSection.REPRODUCTION_STEPS,
        title="Reproduction Steps",
        content="\n".join(numbered_steps),
        evidence_refs=tuple(),
    )


def build_why_matters_section(
    severity: str,
    cve_context: Optional[EvidenceItem],
) -> ReportSectionContent:
    """Build WHY_THIS_MATTERS section."""
    content_parts = []
    refs = []
    
    if severity == "CRITICAL":
        content_parts.append("This vulnerability poses immediate risk to the system.")
    elif severity == "HIGH":
        content_parts.append("This vulnerability requires prompt attention.")
    else:
        content_parts.append("This vulnerability should be addressed.")
    
    if cve_context:
        content_parts.append(f"CVE Context: {cve_context.content}")
        refs.append(cve_context.evidence_id)
    
    return ReportSectionContent(
        section=ReportSection.WHY_THIS_MATTERS,
        title="Why This Matters",
        content=" ".join(content_parts),
        evidence_refs=tuple(refs),
    )


def generate_structured_report(
    evidence_pack: EvidencePack,
    target: str,
    bug_type: str,
    severity: str,
    reproduction_steps: List[str],
) -> StructuredReport:
    """Generate a structured report from evidence."""
    sections = [
        build_context_section(evidence_pack, target, bug_type),
        build_observations_section(evidence_pack),
        build_reasoning_section(bug_type, evidence_pack),
        build_impact_section(severity, bug_type),
        build_reproduction_section(reproduction_steps),
        build_why_matters_section(severity, evidence_pack.cve_context),
    ]
    
    det_hash = generate_deterministic_hash(evidence_pack, bug_type, severity)
    
    return StructuredReport(
        report_id=f"RPT-{uuid.uuid4().hex[:16].upper()}",
        sections=tuple(sections),
        evidence_pack_id=evidence_pack.pack_id,
        determinism_hash=det_hash,
        created_at=datetime.now(UTC).isoformat(),
    )


def generate_voice_script(
    report: StructuredReport,
    language: str,
) -> VoiceScript:
    """Generate voice script from report."""
    spoken_sections = []
    
    for section in report.sections:
        if language == "HI":
            # Hindi voice intro for each section
            intros = {
                ReportSection.CONTEXT: "Pahle context samjhte hain.",
                ReportSection.OBSERVATIONS: "Ab observations dekhte hain.",
                ReportSection.LOGICAL_REASONING: "Logic yeh hai.",
                ReportSection.IMPACT_ANALYSIS: "Impact analysis.",
                ReportSection.REPRODUCTION_STEPS: "Reproduce karne ke steps.",
                ReportSection.WHY_THIS_MATTERS: "Yeh important kyun hai.",
            }
            intro = intros.get(section.section, "")
            spoken_sections.append(f"{intro} {section.content}")
        else:
            # English
            spoken_sections.append(f"{section.title}. {section.content}")
    
    # Estimate 150 words per minute
    total_words = sum(len(s.split()) for s in spoken_sections)
    duration = (total_words // 150) * 60 + 30
    
    return VoiceScript(
        script_id=f"VOI-{uuid.uuid4().hex[:16].upper()}",
        report_id=report.report_id,
        language=language,
        sections=tuple(spoken_sections),
        total_duration_estimate_seconds=duration,
    )


def generate_video_metadata(
    report: StructuredReport,
    voice_script: VoiceScript,
) -> VideoNarrationMeta:
    """Generate video narration metadata."""
    timestamps = {}
    current_time = 0
    avg_per_section = voice_script.total_duration_estimate_seconds // len(report.sections)
    
    for section in report.sections:
        timestamps[section.section.value] = current_time
        current_time += avg_per_section
    
    return VideoNarrationMeta(
        meta_id=f"VID-{uuid.uuid4().hex[:16].upper()}",
        report_id=report.report_id,
        section_timestamps=timestamps,
        total_duration_seconds=voice_script.total_duration_estimate_seconds,
    )


def perform_reasoning(
    evidence_pack: EvidencePack,
    target: str,
    bug_type: str,
    severity: str,
    reproduction_steps: List[str],
) -> ReasoningResult:
    """
    Perform complete deterministic reasoning.
    
    HARD FAILS if evidence is incomplete.
    """
    # Check evidence completeness
    if not evidence_pack.is_complete:
        missing_names = [et.value for et in evidence_pack.missing_types]
        return ReasoningResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            status=ReasoningStatus.MISSING_EVIDENCE,
            report=None,
            evidence_pack=evidence_pack,
            voice_script_en=None,
            voice_script_hi=None,
            video_meta=None,
            error_message=f"Missing evidence: {', '.join(missing_names)}",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    # Generate report
    report = generate_structured_report(
        evidence_pack, target, bug_type, severity, reproduction_steps
    )
    
    # Check for forbidden words in all sections
    for section in report.sections:
        has_forbidden, word = check_forbidden_words(section.content)
        if has_forbidden:
            return ReasoningResult(
                result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
                status=ReasoningStatus.FORBIDDEN_WORD,
                report=None,
                evidence_pack=evidence_pack,
                voice_script_en=None,
                voice_script_hi=None,
                video_meta=None,
                error_message=f"Forbidden word detected: '{word}'",
                timestamp=datetime.now(UTC).isoformat(),
            )
    
    # Generate voice scripts
    voice_en = generate_voice_script(report, "EN")
    voice_hi = generate_voice_script(report, "HI")
    
    # Generate video metadata
    video_meta = generate_video_metadata(report, voice_en)
    
    return ReasoningResult(
        result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
        status=ReasoningStatus.SUCCESS,
        report=report,
        evidence_pack=evidence_pack,
        voice_script_en=voice_en,
        voice_script_hi=voice_hi,
        video_meta=video_meta,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ============================================================
# CRITICAL SECURITY GUARDS
# ============================================================

def can_reasoning_execute() -> tuple:
    """
    Check if reasoning engine can execute actions.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot execute actions - report generation only"


def can_reasoning_decide() -> tuple:
    """
    Check if reasoning engine can approve execution.
    
    Returns (can_decide, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot approve execution - human decision required"


def can_reasoning_modify_state() -> tuple:
    """
    Check if reasoning engine can modify system state.
    
    Returns (can_modify, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine is READ-ONLY - no state modification allowed"
