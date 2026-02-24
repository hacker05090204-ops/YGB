"""
Training Mode Architecture — PRODUCTION_REAL / LAB_COMPLEX Split
================================================================

Enforces strict separation between production and lab training:

  PRODUCTION_REAL:
    - Ingestion-only real data
    - Full safety gates required
    - Artifacts tagged "PRODUCTION_REAL" immutably

  LAB_COMPLEX:
    - Advanced experiments allowed
    - Synthetic data permitted
    - Artifacts tagged "LAB_COMPLEX"
    - Promotion to production BLOCKED

Mode tags are immutable after freeze. Promotion guard rejects
any LAB-tagged artifact in production promotion paths.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# MODE ENUM
# =============================================================================

class TrainingModeType(str, Enum):
    """Strict training mode classification."""
    PRODUCTION_REAL = "PRODUCTION_REAL"
    LAB_COMPLEX = "LAB_COMPLEX"


# =============================================================================
# MODE TAG — Immutable after freeze
# =============================================================================

@dataclass
class ModeTag:
    """Immutable mode tag attached to training artifacts."""
    mode: str
    created_at: str = ""
    frozen_at: str = ""
    artifact_type: str = ""       # checkpoint, report, manifest, telemetry
    artifact_path: str = ""
    tag_hash: str = ""            # SHA-256 of (mode + created_at + artifact_type)
    frozen: bool = False

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        if not self.tag_hash:
            self.tag_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.mode.encode())
        h.update(self.created_at.encode())
        h.update(self.artifact_type.encode())
        return h.hexdigest()

    def freeze(self):
        """Freeze the tag — no further changes allowed."""
        if self.frozen:
            raise RuntimeError("ModeTag already frozen — cannot re-freeze")
        self.frozen_at = datetime.now(UTC).isoformat()
        self.frozen = True
        # Recompute hash with freeze timestamp
        h = hashlib.sha256()
        h.update(self.tag_hash.encode())
        h.update(self.frozen_at.encode())
        self.tag_hash = h.hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ModeTag":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# TAG UTILITY — Attach mode tags to artifacts
# =============================================================================

def tag_artifact(
    artifact_path: str,
    mode: TrainingModeType,
    artifact_type: str,
) -> ModeTag:
    """
    Create and attach an immutable mode tag to an artifact.

    Args:
        artifact_path: Path to the artifact file
        mode: PRODUCTION_REAL or LAB_COMPLEX
        artifact_type: checkpoint, report, manifest, telemetry

    Returns:
        Frozen ModeTag
    """
    tag = ModeTag(
        mode=mode.value,
        artifact_type=artifact_type,
        artifact_path=str(artifact_path),
    )
    tag.freeze()

    # Write tag alongside artifact
    tag_path = Path(artifact_path).with_suffix(".mode_tag.json")
    tag_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tag_path, "w") as f:
        json.dump(tag.to_dict(), f, indent=2)

    logger.info(f"[MODE_TAG] {mode.value} tag attached to {artifact_path}")
    return tag


def read_artifact_tag(artifact_path: str) -> Optional[ModeTag]:
    """Read the mode tag for an artifact, if it exists."""
    tag_path = Path(artifact_path).with_suffix(".mode_tag.json")
    if not tag_path.exists():
        return None
    with open(tag_path) as f:
        data = json.load(f)
    return ModeTag.from_dict(data)


# =============================================================================
# PROMOTION GUARD — Blocks LAB artifacts in production paths
# =============================================================================

class PromotionGuardError(RuntimeError):
    """Raised when a LAB artifact is detected in a production promotion path."""
    pass


def check_promotion(artifact_path: str) -> bool:
    """
    Check if an artifact is eligible for production promotion.

    Returns True if promotion is allowed.
    Raises PromotionGuardError if artifact is LAB-tagged.
    """
    tag = read_artifact_tag(artifact_path)

    if tag is None:
        # No tag = unknown provenance → BLOCK (fail closed)
        raise PromotionGuardError(
            f"PROMOTION BLOCKED: No mode tag found for {artifact_path}. "
            f"All production artifacts must have a PRODUCTION_REAL mode tag."
        )

    if tag.mode == TrainingModeType.LAB_COMPLEX.value:
        raise PromotionGuardError(
            f"PROMOTION BLOCKED: {artifact_path} is tagged LAB_COMPLEX. "
            f"LAB artifacts cannot be promoted to production. "
            f"Tag hash: {tag.tag_hash[:16]}..."
        )

    if tag.mode != TrainingModeType.PRODUCTION_REAL.value:
        raise PromotionGuardError(
            f"PROMOTION BLOCKED: {artifact_path} has unknown mode '{tag.mode}'. "
            f"Only PRODUCTION_REAL artifacts can be promoted."
        )

    if not tag.frozen:
        raise PromotionGuardError(
            f"PROMOTION BLOCKED: {artifact_path} mode tag is not frozen. "
            f"Only frozen tags are valid for promotion."
        )

    logger.info(f"[PROMOTION] Allowed: {artifact_path} (PRODUCTION_REAL, frozen)")
    return True


# =============================================================================
# MODE RESOLUTION — Determine current training mode
# =============================================================================

import os

def resolve_training_mode() -> TrainingModeType:
    """
    Resolve the current training mode from environment.

    Env var: YGB_TRAINING_MODE
      - "PRODUCTION_REAL" (default, fail-closed)
      - "LAB_COMPLEX" (requires explicit opt-in)
    """
    mode_str = os.getenv("YGB_TRAINING_MODE", "PRODUCTION_REAL").upper()
    try:
        return TrainingModeType(mode_str)
    except ValueError:
        logger.warning(
            f"[MODE] Unknown YGB_TRAINING_MODE='{mode_str}', "
            f"defaulting to PRODUCTION_REAL (fail-closed)"
        )
        return TrainingModeType.PRODUCTION_REAL


def is_production_mode() -> bool:
    """Check if current mode is PRODUCTION_REAL."""
    return resolve_training_mode() == TrainingModeType.PRODUCTION_REAL
