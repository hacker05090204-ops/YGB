# G35: AI Accelerator (Advisory Only)
"""
AI ACCELERATOR - ADVISORY ONLY.

Speeds up triage but NEVER makes decisions.

AI CAN:
✓ Rank findings by priority
✓ Reduce noise in results
✓ Catch human mistakes
✓ Suggest reasoning improvements

AI CANNOT:
✗ Approve bugs
✗ Verify bugs
✗ Execute actions
✗ Bypass governors

FINAL DECISION: G33 + HUMAN ONLY
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional, Dict
import hashlib
import uuid


class AdvisoryType(Enum):
    """CLOSED ENUM - Types of AI advisory output."""
    PRIORITY_RANKING = "PRIORITY_RANKING"
    NOISE_REDUCTION = "NOISE_REDUCTION"
    MISTAKE_DETECTION = "MISTAKE_DETECTION"
    REASONING_IMPROVEMENT = "REASONING_IMPROVEMENT"


class PriorityLevel(Enum):
    """CLOSED ENUM - Priority levels for findings."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOISE = "NOISE"


@dataclass(frozen=True)
class AIAdvisory:
    """Single AI advisory recommendation."""
    advisory_id: str
    advisory_type: AdvisoryType
    suggestion: str
    confidence: int  # 0-100
    reasoning: str
    is_binding: bool  # Always False


@dataclass(frozen=True)
class PriorityRanking:
    """AI-suggested priority ranking for findings."""
    ranking_id: str
    finding_id: str
    suggested_priority: PriorityLevel
    confidence: int  # 0-100
    factors: Tuple[str, ...]
    is_binding: bool  # Always False


@dataclass(frozen=True)
class NoiseReduction:
    """AI-suggested noise reduction."""
    reduction_id: str
    original_count: int
    reduced_count: int
    removed_ids: Tuple[str, ...]
    removal_reasons: Tuple[str, ...]
    is_binding: bool  # Always False


@dataclass(frozen=True)
class MistakeDetection:
    """AI-detected potential mistake."""
    detection_id: str
    mistake_type: str
    description: str
    suggested_fix: str
    confidence: int  # 0-100
    is_binding: bool  # Always False


@dataclass(frozen=True)
class AIAcceleratorResult:
    """Complete AI accelerator output."""
    result_id: str
    advisories: Tuple[AIAdvisory, ...]
    priority_rankings: Tuple[PriorityRanking, ...]
    noise_reductions: Tuple[NoiseReduction, ...]
    mistake_detections: Tuple[MistakeDetection, ...]
    total_suggestions: int
    binding_decisions: int  # Always 0
    determinism_hash: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate deterministic-format ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _hash_content(content: str) -> str:
    """Generate hash for determinism verification."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


# =============================================================================
# PRIORITY RANKING
# =============================================================================

PRIORITY_KEYWORDS: Dict[PriorityLevel, Tuple[str, ...]] = {
    PriorityLevel.CRITICAL: ("rce", "remote code", "account takeover", "full access"),
    PriorityLevel.HIGH: ("sqli", "xss stored", "auth bypass", "privilege escalation"),
    PriorityLevel.MEDIUM: ("idor", "csrf", "ssrf", "xss reflected"),
    PriorityLevel.LOW: ("information disclosure", "open redirect"),
    PriorityLevel.NOISE: ("missing header", "version disclosure", "theoretical"),
}


def suggest_priority(
    finding_text: str,
    finding_id: str,
) -> PriorityRanking:
    """
    Suggest a priority ranking for a finding.
    
    ADVISORY ONLY - not binding.
    """
    text_lower = finding_text.lower()
    
    for priority, keywords in PRIORITY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return PriorityRanking(
                    ranking_id=_generate_id("PRK"),
                    finding_id=finding_id,
                    suggested_priority=priority,
                    confidence=80,
                    factors=(f"keyword_match:{keyword}",),
                    is_binding=False,  # NEVER binding
                )
    
    return PriorityRanking(
        ranking_id=_generate_id("PRK"),
        finding_id=finding_id,
        suggested_priority=PriorityLevel.MEDIUM,
        confidence=50,
        factors=("default_priority",),
        is_binding=False,  # NEVER binding
    )


def rank_findings_batch(
    findings: Tuple[Tuple[str, str], ...],  # (finding_id, finding_text)
) -> Tuple[PriorityRanking, ...]:
    """
    Rank a batch of findings by priority.
    
    ADVISORY ONLY - not binding.
    """
    return tuple(
        suggest_priority(text, fid)
        for fid, text in findings
    )


# =============================================================================
# NOISE REDUCTION
# =============================================================================

NOISE_PATTERNS = frozenset([
    "missing x-",
    "server header",
    "version disclosed",
    "directory listing",
    "robots.txt",
    "sitemap.xml",
])


def suggest_noise_reduction(
    findings: Tuple[Tuple[str, str], ...],  # (finding_id, finding_text)
) -> NoiseReduction:
    """
    Suggest findings to remove as noise.
    
    ADVISORY ONLY - not binding.
    """
    removed_ids = []
    removal_reasons = []
    
    for fid, text in findings:
        text_lower = text.lower()
        for pattern in NOISE_PATTERNS:
            if pattern in text_lower:
                removed_ids.append(fid)
                removal_reasons.append(f"noise_pattern:{pattern}")
                break
    
    return NoiseReduction(
        reduction_id=_generate_id("NRD"),
        original_count=len(findings),
        reduced_count=len(findings) - len(removed_ids),
        removed_ids=tuple(removed_ids),
        removal_reasons=tuple(removal_reasons),
        is_binding=False,  # NEVER binding
    )


# =============================================================================
# MISTAKE DETECTION
# =============================================================================

COMMON_MISTAKES = {
    "no proof of concept": "Add step-by-step reproduction",
    "theoretical only": "Demonstrate actual exploitation",
    "missing impact": "Explain business impact clearly",
    "out of scope": "Verify scope before submission",
    "duplicate indicator": "Check for existing reports",
}


def detect_mistakes(
    report_text: str,
) -> Tuple[MistakeDetection, ...]:
    """
    Detect potential mistakes in a report.
    
    ADVISORY ONLY - not binding.
    """
    detections = []
    text_lower = report_text.lower()
    
    for mistake, fix in COMMON_MISTAKES.items():
        if mistake in text_lower or (
            mistake == "no proof of concept" and "poc" not in text_lower and "proof" not in text_lower
        ):
            detections.append(MistakeDetection(
                detection_id=_generate_id("MSD"),
                mistake_type=mistake.replace(" ", "_").upper(),
                description=f"Potential issues: {mistake}",
                suggested_fix=fix,
                confidence=70,
                is_binding=False,  # NEVER binding
            ))
    
    return tuple(detections)


# =============================================================================
# FULL ACCELERATOR
# =============================================================================

def accelerate_triage(
    findings: Tuple[Tuple[str, str], ...],
    report_text: str = "",
) -> AIAcceleratorResult:
    """
    Run full AI acceleration on findings.
    
    ADVISORY ONLY - ALL is_binding = False.
    """
    # Generate all advisories
    priority_rankings = rank_findings_batch(findings)
    noise_reduction = suggest_noise_reduction(findings)
    mistakes = detect_mistakes(report_text) if report_text else tuple()
    
    # Create summary advisories
    advisories = []
    
    if noise_reduction.removed_ids:
        advisories.append(AIAdvisory(
            advisory_id=_generate_id("ADV"),
            advisory_type=AdvisoryType.NOISE_REDUCTION,
            suggestion=f"Consider removing {len(noise_reduction.removed_ids)} noise findings",
            confidence=75,
            reasoning="Pattern-based noise detection",
            is_binding=False,
        ))
    
    critical_count = sum(1 for r in priority_rankings if r.suggested_priority == PriorityLevel.CRITICAL)
    if critical_count > 0:
        advisories.append(AIAdvisory(
            advisory_id=_generate_id("ADV"),
            advisory_type=AdvisoryType.PRIORITY_RANKING,
            suggestion=f"Focus on {critical_count} critical findings first",
            confidence=85,
            reasoning="Critical findings have highest impact",
            is_binding=False,
        ))
    
    for mistake in mistakes:
        advisories.append(AIAdvisory(
            advisory_id=_generate_id("ADV"),
            advisory_type=AdvisoryType.MISTAKE_DETECTION,
            suggestion=mistake.suggested_fix,
            confidence=mistake.confidence,
            reasoning=mistake.description,
            is_binding=False,
        ))
    
    total_suggestions = len(advisories) + len(priority_rankings)
    
    return AIAcceleratorResult(
        result_id=_generate_id("ACC"),
        advisories=tuple(advisories),
        priority_rankings=priority_rankings,
        noise_reductions=(noise_reduction,) if noise_reduction.removed_ids else tuple(),
        mistake_detections=mistakes,
        total_suggestions=total_suggestions,
        binding_decisions=0,  # ALWAYS 0
        determinism_hash=_hash_content(str(findings) + report_text),
    )


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_ai_approve() -> Tuple[bool, str]:
    """
    Check if AI can approve bugs.
    
    Returns (can_approve, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot approve bugs - human approval required"


def can_ai_verify() -> Tuple[bool, str]:
    """
    Check if AI can verify bugs.
    
    Returns (can_verify, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot verify bugs - G33 + human verification required"


def can_ai_execute() -> Tuple[bool, str]:
    """
    Check if AI can execute actions.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot execute actions - advisory only"


def can_ai_bypass_governance() -> Tuple[bool, str]:
    """
    Check if AI can bypass governance.
    
    Returns (can_bypass, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot bypass governance - governance is absolute"


def can_ai_make_binding_decision() -> Tuple[bool, str]:
    """
    Check if AI can make binding decisions.
    
    Returns (can_decide, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot make binding decisions - advisory only"


def can_ai_override_human() -> Tuple[bool, str]:
    """
    Check if AI can override human decisions.
    
    Returns (can_override, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot override human decisions - human authority is absolute"


# =============================================================================
# GPU TRAINING EXTENSION
# =============================================================================

class TrainingMode(Enum):
    """CLOSED ENUM - When AI training is allowed."""
    IDLE = "IDLE"        # System idle, no human interaction
    AUTO = "AUTO"        # System in auto mode


class TrainingDataSource(Enum):
    """CLOSED ENUM - Sources of training data."""
    G33_VERIFIED_REAL = "G33_VERIFIED_REAL"      # Human-verified real bugs
    G33_REJECTED = "G33_REJECTED"                # Rejected findings
    G36_AUTO_VERIFIED = "G36_AUTO_VERIFIED"      # Auto-verified results
    G36_HUMAN_CORRECTED = "G36_HUMAN_CORRECTED"  # Auto results later corrected
    ACCEPTED_BOUNTY = "ACCEPTED_BOUNTY"          # Accepted bounty reports
    REJECTED_BOUNTY = "REJECTED_BOUNTY"          # Rejected/duplicate reports
    POC_VIDEO = "POC_VIDEO"                      # PoC videos with explanations


@dataclass(frozen=True)
class GPUTrainingConfig:
    """Configuration for GPU-accelerated training."""
    config_id: str
    model_name: str
    batch_size: int
    learning_rate: float
    epochs: int
    gpu_memory_limit_mb: int
    internet_allowed: bool  # For fetching public reports/CVEs


@dataclass(frozen=True)
class TrainingDataItem:
    """Single training data item."""
    item_id: str
    source: TrainingDataSource
    content_hash: str
    label: str  # "REAL", "NOT_REAL", "DUPLICATE"
    confidence_target: int
    metadata: Dict[str, str]


@dataclass(frozen=True)
class TrainingBatch:
    """Batch of training data."""
    batch_id: str
    items: Tuple[TrainingDataItem, ...]
    total_items: int
    sources_used: Tuple[TrainingDataSource, ...]
    batch_hash: str


@dataclass(frozen=True)
class TrainingResult:
    """Result of a training run."""
    result_id: str
    mode: TrainingMode
    epochs_completed: int
    loss_final: float
    accuracy_estimate: float
    gpu_time_seconds: float
    is_mock: bool  # True = mock, False = real C++ GPU


def _create_training_config(
    model_name: str = "ygb-bug-classifier-v1",
    batch_size: int = 32,
) -> GPUTrainingConfig:
    """Create default training configuration."""
    return GPUTrainingConfig(
        config_id=_generate_id("CFG"),
        model_name=model_name,
        batch_size=batch_size,
        learning_rate=0.001,
        epochs=10,
        gpu_memory_limit_mb=4096,
        internet_allowed=True,  # For public reports/CVEs ONLY
    )


def can_train_now(current_mode: str) -> Tuple[bool, str]:
    """
    Check if training is allowed in current mode.
    
    Training ONLY allowed in IDLE or AUTO mode.
    """
    allowed_modes = {"IDLE", "AUTO"}
    
    if current_mode.upper() in allowed_modes:
        return True, f"Training allowed in {current_mode} mode"
    
    return False, f"Training not allowed in {current_mode} mode - requires IDLE or AUTO"


def prepare_training_batch(
    verified_bugs: Tuple[Tuple[str, str, str], ...],  # (id, content_hash, label)
    rejected_findings: Tuple[Tuple[str, str], ...],   # (id, content_hash)
    max_items: int = 1000,
) -> TrainingBatch:
    """
    Prepare a batch of training data.
    
    Uses G33 verified bugs and rejected findings.
    """
    items = []
    sources_used = set()
    
    # Add verified bugs
    for item_id, content_hash, label in verified_bugs[:max_items // 2]:
        items.append(TrainingDataItem(
            item_id=item_id,
            source=TrainingDataSource.G33_VERIFIED_REAL,
            content_hash=content_hash,
            label=label,
            confidence_target=95,
            metadata={},
        ))
        sources_used.add(TrainingDataSource.G33_VERIFIED_REAL)
    
    # Add rejected findings
    for item_id, content_hash in rejected_findings[:max_items // 2]:
        items.append(TrainingDataItem(
            item_id=item_id,
            source=TrainingDataSource.G33_REJECTED,
            content_hash=content_hash,
            label="NOT_REAL",
            confidence_target=90,
            metadata={},
        ))
        sources_used.add(TrainingDataSource.G33_REJECTED)
    
    batch_hash = _hash_content(str([i.content_hash for i in items]))
    
    return TrainingBatch(
        batch_id=_generate_id("TRB"),
        items=tuple(items),
        total_items=len(items),
        sources_used=tuple(sources_used),
        batch_hash=batch_hash,
    )


def simulate_gpu_training(
    batch: TrainingBatch,
    config: GPUTrainingConfig,
    mode: TrainingMode,
) -> TrainingResult:
    """
    GPU training stub — BLOCKED in production.

    Real training runs through g37_pytorch_backend.py or the C++ GPU kernel.
    This function exists only for interface compatibility and MUST NOT
    return fabricated results in strict mode.
    """
    import os
    if os.environ.get("YGB_ALLOW_MOCK_TRAINING") != "1":
        raise RuntimeError(
            "BLOCKED: simulate_gpu_training() is a mock stub. "
            "Real training must use g37_pytorch_backend or C++ GPU kernel. "
            "Set YGB_ALLOW_MOCK_TRAINING=1 to override for testing only."
        )

    # TEST-ONLY fallback — never reached in production
    return TrainingResult(
        result_id=_generate_id("TRR"),
        mode=mode,
        epochs_completed=0,
        loss_final=float('inf'),
        accuracy_estimate=0.0,
        gpu_time_seconds=0.0,
        is_mock=True,
    )


# =============================================================================
# ADDITIONAL TRAINING GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_ai_approve_bug() -> Tuple[bool, str]:
    """
    Check if AI can approve bugs during training.
    
    Returns (can_approve, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot approve bugs - human approval required"


def can_ai_override_governance() -> Tuple[bool, str]:
    """
    Check if AI can override governance during training.
    
    Returns (can_override, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot override governance - governance is absolute"


def can_ai_submit() -> Tuple[bool, str]:
    """
    Check if AI can submit bugs.
    
    Returns (can_submit, reason).
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot submit bugs - human submission required"


def can_training_access_credentials() -> Tuple[bool, str]:
    """
    Check if training can access credentials.
    
    Returns (can_access, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Training cannot access credentials - read-only data access"

