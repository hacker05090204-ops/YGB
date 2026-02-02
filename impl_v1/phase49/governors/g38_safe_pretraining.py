# G38: Safe Auto-Mode Pre-Training Governance
"""
SAFE AUTO-MODE PRE-TRAINING GOVERNANCE.

PURPOSE:
Enable AUTO MODE to be pre-trained FIRST — before any manual hunts —
WITHOUT false positives, hallucinations, duplicates, or trust violations.

CORE PRINCIPLE (NON-NEGOTIABLE):
❌ AI must NOT learn "this is a bug" from the internet
✅ AI may learn how systems look and behave

TRAINING MODES (STRICT SPLIT):

🔒 MODE-A: REPRESENTATION-ONLY (ALLOWED FROM INTERNET)
    AI MAY learn:
    - HTTP request/response shapes
    - DOM structure & mutation patterns
    - Auth flow topology
    - OAuth / SSO structure
    - API & GraphQL schemas
    - Error response morphology
    - Parameter behavior
    - Duplicate fingerprints
    - Noise patterns
    
    AI MUST NOT learn:
    - Bug labels
    - Severity
    - Acceptance / rejection
    - Platform outcomes

🔐 MODE-B: PROOF-LEARNING (LOCKED)
    This mode is LOCKED until:
    - G33 / G36 produce verified REAL bugs
    - Duplicate-free
    - Proof-complete
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, List, Optional, Set, FrozenSet
import uuid
from datetime import datetime, timezone


# =============================================================================
# TRAINING MODE DEFINITIONS
# =============================================================================

class TrainingMode(Enum):
    """Training mode enumeration."""
    REPRESENTATION_ONLY = "REPRESENTATION_ONLY"  # MODE-A: Internet allowed
    PROOF_LEARNING = "PROOF_LEARNING"            # MODE-B: LOCKED


class TrainingModeStatus(Enum):
    """Training mode activation status."""
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"


@dataclass(frozen=True)
class TrainingModeConfig:
    """Configuration for a training mode."""
    mode: TrainingMode
    status: TrainingModeStatus
    internet_allowed: bool
    bug_label_learning: bool
    description: str


# =============================================================================
# MODE CONFIGURATIONS
# =============================================================================

# MODE-A: REPRESENTATION-ONLY
MODE_A_CONFIG = TrainingModeConfig(
    mode=TrainingMode.REPRESENTATION_ONLY,
    status=TrainingModeStatus.ACTIVE,
    internet_allowed=True,
    bug_label_learning=False,
    description="Representation-only training from internet - structure learning only"
)

# MODE-B: PROOF-LEARNING (LOCKED)
MODE_B_CONFIG = TrainingModeConfig(
    mode=TrainingMode.PROOF_LEARNING,
    status=TrainingModeStatus.LOCKED,
    internet_allowed=False,
    bug_label_learning=True,  # Allowed only with verified proofs
    description="Proof-learning from verified real bugs - LOCKED until G33/G36 produce proofs"
)


# =============================================================================
# ALLOWED LEARNING TYPES (MODE-A)
# =============================================================================

class AllowedLearningType(Enum):
    """What AI MAY learn in MODE-A."""
    HTTP_REQUEST_RESPONSE_SHAPES = "HTTP_REQUEST_RESPONSE_SHAPES"
    DOM_STRUCTURE_PATTERNS = "DOM_STRUCTURE_PATTERNS"
    AUTH_FLOW_TOPOLOGY = "AUTH_FLOW_TOPOLOGY"
    OAUTH_SSO_STRUCTURE = "OAUTH_SSO_STRUCTURE"
    API_GRAPHQL_SCHEMAS = "API_GRAPHQL_SCHEMAS"
    ERROR_RESPONSE_MORPHOLOGY = "ERROR_RESPONSE_MORPHOLOGY"
    PARAMETER_BEHAVIOR = "PARAMETER_BEHAVIOR"
    DUPLICATE_FINGERPRINTS = "DUPLICATE_FINGERPRINTS"
    NOISE_PATTERNS = "NOISE_PATTERNS"


class ForbiddenLearningType(Enum):
    """What AI MUST NOT learn in MODE-A."""
    BUG_LABELS = "BUG_LABELS"
    SEVERITY_RATINGS = "SEVERITY_RATINGS"
    ACCEPTANCE_REJECTION = "ACCEPTANCE_REJECTION"
    PLATFORM_OUTCOMES = "PLATFORM_OUTCOMES"
    CRITICAL_HIGH_VALID_SEMANTICS = "CRITICAL_HIGH_VALID_SEMANTICS"


# =============================================================================
# SAFE DATA SOURCES (REPRESENTATION ONLY)
# =============================================================================

class SafeDataSource(Enum):
    """Allowed data sources for MODE-A training."""
    OWASP_JUICE_SHOP = "OWASP_JUICE_SHOP"
    WEBGOAT = "WEBGOAT"
    DVWA = "DVWA"
    PORTSWIGGER_LABS = "PORTSWIGGER_LABS"
    OPENAPI_SPECS = "OPENAPI_SPECS"
    CVE_METADATA_STRUCTURE = "CVE_METADATA_STRUCTURE"
    PUBLIC_VULNERABLE_APPS_STRUCTURE = "PUBLIC_VULNERABLE_APPS_STRUCTURE"
    HTTP_TRAFFIC_REPLAYS = "HTTP_TRAFFIC_REPLAYS"
    DOM_SNAPSHOTS = "DOM_SNAPSHOTS"
    API_SCHEMAS = "API_SCHEMAS"


class ForbiddenDataSource(Enum):
    """Forbidden data sources for all training."""
    HACKERONE_REPORTS_AS_TRUTH = "HACKERONE_REPORTS_AS_TRUTH"
    BUGCROWD_REPORTS_AS_TRUTH = "BUGCROWD_REPORTS_AS_TRUTH"
    FORUM_CLAIMS = "FORUM_CLAIMS"
    SCANNER_VERDICTS = "SCANNER_VERDICTS"
    SEVERITY_LABELS = "SEVERITY_LABELS"
    ACCEPTED_REJECTED_SEMANTICS = "ACCEPTED_REJECTED_SEMANTICS"


# =============================================================================
# PRETRAINING SAMPLE DEFINITION
# =============================================================================

@dataclass(frozen=True)
class PretrainingSample:
    """A single pre-training sample with provenance."""
    sample_id: str
    source: SafeDataSource
    learning_type: AllowedLearningType
    mode: TrainingMode
    contains_bug_labels: bool
    contains_severity: bool
    contains_acceptance_status: bool
    raw_data_hash: str
    created_at: str


@dataclass(frozen=True)
class PretrainingValidation:
    """Validation result for a pretraining sample."""
    validation_id: str
    sample_id: str
    is_valid: bool
    violations: Tuple[str, ...]
    mode: TrainingMode
    validated_at: str


@dataclass(frozen=True)
class PretrainingBatch:
    """A batch of pretraining samples."""
    batch_id: str
    samples: Tuple[PretrainingSample, ...]
    mode: TrainingMode
    total_samples: int
    valid_samples: int
    created_at: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _now_iso() -> str:
    """Current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# MODE STATUS CHECKS
# =============================================================================

def get_mode_a_status() -> Tuple[TrainingModeStatus, str]:
    """Get MODE-A (REPRESENTATION_ONLY) status."""
    return TrainingModeStatus.ACTIVE, "MODE-A active - representation learning allowed"


def get_mode_b_status() -> Tuple[TrainingModeStatus, str]:
    """Get MODE-B (PROOF_LEARNING) status."""
    return TrainingModeStatus.LOCKED, "MODE-B locked - awaiting G33/G36 verified proofs"


def is_mode_b_unlocked() -> bool:
    """
    Check if MODE-B is unlocked.
    
    MODE-B unlocks ONLY when:
    - G33 / G36 produce verified REAL bugs
    - Duplicate-free
    - Proof-complete
    
    Currently ALWAYS returns False.
    """
    return False


# =============================================================================
# SAMPLE VALIDATION
# =============================================================================

def validate_pretraining_sample(
    sample: PretrainingSample,
) -> PretrainingValidation:
    """
    Validate a pretraining sample.
    
    MODE-A samples MUST NOT contain:
    - Bug labels
    - Severity ratings
    - Acceptance status
    """
    validation_id = _generate_id("VAL")
    violations: List[str] = []
    
    # Check for forbidden content in MODE-A
    if sample.mode == TrainingMode.REPRESENTATION_ONLY:
        if sample.contains_bug_labels:
            violations.append("Sample contains bug labels - forbidden in MODE-A")
        
        if sample.contains_severity:
            violations.append("Sample contains severity ratings - forbidden in MODE-A")
        
        if sample.contains_acceptance_status:
            violations.append("Sample contains acceptance status - forbidden in MODE-A")
    
    # MODE-B is locked
    if sample.mode == TrainingMode.PROOF_LEARNING:
        if not is_mode_b_unlocked():
            violations.append("MODE-B is LOCKED - cannot use PROOF_LEARNING mode")
    
    return PretrainingValidation(
        validation_id=validation_id,
        sample_id=sample.sample_id,
        is_valid=len(violations) == 0,
        violations=tuple(violations),
        mode=sample.mode,
        validated_at=_now_iso(),
    )


def is_source_safe(source: SafeDataSource) -> Tuple[bool, str]:
    """Check if a data source is safe for MODE-A."""
    return True, f"Source {source.value} is safe for representation learning"


def is_source_forbidden(source_name: str) -> Tuple[bool, str]:
    """Check if a data source is forbidden."""
    forbidden_names = {s.value.lower() for s in ForbiddenDataSource}
    if source_name.lower() in forbidden_names:
        return True, f"Source {source_name} is FORBIDDEN - cannot be used for training"
    
    # Check for keywords that indicate forbidden sources
    forbidden_keywords = ["hackerone", "bugcrowd", "accepted", "rejected", 
                          "critical", "high", "medium", "low", "severity"]
    for keyword in forbidden_keywords:
        if keyword in source_name.lower():
            return True, f"Source contains forbidden keyword: {keyword}"
    
    return False, f"Source {source_name} is not explicitly forbidden"


def check_learning_type_allowed(
    learning_type: AllowedLearningType,
    mode: TrainingMode,
) -> Tuple[bool, str]:
    """Check if a learning type is allowed in the given mode."""
    if mode == TrainingMode.REPRESENTATION_ONLY:
        return True, f"{learning_type.value} allowed in MODE-A"
    elif mode == TrainingMode.PROOF_LEARNING:
        if is_mode_b_unlocked():
            return True, f"{learning_type.value} allowed in unlocked MODE-B"
        else:
            return False, "MODE-B is LOCKED - all learning types blocked"
    return False, "Unknown mode"


# =============================================================================
# PRETRAINING GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_ai_learn_bug_labels_from_internet() -> Tuple[bool, str]:
    """
    Check if AI can learn bug labels from internet.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot learn bug labels from internet - representation only"


def can_ai_learn_severity_from_internet() -> Tuple[bool, str]:
    """
    Check if AI can learn severity from internet.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot learn severity from internet - representation only"


def can_ai_learn_acceptance_status() -> Tuple[bool, str]:
    """
    Check if AI can learn acceptance/rejection status.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot learn acceptance/rejection status - representation only"


def can_ai_use_platform_outcomes() -> Tuple[bool, str]:
    """
    Check if AI can use platform outcomes for training.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot use platform outcomes - representation only"


def can_mode_b_activate_without_proofs() -> Tuple[bool, str]:
    """
    Check if MODE-B can activate without verified proofs.
    
    ALWAYS returns (False, ...).
    """
    return False, "MODE-B cannot activate without G33/G36 verified proofs"


def can_ai_train_on_scanner_verdicts() -> Tuple[bool, str]:
    """
    Check if AI can train on scanner verdicts.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot train on scanner verdicts - representation only"


# =============================================================================
# ALL PRETRAINING GUARDS
# =============================================================================

PRETRAINING_GUARDS = (
    can_ai_learn_bug_labels_from_internet,
    can_ai_learn_severity_from_internet,
    can_ai_learn_acceptance_status,
    can_ai_use_platform_outcomes,
    can_mode_b_activate_without_proofs,
    can_ai_train_on_scanner_verdicts,
)


def verify_pretraining_guards() -> Tuple[bool, str]:
    """
    Verify all pretraining guards return False.
    
    Returns (True, ...) if all guards pass.
    """
    for guard in PRETRAINING_GUARDS:
        result, msg = guard()
        if result:
            return False, f"Guard {guard.__name__} returned True: {msg}"
    return True, "All pretraining guards verified - representation-only training enforced"


# =============================================================================
# BATCH CREATION
# =============================================================================

def create_pretraining_batch(
    samples: Tuple[PretrainingSample, ...],
) -> Tuple[PretrainingBatch, List[PretrainingValidation]]:
    """
    Create a pretraining batch with validation.
    
    All samples MUST pass validation.
    """
    validations: List[PretrainingValidation] = []
    valid_samples: List[PretrainingSample] = []
    
    for sample in samples:
        validation = validate_pretraining_sample(sample)
        validations.append(validation)
        if validation.is_valid:
            valid_samples.append(sample)
    
    batch = PretrainingBatch(
        batch_id=_generate_id("BTH"),
        samples=tuple(valid_samples),
        mode=TrainingMode.REPRESENTATION_ONLY,  # Only MODE-A allowed
        total_samples=len(samples),
        valid_samples=len(valid_samples),
        created_at=_now_iso(),
    )
    
    return batch, validations


# =============================================================================
# SUMMARY FUNCTIONS
# =============================================================================

def get_training_mode_summary() -> str:
    """Get human-readable training mode summary."""
    mode_a_status, mode_a_msg = get_mode_a_status()
    mode_b_status, mode_b_msg = get_mode_b_status()
    
    lines = [
        "=== G38 SAFE PRE-TRAINING STATUS ===",
        "",
        "MODE-A (REPRESENTATION_ONLY):",
        f"  Status: {mode_a_status.value}",
        f"  Internet: ALLOWED",
        f"  Bug Labels: FORBIDDEN",
        "",
        "MODE-B (PROOF_LEARNING):",
        f"  Status: {mode_b_status.value}",
        f"  Internet: BLOCKED",
        f"  Unlock Condition: G33/G36 verified proofs",
        "",
        "==================================="
    ]
    
    return "\n".join(lines)


def get_safe_sources_list() -> Tuple[str, ...]:
    """Get list of safe data sources."""
    return tuple(s.value for s in SafeDataSource)


def get_forbidden_sources_list() -> Tuple[str, ...]:
    """Get list of forbidden data sources."""
    return tuple(s.value for s in ForbiddenDataSource)
