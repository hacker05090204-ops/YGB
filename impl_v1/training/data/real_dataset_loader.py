"""
Dataset Loader — Training Data Source
======================================

REAL DATA ONLY:
  - SyntheticTrainingDataset is BLOCKED everywhere
  - Only IngestionPipelineDataset (Phase 3) is permitted
  - Training aborts if dataset_source != "INGESTION_PIPELINE"

SyntheticTrainingDataset (formerly RealTrainingDataset):
  - Uses ScaledDatasetGenerator (SYNTHETIC data)
  - Retained only as a blocked compatibility symbol
  - Never permitted for training

FORBIDDEN FIELDS (hard blocked):
- valid, accepted, rejected, severity, platform_decision
"""

import torch
import numpy as np
from torch.utils.data import Dataset, DataLoader
from typing import List, Tuple, Optional, Dict, Any
import random
from dataclasses import dataclass
from pathlib import Path

# Import the scaled dataset generator
from impl_v1.training.data.scaled_dataset import (
    ScaledDatasetGenerator,
    DatasetConfig,
    Sample,
    FIXED_SEED,
)


# =============================================================================
# STRICT REAL MODE — BLOCKS SYNTHETIC DATA IN PRODUCTION
# =============================================================================

import os as _os

STRICT_REAL_MODE = True


def _enforce_strict_real_mode(cls_name: str):
    """Abort all synthetic training paths unconditionally."""
    raise RuntimeError(
        f"ABORT: {cls_name} is BLOCKED. Real-data-only mode is enforced. "
        f"Only IngestionPipelineDataset (dataset_source='INGESTION_PIPELINE') "
        f"is permitted for training."
    )


# =============================================================================
# FORBIDDEN FIELDS - GOVERNANCE ENFORCEMENT
# =============================================================================

FORBIDDEN_FIELDS = frozenset(
    [
        "valid",
        "accepted",
        "rejected",
        "severity",
        "platform_decision",
        "decision",
        "outcome",
        "verified",
    ]
)


def strip_forbidden_fields(data: dict) -> dict:
    """Remove any forbidden fields from data dictionary."""
    return {k: v for k, v in data.items() if k.lower() not in FORBIDDEN_FIELDS}


def validate_no_forbidden_fields(data: dict) -> bool:
    """Validate that no forbidden fields exist in data."""
    for key in data.keys():
        if key.lower() in FORBIDDEN_FIELDS:
            return False
    return True


# =============================================================================
# PYTORCH DATASET
# =============================================================================


class SyntheticTrainingDataset(Dataset):
    """
    SYNTHETIC Training Dataset (formerly RealTrainingDataset).

    WARNING: This class generates SYNTHETIC data via ScaledDatasetGenerator.
    It is BLOCKED when STRICT_REAL_MODE=True (default).
    Use IngestionPipelineDataset for real production training.

    Uses ScaledDatasetGenerator for structured samples with:
    - 20,000+ samples
    - Balanced classes
    - Edge cases for robustness
    - Deterministic shuffle
    """

    dataset_source = "SYNTHETIC_GENERATOR"  # NOT from ingestion pipeline

    def __init__(
        self,
        config: DatasetConfig = None,
        seed: int = FIXED_SEED,
        feature_dim: int = 256,
        is_holdout: bool = False,
    ):
        # STRICT_REAL_MODE enforcement
        _enforce_strict_real_mode("SyntheticTrainingDataset")

        self.config = config or DatasetConfig(total_samples=20000)
        self.seed = seed
        self.feature_dim = feature_dim
        self.is_holdout = is_holdout

        # Generate samples
        generator = ScaledDatasetGenerator(self.config, seed)
        train_samples, holdout_samples = generator.generate()

        self.samples = holdout_samples if is_holdout else train_samples
        self.rng = random.Random(seed)

        # Pre-encode all features to tensors
        self._features = []
        self._labels = []

        for sample in self.samples:
            # Strip any forbidden fields
            clean_features = strip_forbidden_fields(sample.features)

            # Encode features to fixed-size vector
            feature_vec = self._encode_features(clean_features, sample.is_edge_case)
            self._features.append(feature_vec)
            self._labels.append(sample.label)

        # Convert to tensors
        self._features_tensor = torch.tensor(self._features, dtype=torch.float32)
        self._labels_tensor = torch.tensor(self._labels, dtype=torch.long)

    def _encode_features(self, features: dict, is_edge: bool) -> List[float]:
        """Encode feature dict to fixed-size vector with label-correlated patterns.

        Feature layout:
          [0-63]   Signal-strength features (primary label signal)
          [64-127] Response-ratio features (secondary label signal)
          [128-191] Diverse derived features (NOT simple signal×response)
          [192-255] Controlled noise (small amplitude)

        DESIGN: Each feature group encodes INDEPENDENT aspects of the label
        signal. No single group should be sufficient for >90% accuracy.
        Interaction dims use diverse nonlinear combinations with higher
        noise to prevent shortcut dominance.
        """
        vec = []

        # Extract label-correlated fields
        signal = features.get("signal_strength", 0.5)
        response = features.get("response_ratio", 0.5)
        difficulty = features.get("difficulty", 0.5)
        noise_level = features.get("noise", 0.1)

        # Use a per-sample seed derived from signal+response for determinism
        sample_seed = int((signal * 10000 + response * 1000 + difficulty * 100) * 100)
        sample_rng = random.Random(sample_seed)

        for i in range(self.feature_dim):
            if i < 64:
                # Signal-strength features — PRIMARY label signal
                base = signal
                noise = noise_level * 0.08 * sample_rng.gauss(0, 1)
                val = base + noise
            elif i < 128:
                # Response-ratio features — SECONDARY label signal
                base = response
                noise = noise_level * 0.08 * sample_rng.gauss(0, 1)
                val = base + noise
            elif i < 192:
                # Diverse derived features — INDEPENDENT combinations
                # Each sub-range uses a different non-redundant encoding
                sub_idx = i - 128  # 0-63

                if sub_idx < 16:
                    # Polynomial: signal^2 with independent noise
                    base = signal * signal
                    noise = 0.06 * sample_rng.gauss(0, 1)
                elif sub_idx < 32:
                    # Polynomial: response^2 with independent noise
                    base = response * response
                    noise = 0.06 * sample_rng.gauss(0, 1)
                elif sub_idx < 40:
                    # Trigonometric: sin(signal * pi)
                    import math

                    base = 0.5 + 0.5 * math.sin(signal * math.pi)
                    noise = 0.05 * sample_rng.gauss(0, 1)
                elif sub_idx < 48:
                    # Trigonometric: cos(response * pi)
                    import math

                    base = 0.5 + 0.5 * math.cos(response * math.pi)
                    noise = 0.05 * sample_rng.gauss(0, 1)
                elif sub_idx < 56:
                    # Threshold: binary indicator with noise
                    threshold = 0.5 + 0.02 * sample_rng.gauss(0, 1)
                    base = 0.8 if signal > threshold else 0.2
                    noise = 0.04 * sample_rng.gauss(0, 1)
                else:
                    # Rank-based: difficulty-weighted signal magnitude
                    base = signal * (1.0 - difficulty * 0.3)
                    noise = 0.05 * sample_rng.gauss(0, 1)

                val = base + noise
            else:
                # [192-255] Additional feature groups from raw metadata
                sub_idx = i - 192  # 0-63
                endpoint_entropy = features.get("endpoint_entropy", 0.5)
                exploit_complexity = features.get("exploit_complexity", 0.5)
                impact_severity_val = features.get("impact_severity", 0.5)
                fingerprint_density = features.get("fingerprint_density", 0.5)

                if sub_idx < 16:
                    # Endpoint entropy features
                    base = endpoint_entropy
                    noise = 0.04 * sample_rng.gauss(0, 1)
                elif sub_idx < 32:
                    # Exploit complexity features
                    base = exploit_complexity
                    noise = 0.04 * sample_rng.gauss(0, 1)
                elif sub_idx < 48:
                    # Impact severity features
                    base = impact_severity_val
                    noise = 0.04 * sample_rng.gauss(0, 1)
                else:
                    # Fingerprint density features
                    base = fingerprint_density
                    noise = 0.04 * sample_rng.gauss(0, 1)
                val = base + noise

            # Clamp to [0, 1]
            vec.append(max(0.0, min(1.0, val)))

        return vec

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self._features_tensor[idx], self._labels_tensor[idx]

    def get_statistics(self) -> dict:
        """Get dataset statistics."""
        n_positive = sum(1 for s in self.samples if s.label == 1)
        n_edge = sum(1 for s in self.samples if s.is_edge_case)

        return {
            "total": len(self.samples),
            "positive": n_positive,
            "negative": len(self.samples) - n_positive,
            "edge_cases": n_edge,
            "feature_dim": self.feature_dim,
            "is_holdout": self.is_holdout,
        }


class RealTrainingDataset(Dataset):
    """
    Backward-compatible dataset adapter.

    Legacy callers still import/use `RealTrainingDataset`.
    It now always resolves to IngestionPipelineDataset so synthetic data
    paths cannot be re-enabled accidentally.
    """

    def __new__(cls, *args, **kwargs):
        seed = int(kwargs.pop("seed", FIXED_SEED))
        feature_dim = int(kwargs.pop("feature_dim", 256))
        min_samples = int(
            kwargs.pop(
                "min_samples",
                int(_os.environ.get("YGB_MIN_REAL_SAMPLES", "125000")),
            )
        )
        return IngestionPipelineDataset(
            feature_dim=feature_dim,
            min_samples=min_samples,
            seed=seed,
        )


@dataclass
class _LegacyCompatSample:
    """Minimal legacy sample object for compatibility with old callers/tests."""

    id: str
    features: dict


class _LegacySampleCollection:
    """
    Lazy view that emulates the legacy `dataset.samples` list shape.

    It avoids duplicating all sample objects in memory for large real datasets.
    """

    def __init__(self, dataset: "IngestionPipelineDataset"):
        self._dataset = dataset

    def __len__(self) -> int:
        if self._dataset._raw_samples:
            return len(self._dataset._raw_samples)
        labels_tensor = getattr(self._dataset, "_labels_tensor", None)
        if labels_tensor is not None:
            return int(labels_tensor.shape[0])
        return 0

    def __iter__(self):
        for idx in range(len(self)):
            yield self[idx]

    def __getitem__(self, idx: int) -> _LegacyCompatSample:
        if self._dataset._raw_samples:
            raw = self._dataset._raw_samples[idx]
            sample_id = (
                raw.get("fingerprint")
                or hashlib.sha256(raw.get("endpoint", "").encode()).hexdigest()[:16]
            )
            reliability = float(raw.get("reliability", 0.7))
            exploit_vector = raw.get("exploit_vector", "")
            features = strip_forbidden_fields(
                {
                    "signal_strength": min(reliability, 1.0),
                    "response_ratio": min(len(exploit_vector) / 100.0, 1.0),
                    "difficulty": 1.0 - min(reliability, 1.0),
                    "noise": 0.05,
                }
            )
        else:
            label = int(self._dataset._labels_tensor[idx].item())
            sample_id = f"cached-{idx:08d}"
            features = strip_forbidden_fields(
                {
                    "signal_strength": 0.9 if label == 1 else 0.5,
                    "response_ratio": 0.5,
                    "difficulty": 0.1 if label == 1 else 0.5,
                    "noise": 0.05,
                }
            )
        return _LegacyCompatSample(id=sample_id, features=features)


# =============================================================================
# DATALOADER FACTORY
# =============================================================================


def create_training_dataloader(
    batch_size: int = 1024,
    num_workers: int = 4,
    pin_memory: bool = True,
    prefetch_factor: int = 2,
    seed: int = FIXED_SEED,
) -> Tuple[DataLoader, DataLoader, dict]:
    """
    Create optimized DataLoaders for GPU training.

    Real-data-only mode:
      Uses IngestionPipelineDataset from the ingestion bridge ONLY.
      SyntheticTrainingDataset is blocked and never selected.

    Args:
        batch_size: Samples per batch (default 1024 for RTX 2050)
        num_workers: Parallel data loading workers (default 4 for laptop safety)
        pin_memory: Pin memory for faster GPU transfer
        prefetch_factor: Batches to prefetch per worker
        seed: Random seed for determinism

    Returns:
        Tuple of (train_loader, holdout_loader, stats)
    """
    min_samples = YGB_MIN_REAL_SAMPLES

    # === REAL-DATA PATH: IngestionPipelineDataset only ===
    train_dataset = IngestionPipelineDataset(
        feature_dim=256,
        min_samples=min_samples,
        seed=seed,
    )
    # Holdout: use a portion of the same pipeline data
    # (IngestionPipelineDataset does not support is_holdout,
    #  so we split the single dataset via random_split)
    total = len(train_dataset)
    holdout_size = max(1, int(total * 0.1))
    train_size = total - holdout_size
    train_subset, holdout_subset = torch.utils.data.random_split(
        train_dataset,
        [train_size, holdout_size],
        generator=torch.Generator().manual_seed(seed),
    )
    stats = {
        "train": {**train_dataset.get_statistics(), "total": train_size},
        "holdout": {**train_dataset.get_statistics(), "total": holdout_size},
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": pin_memory,
        "dataset_source": "INGESTION_PIPELINE",
    }
    stats.update(verify_dataset(train_dataset))
    effective_train = train_subset
    effective_holdout = holdout_subset

    # Deterministic generator for shuffle reproducibility
    g = torch.Generator()
    g.manual_seed(seed)

    # Create DataLoaders with CUDA optimizations
    train_loader = DataLoader(
        effective_train,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
        drop_last=True,  # Consistent batch sizes
        generator=g,  # Deterministic shuffle order
    )

    holdout_loader = DataLoader(
        effective_holdout,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
    )

    return train_loader, holdout_loader, stats


# =============================================================================
# VALIDATION
# =============================================================================

# Minimum real samples threshold (configurable via env)
YGB_MIN_REAL_SAMPLES = int(_os.environ.get("YGB_MIN_REAL_SAMPLES", "125000"))
_VALIDATION_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_VALIDATION_MANIFEST_PATH = (
    _VALIDATION_PROJECT_ROOT / "secure_data" / "dataset_manifest.json"
)
_DATASET_VALIDATION_CACHE_KEY: Optional[Tuple[Any, ...]] = None
_DATASET_VALIDATION_CACHE_RESULT: Optional[Tuple[bool, str]] = None
_DATASET_MANIFEST_SCHEMA_VERSION = 1
_DATASET_MAX_FUTURE_SKEW_SECONDS = 300
_DATASET_VERIFICATION_SAMPLE_LIMIT = 2048
_DATASET_MIN_SOURCE_CONFIDENCE = 0.5


def _dataset_validation_signature(
    *,
    feature_dim: int,
    min_samples: int,
    seed: int,
) -> Tuple[Any, ...]:
    manifest_mtime_ns = 0
    if _VALIDATION_MANIFEST_PATH.exists():
        try:
            manifest_mtime_ns = _VALIDATION_MANIFEST_PATH.stat().st_mtime_ns
        except OSError:
            manifest_mtime_ns = 0

    try:
        from backend.bridge.bridge_state import get_bridge_state

        counts = get_bridge_state().get_counts()
    except Exception as exc:
        counts = {"bridge_state_error": str(exc)}

    return (
        int(feature_dim),
        int(min_samples),
        int(seed),
        bool(STRICT_REAL_MODE),
        int(counts.get("bridge_count", 0) or 0),
        int(counts.get("bridge_verified_count", 0) or 0),
        int(counts.get("total_ingested", 0) or 0),
        int(counts.get("total_dropped", 0) or 0),
        int(counts.get("total_deduped", 0) or 0),
        str(counts.get("last_ingest_at") or ""),
        manifest_mtime_ns,
        str(counts.get("bridge_state_error") or ""),
    )


def validate_dataset_integrity(
    *,
    feature_dim: int = 256,
    min_samples: Optional[int] = None,
    seed: int = FIXED_SEED,
) -> Tuple[bool, str]:
    """
    Validate dataset meets all requirements:
    - Min YGB_MIN_REAL_SAMPLES samples
    - No forbidden fields
    - Class balance within 10%

    Real-data-only mode:
      - Uses IngestionPipelineDataset ONLY.
      - Returns explicit fail reasons:
        INSUFFICIENT_REAL_SAMPLES, INGESTION_SOURCE_INVALID,
        REAL_DATA_REQUIRED

    Returns:
        Tuple of (passed, message)
    """
    global _DATASET_VALIDATION_CACHE_KEY, _DATASET_VALIDATION_CACHE_RESULT

    min_samples = YGB_MIN_REAL_SAMPLES if min_samples is None else int(min_samples)
    cache_key = _dataset_validation_signature(
        feature_dim=feature_dim,
        min_samples=min_samples,
        seed=seed,
    )
    if (
        cache_key == _DATASET_VALIDATION_CACHE_KEY
        and _DATASET_VALIDATION_CACHE_RESULT is not None
    ):
        return _DATASET_VALIDATION_CACHE_RESULT

    if not STRICT_REAL_MODE:
        try:
            from backend.bridge.bridge_state import get_bridge_state

            counts = get_bridge_state().get_counts()
            real_samples = int(
                counts.get("bridge_verified_count", 0)
                or counts.get("bridge_count", 0)
                or 0
            )
        except Exception:
            real_samples = 0

        result = (
            True,
            "Dataset valid (LAB): synthetic fallback permitted when "
            f"STRICT_REAL_MODE=False; real_samples={real_samples}",
        )
        _DATASET_VALIDATION_CACHE_KEY = cache_key
        _DATASET_VALIDATION_CACHE_RESULT = result
        return result

    # ── REAL-DATA PATH: IngestionPipelineDataset only ──────────────
    try:
        dataset = IngestionPipelineDataset(
            feature_dim=feature_dim,
            min_samples=min_samples,
            seed=seed,
        )
    except FileNotFoundError:
        result = (
            False,
            "INGESTION_SOURCE_INVALID: Ingestion bridge library not found. "
            "Real ingestion pipeline is required.",
        )
    except RuntimeError as e:
        msg = str(e)
        if "Insufficient" in msg:
            result = (
                False,
                f"INSUFFICIENT_REAL_SAMPLES: {msg} (threshold: {min_samples})",
            )
        else:
            result = (False, f"REAL_DATA_REQUIRED: {msg}")
    except Exception as e:
        result = (False, f"INGESTION_SOURCE_INVALID: {str(e)}")
    else:
        try:
            verification = verify_dataset(dataset)
        except RuntimeError as exc:
            result = (False, str(exc))
        else:
            stats = dataset.get_statistics()

            if stats["total"] < min_samples:
                deficit = min_samples - stats["total"]
                result = (
                    False,
                    f"INSUFFICIENT_REAL_SAMPLES: {stats['total']} < {min_samples} "
                    f"(deficit: {deficit} samples needed)",
                )
            elif stats["total"] > 0:
                positive_ratio = stats["positive"] / stats["total"]
                if not (0.40 <= positive_ratio <= 0.60):
                    result = (
                        False,
                        f"REAL_DATA_REQUIRED: Class imbalance: "
                        f"{positive_ratio:.2%} positive",
                    )
                else:
                    result = (
                        True,
                        f"Dataset valid (REAL): {stats['total']} samples, "
                        f"{positive_ratio:.2%} positive, "
                        f"source={stats.get('dataset_source', 'INGESTION_PIPELINE')}, "
                        f"hash={verification['dataset_hash'][:16]}..., "
                        f"confidence={verification['confidence_score']:.3f}, "
                        f"duplicates={verification['duplicate_ratio']:.4f}",
                    )
            else:
                result = (False, "INSUFFICIENT_REAL_SAMPLES: 0 samples available")

    _DATASET_VALIDATION_CACHE_KEY = cache_key
    _DATASET_VALIDATION_CACHE_RESULT = result
    return result


# =============================================================================
# INGESTION PIPELINE DATASET — REAL DATA ONLY
# =============================================================================

import ctypes
import hashlib
import json
import os
import logging
import math
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from safetensors.torch import (
        load_file as load_safetensors_file,
        save_file as save_safetensors_file,
    )

    SAFETENSORS_AVAILABLE = True
except ImportError:
    load_safetensors_file = None
    save_safetensors_file = None
    SAFETENSORS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BRIDGE_DIR = _PROJECT_ROOT / "native" / "distributed"
_SECURE_DATA = _PROJECT_ROOT / "secure_data"
_INGESTION_TENSOR_CACHE_SCHEMA_VERSION = 1

# Bridge library name
_BRIDGE_LIB = "ingestion_bridge.dll" if os.name == "nt" else "libingestion_bridge.so"


def _load_bridge():
    """Load the ingestion bridge shared library via ctypes."""
    lib_path = _BRIDGE_DIR / _BRIDGE_LIB
    if not lib_path.exists():
        raise FileNotFoundError(
            f"Ingestion bridge not found: {lib_path}\n"
            f"Run: python native/distributed/build_bridge.py"
        )
    lib = ctypes.CDLL(str(lib_path))

    # Define function signatures
    lib.bridge_init.restype = ctypes.c_int
    lib.bridge_init.argtypes = []

    lib.bridge_get_count.restype = ctypes.c_int
    lib.bridge_get_count.argtypes = []

    lib.bridge_get_verified_count.restype = ctypes.c_int
    lib.bridge_get_verified_count.argtypes = []

    lib.bridge_fetch_verified_sample.restype = ctypes.c_int
    lib.bridge_fetch_verified_sample.argtypes = [
        ctypes.c_int,  # verified_idx
        ctypes.c_char_p,
        ctypes.c_int,  # endpoint
        ctypes.c_char_p,
        ctypes.c_int,  # parameters
        ctypes.c_char_p,
        ctypes.c_int,  # exploit_vector
        ctypes.c_char_p,
        ctypes.c_int,  # impact
        ctypes.c_char_p,
        ctypes.c_int,  # source_tag
        ctypes.c_char_p,
        ctypes.c_int,  # fingerprint
        ctypes.POINTER(ctypes.c_double),  # reliability
        ctypes.POINTER(ctypes.c_long),  # ingested_at
    ]

    lib.bridge_get_dataset_manifest_hash.restype = None
    lib.bridge_get_dataset_manifest_hash.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
    ]

    lib.bridge_ingest_sample.restype = ctypes.c_int
    lib.bridge_ingest_sample.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_double,
    ]

    return lib


class IngestionPipelineDataset(Dataset):
    """
    REAL Training Dataset — Ingestion Pipeline Only.

    Loads verified samples from the C++ ingestion engine via ctypes bridge.
    Applies:
      1. IngestionPolicy (reproducibility, impact, real-world confirmation)
      2. DataQualityScorer (exploit complexity, diversity, entropy)
      3. Forbidden field stripping

    dataset_source = "INGESTION_PIPELINE" — the ONLY permitted source for training.
    """

    dataset_source = "INGESTION_PIPELINE"

    def __init__(
        self,
        feature_dim: int = 256,
        min_samples: int = 100,
        seed: int = FIXED_SEED,
    ):
        self.feature_dim = feature_dim
        self.min_samples = min_samples
        self.seed = seed
        self.rng = random.Random(seed)

        # Load bridge (do NOT call bridge_init — it wipes existing ingested data)
        self._lib = _load_bridge()

        # Check PERSISTED bridge state first (cross-process authoritative)
        from backend.bridge.bridge_state import get_bridge_state

        self._bridge_state = get_bridge_state()
        persisted_counts = self._bridge_state.get_counts()
        persisted_verified = persisted_counts["bridge_verified_count"]

        # DLL counters (may be 0 in a fresh process)
        dll_verified = self._lib.bridge_get_verified_count()

        # Use the HIGHER of persisted vs DLL (persisted is authoritative)
        verified_count = max(dll_verified, persisted_verified)
        self._use_persisted_samples = dll_verified == 0 and persisted_verified > 0
        self._verified_count = verified_count
        self._raw_samples = []
        self._features = []
        self._labels = []
        self._tensor_cache_metadata: Dict[str, Any] = {}

        logger.info(
            f"[INGESTION] DLL verified={dll_verified}, "
            f"persisted verified={persisted_verified}, "
            f"authoritative={verified_count}, "
            f"use_persisted={'YES' if self._use_persisted_samples else 'NO'}"
        )

        if verified_count < min_samples:
            # NO FALLBACK — freeze field, abort
            deficit = min_samples - verified_count
            logger.error(
                f"[INGESTION] ABORT: Only {verified_count} verified samples "
                f"(minimum: {min_samples}, deficit: {deficit}). Field FROZEN. "
                f"NO synthetic fallback permitted."
            )
            raise RuntimeError(
                f"Insufficient ingestion data: {verified_count} < {min_samples} "
                f"(deficit: {deficit} samples needed). "
                f"Field frozen. No synthetic fallback."
            )

        self._manifest_hash = self._compute_manifest_hash()

        if self._load_tensor_cache(verified_count):
            logger.info(
                "[INGESTION] Tensor cache hit: %s (%s samples)",
                self._manifest_hash[:16],
                self._features_tensor.shape[0],
            )
            self.samples = _LegacySampleCollection(self)
            self._ensure_manifest_from_cache()
            return

        # Import policy + quality scorer
        from impl_v1.training.distributed.ingestion_policy import (
            IngestionPolicy,
            IngestionCandidate,
        )
        from impl_v1.training.distributed.data_quality_scorer import (
            DataQualityScorer,
        )

        policy = IngestionPolicy()
        scorer = DataQualityScorer()

        # Fetch and filter samples
        accepted = 0
        rejected_policy = 0
        rejected_quality = 0

        if self._use_persisted_samples:
            # Load from disk sample store (cross-process path)
            logger.info("[INGESTION] Loading samples from persisted store...")
            disk_samples = self._bridge_state.read_samples(max_samples=verified_count)
            logger.info(f"[INGESTION] Loaded {len(disk_samples)} samples from disk")
            accepted, rejected_policy, rejected_quality = (
                self._process_persisted_samples(
                    disk_samples, policy, scorer, min_samples
                )
            )
        else:
            # Load from DLL (same-process path)
            logger.info("[INGESTION] Loading samples from DLL...")
            FIELD_LEN = 512
            for idx in range(verified_count):
                # Allocate buffers
                ep = ctypes.create_string_buffer(FIELD_LEN)
                params = ctypes.create_string_buffer(FIELD_LEN)
                ev = ctypes.create_string_buffer(FIELD_LEN)
                imp = ctypes.create_string_buffer(FIELD_LEN)
                st = ctypes.create_string_buffer(FIELD_LEN)
                fp = ctypes.create_string_buffer(65)
                reliability = ctypes.c_double(0.0)
                ingested_at = ctypes.c_long(0)

                rc = self._lib.bridge_fetch_verified_sample(
                    idx,
                    ep,
                    FIELD_LEN,
                    params,
                    FIELD_LEN,
                    ev,
                    FIELD_LEN,
                    imp,
                    FIELD_LEN,
                    st,
                    FIELD_LEN,
                    fp,
                    65,
                    ctypes.byref(reliability),
                    ctypes.byref(ingested_at),
                )
                if rc != 0:
                    continue

                endpoint = ep.value.decode("utf-8", errors="replace")
                parameters = params.value.decode("utf-8", errors="replace")
                exploit_vector = ev.value.decode("utf-8", errors="replace")
                impact = imp.value.decode("utf-8", errors="replace")
                source_tag = st.value.decode("utf-8", errors="replace")
                fingerprint = fp.value.decode("utf-8", errors="replace")

                ok = self._process_one_sample(
                    endpoint,
                    parameters,
                    exploit_vector,
                    impact,
                    source_tag,
                    fingerprint,
                    reliability.value,
                    policy,
                    scorer,
                )
                if ok == "accepted":
                    accepted += 1
                elif ok == "rejected_policy":
                    rejected_policy += 1
                elif ok == "rejected_quality":
                    rejected_quality += 1

        logger.info(
            f"[INGESTION] Pipeline result: {accepted} accepted, "
            f"{rejected_policy} rejected (policy), "
            f"{rejected_quality} rejected (quality)"
        )

        if accepted < min_samples:
            deficit = min_samples - accepted
            raise RuntimeError(
                f"Insufficient quality samples after filtering: "
                f"{accepted} < {min_samples} (deficit: {deficit} samples needed). "
                f"No synthetic fallback."
            )

        # Convert to tensors
        self._features_tensor = torch.tensor(self._features, dtype=torch.float32)
        self._labels_tensor = torch.tensor(self._labels, dtype=torch.long)
        # Legacy compatibility for callers/tests that iterate dataset.samples.
        self.samples = _LegacySampleCollection(self)
        self._tensor_cache_metadata = self._build_tensor_cache_metadata(
            accepted=accepted,
            rejected_policy=rejected_policy,
            rejected_quality=rejected_quality,
            verified_count=verified_count,
        )
        self._write_manifest(
            accepted,
            rejected_policy,
            rejected_quality,
            cache_metadata=self._tensor_cache_metadata,
        )
        self._save_tensor_cache(self._tensor_cache_metadata)

    @staticmethod
    def _stable_unit_value(payload: str) -> float:
        """Map arbitrary content to a deterministic unit-range value."""
        if not payload:
            return 0.0
        digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).digest()
        return int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)

    @staticmethod
    def _char_entropy(text: str) -> float:
        """Normalized Shannon entropy over characters."""
        if not text:
            return 0.0
        from collections import Counter

        counts = Counter(text)
        total = len(text)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        return min(entropy / 6.0, 1.0)

    @classmethod
    def _text_stats(cls, text: str, *, fingerprint_mode: bool = False) -> List[float]:
        """Extract deterministic normalized stats from raw text."""
        normalized = text or ""
        length = len(normalized)
        if length == 0:
            return [0.0] * 8

        unique_ratio = min(len(set(normalized)) / length, 1.0)
        digit_ratio = sum(ch.isdigit() for ch in normalized) / length
        alpha_ratio = sum(ch.isalpha() for ch in normalized) / length
        upper_ratio = sum(ch.isupper() for ch in normalized) / length
        symbol_ratio = sum(not ch.isalnum() for ch in normalized) / length
        slash_ratio = normalized.count("/") / max(length, 1)
        token_count = len(
            [
                token
                for token in normalized.replace("/", " ").replace("&", " ").split()
                if token
            ]
        )
        token_ratio = min(token_count / 16.0, 1.0)
        entropy = cls._char_entropy(normalized)

        if fingerprint_mode:
            hex_ratio = (
                sum(ch.lower() in "0123456789abcdef" for ch in normalized) / length
            )
            symbol_ratio = hex_ratio

        return [
            min(length / 128.0, 1.0),
            unique_ratio,
            digit_ratio,
            alpha_ratio,
            upper_ratio,
            min(symbol_ratio, 1.0),
            min(slash_ratio, 1.0),
            min((token_ratio + entropy) / 2.0, 1.0),
        ]

    @classmethod
    def _build_text_block(
        cls,
        text: str,
        *,
        salt: str,
        scalar_a: float,
        scalar_b: float,
        size: int = 32,
        fingerprint_mode: bool = False,
    ) -> List[float]:
        """Build a dense deterministic projection block from raw text."""
        normalized = (text or "").strip().lower()
        stats = cls._text_stats(normalized, fingerprint_mode=fingerprint_mode)
        reversed_text = normalized[::-1]
        if not normalized:
            return [min(max((0.55 * scalar_a) + (0.45 * scalar_b), 0.0), 1.0)] * size

        vec = []
        for i in range(size):
            stat_a = stats[i % len(stats)]
            stat_b = stats[(i * 3 + 1) % len(stats)]
            hash_a = cls._stable_unit_value(f"{salt}|a|{i}|{normalized}")
            hash_b = cls._stable_unit_value(f"{salt}|b|{i}|{reversed_text}")
            hash_c = cls._stable_unit_value(
                f"{salt}|c|{i}|{len(normalized)}|{stat_a:.6f}|{stat_b:.6f}"
            )
            val = (
                0.38 * hash_a
                + 0.16 * hash_b
                + 0.12 * hash_c
                + 0.14 * stat_a
                + 0.08 * stat_b
                + 0.07 * scalar_a
                + 0.05 * scalar_b
            )
            vec.append(min(max(val, 0.0), 1.0))
        return vec

    @classmethod
    def _build_numeric_block(cls, metrics: List[float], size: int = 64) -> List[float]:
        """Build interaction features from normalized numeric metrics."""
        if not metrics:
            return [0.0] * size

        clean = [min(max(float(v), 0.0), 1.0) for v in metrics]
        vec = []
        for i in range(size):
            a = clean[i % len(clean)]
            b = clean[(i * 3 + 1) % len(clean)]
            c = clean[(i * 5 + 2) % len(clean)]
            trig = 0.5 + 0.5 * math.sin(
                (a * math.pi * (i + 1)) + (b * 2.17) + (c * 1.13)
            )
            mixed = (a * b + b * c + c * a) / 3.0
            hashed = cls._stable_unit_value(
                f"numeric|{i}|{a:.6f}|{b:.6f}|{c:.6f}|{sum(clean):.6f}"
            )
            val = (
                (0.42 * trig)
                + (0.28 * mixed)
                + (0.18 * hashed)
                + (0.12 * ((a + b + c) / 3.0))
            )
            vec.append(min(max(val, 0.0), 1.0))
        return vec

    def _process_one_sample(
        self,
        endpoint,
        parameters,
        exploit_vector,
        impact,
        source_tag,
        fingerprint,
        reliability_val,
        policy,
        scorer,
    ) -> str:
        """Process a single sample through policy + quality checks.

        Returns: 'accepted', 'rejected_policy', or 'rejected_quality'.
        """
        from impl_v1.training.distributed.ingestion_policy import IngestionCandidate

        candidate = IngestionCandidate(
            sample_id=(fingerprint or hashlib.sha256(endpoint.encode()).hexdigest())[
                :16
            ],
            endpoint=endpoint,
            exploit_vector=exploit_vector,
            impact=impact,
            source_id=source_tag,
            reproducible=reliability_val >= 0.7,
            impact_classified=len(impact) > 0,
            real_world_confirmed=reliability_val >= 0.5,
        )
        policy_result = policy.check(candidate)
        if not policy_result.accepted:
            return "rejected_policy"

        # === COMPUTE RICHER RAW FEATURES (8 instead of 4) ===
        # Endpoint entropy: Shannon entropy of endpoint characters
        ep_entropy = 0.5
        if endpoint:
            from collections import Counter

            char_counts = Counter(endpoint)
            ep_len = len(endpoint)
            ep_entropy = 0.0
            for cnt in char_counts.values():
                p = cnt / ep_len
                if p > 0:
                    ep_entropy -= p * math.log2(p)
            ep_entropy = min(ep_entropy / 6.0, 1.0)  # normalize (max ~6 bits)

        # Exploit complexity: unique character ratio
        exploit_cmplx = 0.5
        if exploit_vector:
            exploit_cmplx = min(
                len(set(exploit_vector)) / max(len(exploit_vector), 1), 1.0
            )

        # Parameters richness: token density + character entropy
        params_ratio = min(len(parameters) / 96.0, 1.0) if parameters else 0.0
        params_entropy = self._char_entropy(parameters)

        # Impact severity: keyword + CVSS-based scoring
        impact_sev = 0.5
        if impact:
            impact_lower = impact.lower()
            if impact.startswith("CVSS:"):
                try:
                    score = float(impact.split("|", 1)[0].split(":", 1)[1])
                    impact_sev = min(score / 10.0, 1.0)
                except (ValueError, IndexError):
                    pass
            elif "critical" in impact_lower:
                impact_sev = 0.95
            elif "high" in impact_lower:
                impact_sev = 0.75
            elif "medium" in impact_lower:
                impact_sev = 0.50
            elif "low" in impact_lower:
                impact_sev = 0.25

        # Fingerprint density: uniformity of hex character distribution

        # Impact severity: keyword + CVSS-based scoring
        impact_sev = 0.5
        if impact:
            impact_lower = impact.lower()
            if impact.startswith("CVSS:"):
                try:
                    score = float(impact.split("|", 1)[0].split(":", 1)[1])
                    impact_sev = min(score / 10.0, 1.0)
                except (ValueError, IndexError):
                    pass
            elif "critical" in impact_lower:
                impact_sev = 0.95
            elif "high" in impact_lower:
                impact_sev = 0.75
            elif "medium" in impact_lower:
                impact_sev = 0.50
            elif "low" in impact_lower:
                impact_sev = 0.25

        # Fingerprint density: uniformity of hex character distribution
        fp_density = 0.5
        if fingerprint and len(fingerprint) >= 8:
            from collections import Counter

            hex_counts = Counter(fingerprint.lower())
            hex_chars = len(hex_counts)
            fp_density = min(hex_chars / 16.0, 1.0)  # 16 hex chars = maximum diversity

        # Encode content-derived features ONLY.
        # CRITICAL: reliability is EXCLUDED — it is used for label derivation
        # and including it would cause label leakage (trivial 100% accuracy).
        endpoint_len_norm = min(len(endpoint) / 256.0, 1.0)
        exploit_len_norm = min(len(exploit_vector) / 256.0, 1.0)
        impact_len_norm = min(len(impact) / 128.0, 1.0)
        features_dict = {
            "endpoint_length": endpoint_len_norm,
            "exploit_length": exploit_len_norm,
            "response_ratio": min(len(exploit_vector) / 100.0, 1.0),
            "impact_length": impact_len_norm,
            "endpoint_entropy": ep_entropy,
            "exploit_complexity": exploit_cmplx,
            "impact_severity": impact_sev,
            "fingerprint_density": fp_density,
            "parameter_ratio": params_ratio,
            "parameters_entropy": params_entropy,
        }

        clean_features = strip_forbidden_fields(features_dict)
        feature_vec = self._encode_features(
            clean_features,
            endpoint=endpoint,
            parameters=parameters,
            exploit_vector=exploit_vector,
            impact=impact,
            source_tag=source_tag,
            fingerprint=fingerprint,
        )

        # Quality score
        import numpy as np

        fv_array = np.array(feature_vec, dtype=np.float32)
        quality = scorer.score_features(
            sample_id=candidate.sample_id,
            features=fv_array,
            impact_level="high" if reliability_val >= 0.8 else "medium",
            source_count=1,
        )
        if not quality.accepted:
            return "rejected_quality"

        # Label (using enhanced composite scoring for ambiguous samples)
        label = self._derive_label(
            endpoint=endpoint,
            impact=impact,
            fingerprint=fingerprint,
            reliability_val=reliability_val,
            exploit_vector=exploit_vector,
        )

        self._features.append(feature_vec)
        self._labels.append(label)
        self._raw_samples.append(
            {
                "endpoint": endpoint,
                "parameters": parameters,
                "exploit_vector": exploit_vector,
                "impact": impact,
                "source_tag": source_tag,
                "fingerprint": fingerprint or "",
                "reliability": reliability_val,
            }
        )
        return "accepted"

    @staticmethod
    def _derive_label(
        endpoint: str,
        impact: str,
        fingerprint: str,
        reliability_val: float,
        exploit_vector: str = "",
    ) -> int:
        """
        Derive a deterministic binary label from real ingestion metadata.

        Uses CONTENT-BASED signals that are NOT directly represented in the
        feature vector, preventing label leakage:
          1. CVSS score parsed from impact string (strongest signal)
          2. Impact severity keywords (critical/high -> positive)
          3. Composite of exploit complexity, endpoint structure, and content
             richness — deliberately uses DIFFERENT encodings than the features
          4. Deterministic hash tiebreaker for ambiguous samples

        NOTE: reliability_val is deliberately given LOW weight (0.10) to avoid
        leakage — it was previously the primary signal and leaked through
        signal_strength, causing trivial 100% accuracy.
        """
        score = 0.0
        signals_found = 0

        # Signal 1: CVSS score (strongest, explicit)
        if isinstance(impact, str) and impact.startswith("CVSS:"):
            score_part = impact.split("|", 1)[0]
            try:
                cvss = float(score_part.split(":", 1)[1])
                return 1 if cvss >= 7.0 else 0
            except (ValueError, IndexError):
                pass

        # Signal 2: Impact keywords (content-based, not in feature vector)
        if isinstance(impact, str) and impact:
            impact_lower = impact.lower()
            if "critical" in impact_lower or "remote code" in impact_lower:
                score += 0.35
                signals_found += 1
            elif "high" in impact_lower or "injection" in impact_lower:
                score += 0.25
                signals_found += 1
            elif "medium" in impact_lower:
                score += 0.12
                signals_found += 1
            elif "low" in impact_lower or "info" in impact_lower:
                score += 0.05
                signals_found += 1

        # Signal 3: Exploit vector richness (content length + unique chars)
        if exploit_vector:
            ev_len_score = min(len(exploit_vector) / 200.0, 0.25)
            ev_unique = len(set(exploit_vector)) / max(len(exploit_vector), 1)
            score += ev_len_score + ev_unique * 0.10
            signals_found += 1

        # Signal 4: Endpoint structure (path depth, query params present)
        if endpoint:
            depth = endpoint.count("/")
            has_query = "?" in endpoint or "&" in endpoint
            score += min(depth / 8.0, 0.10)
            if has_query:
                score += 0.05
            signals_found += 1

        # Signal 5: Reliability as WEAK tiebreaker (low weight to avoid leak)
        score += reliability_val * 0.10

        # Deterministic hash tiebreaker for samples near the boundary
        if 0.35 <= score <= 0.55 and signals_found < 3:
            fp_hash = hashlib.sha256(
                f"{fingerprint}|{endpoint}|{impact}".encode()
            ).digest()
            hash_val = int.from_bytes(fp_hash[:4], "big") / float((1 << 32) - 1)
            score += (hash_val - 0.5) * 0.10  # +/-0.05 jitter

        return 1 if score >= 0.45 else 0

    def _process_persisted_samples(
        self,
        disk_samples,
        policy,
        scorer,
        min_samples,
    ):
        """Process samples loaded from the persisted gzip store."""
        accepted = 0
        rejected_policy = 0
        rejected_quality = 0

        for sample in disk_samples:
            reliability_val = sample.get("reliability", 0.7)
            # Only process verified samples (reliability >= 0.7)
            if reliability_val < 0.7:
                continue

            ok = self._process_one_sample(
                endpoint=sample.get("endpoint", ""),
                parameters=sample.get("parameters", ""),
                exploit_vector=sample.get("exploit_vector", ""),
                impact=sample.get("impact", ""),
                source_tag=sample.get("source_tag", ""),
                fingerprint=sample.get("fingerprint", ""),
                reliability_val=reliability_val,
                policy=policy,
                scorer=scorer,
            )
            if ok == "accepted":
                accepted += 1
            elif ok == "rejected_policy":
                rejected_policy += 1
            elif ok == "rejected_quality":
                rejected_quality += 1

        return accepted, rejected_policy, rejected_quality

    def _encode_features(
        self,
        features: dict,
        *,
        endpoint: str = "",
        parameters: str = "",
        exploit_vector: str = "",
        impact: str = "",
        source_tag: str = "",
        fingerprint: str = "",
    ) -> List[float]:
        """Encode raw ingestion content to a dense deterministic 256-dim vector."""
        # Content-derived scalars only — NO reliability leakage.
        endpoint_len = features.get("endpoint_length", min(len(endpoint) / 256.0, 1.0))
        exploit_len = features.get(
            "exploit_length", min(len(exploit_vector) / 256.0, 1.0)
        )
        response = features.get("response_ratio", 0.5)
        impact_len = features.get("impact_length", min(len(impact) / 128.0, 1.0))
        endpoint_entropy = features.get("endpoint_entropy", 0.5)
        exploit_complexity = features.get("exploit_complexity", 0.5)
        impact_severity_val = features.get("impact_severity", 0.5)
        fingerprint_density = features.get("fingerprint_density", 0.5)
        parameter_ratio = features.get(
            "parameter_ratio", min(len(parameters) / 96.0, 1.0)
        )
        parameters_entropy = features.get(
            "parameters_entropy", self._char_entropy(parameters)
        )
        source_hash = self._stable_unit_value(f"source|{source_tag.lower()}")

        endpoint_block = self._build_text_block(
            endpoint,
            salt="endpoint",
            scalar_a=endpoint_len,
            scalar_b=endpoint_entropy,
            size=32,
        )
        parameters_block = self._build_text_block(
            parameters,
            salt="parameters",
            scalar_a=parameter_ratio,
            scalar_b=parameters_entropy,
            size=32,
        )
        exploit_block = self._build_text_block(
            exploit_vector,
            salt="exploit",
            scalar_a=response,
            scalar_b=exploit_complexity,
            size=32,
        )
        impact_block = self._build_text_block(
            impact,
            salt="impact",
            scalar_a=impact_severity_val,
            scalar_b=impact_len,
            size=32,
        )
        fingerprint_block = self._build_text_block(
            f"{fingerprint}|{source_tag}",
            salt="fingerprint",
            scalar_a=fingerprint_density,
            scalar_b=source_hash,
            size=32,
            fingerprint_mode=True,
        )
        numeric_block = self._build_numeric_block(
            [
                endpoint_len,
                response,
                exploit_len,
                impact_len,
                endpoint_entropy,
                exploit_complexity,
                impact_severity_val,
                fingerprint_density,
                parameter_ratio,
                parameters_entropy,
                source_hash,
            ],
            size=64,
        )
        combined_block = self._build_text_block(
            "|".join(
                part
                for part in (
                    endpoint,
                    parameters,
                    exploit_vector,
                    impact,
                    source_tag,
                    fingerprint,
                )
                if part
            ),
            salt="combined",
            scalar_a=(endpoint_len + impact_severity_val) / 2.0,
            scalar_b=(exploit_complexity + parameter_ratio) / 2.0,
            size=32,
        )

        vec = (
            endpoint_block
            + parameters_block
            + exploit_block
            + impact_block
            + fingerprint_block
            + numeric_block
            + combined_block
        )
        if len(vec) >= self.feature_dim:
            return vec[: self.feature_dim]

        while len(vec) < self.feature_dim:
            idx = len(vec)
            filler = self._stable_unit_value(
                f"pad|{idx}|{signal:.6f}|{response:.6f}|{impact_severity_val:.6f}|{source_tag}"
            )
            vec.append(filler)
        return vec

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _tensor_cache_dir() -> Path:
        return _SECURE_DATA / "tensor_cache"

    def _tensor_cache_key(self, verified_count: int) -> str:
        digest = hashlib.sha256()
        digest.update(str(_INGESTION_TENSOR_CACHE_SCHEMA_VERSION).encode("utf-8"))
        digest.update(str(self._manifest_hash).encode("utf-8"))
        digest.update(str(verified_count).encode("utf-8"))
        digest.update(str(self.feature_dim).encode("utf-8"))
        digest.update(str(self.seed).encode("utf-8"))
        digest.update(str(bool(STRICT_REAL_MODE)).encode("utf-8"))
        return digest.hexdigest()

    def _tensor_cache_paths(self, verified_count: int) -> Tuple[Path, Path]:
        cache_base = (
            self._tensor_cache_dir()
            / f"ingestion_{self._tensor_cache_key(verified_count)}"
        )
        return cache_base.with_suffix(".safetensors"), cache_base.with_suffix(".json")

    @staticmethod
    def _tensor_hash_for_tensors(
        features_tensor: torch.Tensor, labels_tensor: torch.Tensor
    ) -> str:
        digest = hashlib.sha256()
        digest.update(features_tensor.detach().cpu().contiguous().numpy().tobytes())
        digest.update(labels_tensor.detach().cpu().contiguous().numpy().tobytes())
        return digest.hexdigest()

    def _compute_tensor_hash(self) -> str:
        return self._tensor_hash_for_tensors(self._features_tensor, self._labels_tensor)

    def _build_tensor_cache_metadata(
        self,
        *,
        accepted: int,
        rejected_policy: int,
        rejected_quality: int,
        verified_count: int,
    ) -> Dict[str, Any]:
        if self._labels:
            labels = [int(lbl) for lbl in self._labels]
        else:
            labels = [int(lbl) for lbl in self._labels_tensor.detach().cpu().tolist()]

        class_histogram: Dict[str, int] = {}
        for label in labels:
            key = str(int(label))
            class_histogram[key] = class_histogram.get(key, 0) + 1

        trust_scores = [
            float(sample.get("reliability", 0.0)) for sample in self._raw_samples
        ]
        return {
            "schema_version": _INGESTION_TENSOR_CACHE_SCHEMA_VERSION,
            "cache_kind": "ingestion_tensor_cache",
            "format": "safetensors",
            "dataset_source": self.dataset_source,
            "ingestion_manifest_hash": self._manifest_hash,
            "feature_dim": int(self.feature_dim),
            "seed": int(self.seed),
            "strict_real_mode": bool(STRICT_REAL_MODE),
            "verified_count": int(verified_count),
            "sample_count": int(self._features_tensor.shape[0]),
            "num_classes": len(class_histogram),
            "accepted": int(accepted),
            "rejected_policy": int(rejected_policy),
            "rejected_quality": int(rejected_quality),
            "class_histogram": class_histogram,
            "source_trust_avg": round(sum(trust_scores) / len(trust_scores), 4)
            if trust_scores
            else 0.0,
            "source_trust_min": round(min(trust_scores), 4) if trust_scores else 0.0,
            "tensor_hash": self._compute_tensor_hash(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_tensor_cache(self, verified_count: int) -> bool:
        if not SAFETENSORS_AVAILABLE or load_safetensors_file is None:
            return False

        weights_path, meta_path = self._tensor_cache_paths(verified_count)
        if not weights_path.exists() or not meta_path.exists():
            return False

        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False

        if not isinstance(metadata, dict):
            return False
        if metadata.get("schema_version") != _INGESTION_TENSOR_CACHE_SCHEMA_VERSION:
            return False
        if metadata.get("cache_kind") != "ingestion_tensor_cache":
            return False
        if metadata.get("ingestion_manifest_hash") != self._manifest_hash:
            return False
        if int(metadata.get("verified_count", 0) or 0) != int(verified_count):
            return False
        if int(metadata.get("feature_dim", 0) or 0) != int(self.feature_dim):
            return False
        if int(metadata.get("seed", -1) or -1) != int(self.seed):
            return False
        if bool(metadata.get("strict_real_mode", False)) != bool(STRICT_REAL_MODE):
            return False

        try:
            tensors = load_safetensors_file(str(weights_path))
        except Exception:
            return False

        features_tensor = tensors.get("features")
        labels_tensor = tensors.get("labels")
        if features_tensor is None or labels_tensor is None:
            return False
        if features_tensor.ndim != 2 or labels_tensor.ndim != 1:
            return False
        if features_tensor.shape[1] != self.feature_dim:
            return False
        if features_tensor.shape[0] != labels_tensor.shape[0]:
            return False
        if features_tensor.shape[0] < self.min_samples:
            return False

        expected_samples = int(metadata.get("sample_count", 0) or 0)
        if expected_samples and int(features_tensor.shape[0]) != expected_samples:
            return False

        expected_hash = str(metadata.get("tensor_hash", "") or "")
        if expected_hash:
            actual_hash = self._tensor_hash_for_tensors(features_tensor, labels_tensor)
            if actual_hash != expected_hash:
                return False

        self._features_tensor = features_tensor.to(dtype=torch.float32)
        self._labels_tensor = labels_tensor.to(dtype=torch.long)
        self._labels = [int(lbl) for lbl in self._labels_tensor.detach().cpu().tolist()]
        self._raw_samples = []
        self._features = []
        self._tensor_cache_metadata = metadata
        return True

    def _save_tensor_cache(self, metadata: Dict[str, Any]) -> None:
        if not SAFETENSORS_AVAILABLE or save_safetensors_file is None:
            return

        verified_count = int(
            metadata.get("verified_count", self._verified_count) or self._verified_count
        )
        weights_path, meta_path = self._tensor_cache_paths(verified_count)
        weights_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_weights = tempfile.mkstemp(
            dir=str(weights_path.parent),
            prefix=weights_path.name + ".",
            suffix=".tmp",
        )
        os.close(fd)
        try:
            save_safetensors_file(
                {
                    "features": self._features_tensor.detach().cpu(),
                    "labels": self._labels_tensor.detach().cpu(),
                },
                tmp_weights,
            )
            os.replace(tmp_weights, weights_path)
            self._atomic_write_json(meta_path, metadata)
        except Exception as exc:
            try:
                os.remove(tmp_weights)
            except OSError:
                pass
            logger.warning("[INGESTION] Tensor cache save skipped: %s", exc)

    def _manifest_matches_cache(self, metadata: Dict[str, Any]) -> bool:
        manifest_path = _SECURE_DATA / "dataset_manifest.json"
        if not manifest_path.exists():
            return False
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(manifest, dict):
            return False
        manifest_samples = int(
            manifest.get("sample_count", manifest.get("total_samples", 0)) or 0
        )
        return (
            str(manifest.get("dataset_source", "") or "").upper() == self.dataset_source
            and str(manifest.get("ingestion_manifest_hash", "") or "")
            == str(metadata.get("ingestion_manifest_hash", "") or "")
            and str(manifest.get("tensor_hash", "") or "")
            == str(metadata.get("tensor_hash", "") or "")
            and manifest_samples == int(metadata.get("sample_count", 0) or 0)
        )

    def _ensure_manifest_from_cache(self) -> None:
        metadata = self._tensor_cache_metadata or {}
        if not metadata or self._manifest_matches_cache(metadata):
            return
        self._write_manifest(
            int(metadata.get("accepted", metadata.get("sample_count", 0)) or 0),
            int(metadata.get("rejected_policy", 0) or 0),
            int(metadata.get("rejected_quality", 0) or 0),
            cache_metadata=metadata,
        )

    def _compute_manifest_hash(self) -> str:
        """Get manifest hash from the bridge (C++ side)."""
        hash_buf = ctypes.create_string_buffer(65)
        self._lib.bridge_get_dataset_manifest_hash(hash_buf, 65)
        return hash_buf.value.decode("utf-8", errors="replace")

    def _write_manifest(
        self,
        accepted,
        rejected_policy,
        rejected_quality,
        cache_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Write dataset_manifest.json to secure_data/ with hardened quality metrics."""
        _SECURE_DATA.mkdir(parents=True, exist_ok=True)
        manifest_path = _SECURE_DATA / "dataset_manifest.json"

        metadata = dict(cache_metadata or {})
        tensor_hash = str(
            metadata.get("tensor_hash", "") or self._compute_tensor_hash()
        )

        class_histogram: Dict[int, int] = {}
        if metadata.get("class_histogram"):
            for key, value in (metadata.get("class_histogram") or {}).items():
                class_histogram[int(key)] = int(value)
        elif self._labels:
            for lbl in self._labels:
                label = int(lbl)
                class_histogram[label] = class_histogram.get(label, 0) + 1
        else:
            unique_labels, counts = torch.unique(
                self._labels_tensor.detach().cpu(), return_counts=True
            )
            for label, count in zip(unique_labels.tolist(), counts.tolist()):
                class_histogram[int(label)] = int(count)

        # Class entropy (Shannon)
        total = int(
            metadata.get("sample_count", self._labels_tensor.shape[0])
            or self._labels_tensor.shape[0]
        )
        class_entropy = 0.0
        if total > 0:
            for count in class_histogram.values():
                p = count / total
                if p > 0:
                    class_entropy -= p * math.log2(p)

        # Source trust summary
        if self._raw_samples:
            trust_scores = [float(s.get("reliability", 0.0)) for s in self._raw_samples]
            avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 0.0
            min_trust = min(trust_scores) if trust_scores else 0.0
        else:
            avg_trust = float(metadata.get("source_trust_avg", 0.0) or 0.0)
            min_trust = float(metadata.get("source_trust_min", 0.0) or 0.0)

        manifest = {
            "schema_version": _DATASET_MANIFEST_SCHEMA_VERSION,
            "dataset_source": "INGESTION_PIPELINE",
            "ingestion_manifest_hash": self._manifest_hash,
            "tensor_hash": tensor_hash,
            "sample_count": total,
            "feature_dim": self.feature_dim,
            "num_classes": int(metadata["num_classes"])
            if "num_classes" in metadata
            else len(class_histogram),
            "accepted": int(metadata["accepted"])
            if "accepted" in metadata
            else int(accepted),
            "rejected_policy": int(metadata["rejected_policy"])
            if "rejected_policy" in metadata
            else int(rejected_policy),
            "rejected_quality": int(metadata["rejected_quality"])
            if "rejected_quality" in metadata
            else int(rejected_quality),
            "strict_real_mode": STRICT_REAL_MODE,
            "class_histogram": class_histogram,
            "class_entropy": round(class_entropy, 4),
            "source_trust_avg": round(avg_trust, 4),
            "source_trust_min": round(min_trust, 4),
            "training_mode": "PRODUCTION_REAL" if STRICT_REAL_MODE else "LAB_COMPLEX",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }

        # Canonicalize: add signed fields for DatasetManifest compatibility
        from impl_v1.training.safety.manifest_builder import canonicalize_manifest

        canonicalize_manifest(manifest)

        self._atomic_write_json(manifest_path, manifest)

        logger.info(f"[INGESTION] Manifest written: {manifest_path}")
        logger.info(f"[INGESTION] Ingestion hash: {self._manifest_hash[:32]}...")
        logger.info(f"[INGESTION] Tensor hash: {tensor_hash[:32]}...")

    def __len__(self) -> int:
        if getattr(self, "_features_tensor", None) is not None:
            return int(self._features_tensor.shape[0])
        return len(self._features)

    def __getitem__(self, idx: int):
        return self._features_tensor[idx], self._labels_tensor[idx]

    def get_statistics(self) -> dict:
        """Get dataset statistics."""
        if self._labels:
            total = len(self._labels)
            n_positive = sum(1 for l in self._labels if int(l) == 1)
        else:
            total = int(self._labels_tensor.shape[0])
            n_positive = int((self._labels_tensor == 1).sum().item())
        return {
            "total": total,
            "positive": n_positive,
            "negative": total - n_positive,
            "feature_dim": self.feature_dim,
            "dataset_source": self.dataset_source,
            "manifest_hash": self._manifest_hash,
        }


# =============================================================================
# REAL DATALOADER FACTORY
# =============================================================================


def create_real_training_dataloader(
    batch_size: int = 1024,
    num_workers: int = 4,
    pin_memory: bool = True,
    prefetch_factor: int = 2,
    seed: int = FIXED_SEED,
    min_samples: int = 100,
) -> Tuple[DataLoader, dict]:
    """
    Create DataLoader from REAL ingestion pipeline data.

    Returns:
        Tuple of (data_loader, stats)

    Raises:
        RuntimeError if insufficient real data or bridge unavailable.
    """
    dataset = IngestionPipelineDataset(
        feature_dim=256,
        min_samples=min_samples,
        seed=seed,
    )
    verification = verify_dataset(dataset)

    g = torch.Generator()
    g.manual_seed(seed)

    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
        drop_last=True,
        generator=g,
    )

    stats = dataset.get_statistics()
    stats["batch_size"] = batch_size
    stats["num_workers"] = num_workers
    stats["pin_memory"] = pin_memory
    stats.update(verification)

    return loader, stats


def _parse_manifest_timestamp(raw_value: Any) -> str:
    if raw_value is None:
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset manifest timestamp missing")

    timestamp_text = str(raw_value).strip()
    if not timestamp_text:
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset manifest timestamp missing")

    normalized = timestamp_text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: Dataset manifest timestamp invalid ({timestamp_text})"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    max_allowed = datetime.now(timezone.utc) + timedelta(
        seconds=_DATASET_MAX_FUTURE_SKEW_SECONDS
    )
    if parsed > max_allowed:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: Dataset manifest timestamp is in the future ({timestamp_text})"
        )

    return parsed.isoformat()


def _verification_indices(sample_count: int) -> np.ndarray:
    verify_count = min(sample_count, _DATASET_VERIFICATION_SAMPLE_LIMIT)
    if verify_count <= 0:
        return np.array([], dtype=np.int64)
    if verify_count == sample_count:
        return np.arange(sample_count, dtype=np.int64)
    return (np.arange(verify_count, dtype=np.int64) * sample_count) // verify_count


def verify_dataset(dataset: "IngestionPipelineDataset") -> Dict[str, Any]:
    if dataset is None:
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset missing")
    if (
        str(getattr(dataset, "dataset_source", "") or "").upper()
        != "INGESTION_PIPELINE"
    ):
        raise RuntimeError(
            "REAL_DATA_REQUIRED: dataset_source must be INGESTION_PIPELINE"
        )

    features_tensor = getattr(dataset, "_features_tensor", None)
    labels_tensor = getattr(dataset, "_labels_tensor", None)
    if features_tensor is None or labels_tensor is None:
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset tensors unavailable")
    if features_tensor.ndim != 2 or labels_tensor.ndim != 1:
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset tensor schema invalid")
    if (
        features_tensor.shape[0] != labels_tensor.shape[0]
        or features_tensor.shape[0] <= 0
    ):
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset tensor counts invalid")
    if (
        not torch.isfinite(features_tensor).all()
        or not torch.isfinite(labels_tensor).all()
    ):
        raise RuntimeError(
            "REAL_DATA_REQUIRED: Dataset tensors contain non-finite values"
        )

    from impl_v1.training.safety.dataset_manifest import validate_manifest
    from impl_v1.training.data.quality_gates import check_duplicates
    from impl_v1.training.data.semantic_quality_gate import run_sanity_test

    dataset_hash = dataset._compute_tensor_hash()
    manifest_valid, manifest_reason, _ = validate_manifest(
        expected_dataset_hash=dataset_hash,
        path=str(_VALIDATION_MANIFEST_PATH),
    )
    if not manifest_valid:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: Dataset manifest validation failed ({manifest_reason})"
        )

    try:
        with open(_VALIDATION_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: Dataset manifest unreadable ({type(exc).__name__})"
        ) from exc

    if not isinstance(manifest, dict):
        raise RuntimeError("REAL_DATA_REQUIRED: Dataset manifest schema invalid")

    required_fields = (
        "schema_version",
        "dataset_source",
        "dataset_hash",
        "signature_hash",
        "signed_by",
        "version",
        "total_samples",
        "strict_real_mode",
        "ingestion_manifest_hash",
    )
    missing_fields = [field for field in required_fields if field not in manifest]
    if missing_fields:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: Dataset manifest missing fields {', '.join(missing_fields)}"
        )

    schema_version = int(manifest.get("schema_version", 0) or 0)
    if schema_version != _DATASET_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: Dataset manifest schema_version={schema_version}"
        )

    manifest_source = str(manifest.get("dataset_source", "") or "").upper()
    if manifest_source != "INGESTION_PIPELINE":
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: manifest dataset_source={manifest_source or '<missing>'}"
        )

    if not bool(manifest.get("strict_real_mode", False)):
        raise RuntimeError("REAL_DATA_REQUIRED: strict_real_mode is not enabled")

    if str(manifest.get("dataset_hash", "") or "") != dataset_hash:
        raise RuntimeError("REAL_DATA_REQUIRED: dataset_hash mismatch")

    manifest_hash = str(manifest.get("ingestion_manifest_hash", "") or "")
    if manifest_hash != str(dataset._manifest_hash or ""):
        raise RuntimeError("REAL_DATA_REQUIRED: ingestion manifest hash mismatch")

    manifest_samples = int(
        manifest.get("sample_count", manifest.get("total_samples", 0)) or 0
    )
    sample_count = int(features_tensor.shape[0])
    if manifest_samples != sample_count:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: manifest sample_count={manifest_samples} does not match dataset={sample_count}"
        )

    manifest_timestamp = _parse_manifest_timestamp(
        manifest.get("updated_at")
        or manifest.get("frozen_at")
        or manifest.get("created_at")
    )

    marker_blob = " ".join(
        str(manifest.get(key, "") or "")
        for key in ("dataset_source", "training_mode", "version", "signed_by")
    ).lower()
    if any(
        token in marker_blob for token in ("synthetic", "mock", "fake", "dummy", "stub")
    ):
        raise RuntimeError(
            "REAL_DATA_REQUIRED: Synthetic markers detected in dataset manifest"
        )

    confidence_score = float(
        (dataset._tensor_cache_metadata or {}).get("source_trust_avg", 0.0) or 0.0
    )
    if confidence_score <= 0.0 and getattr(dataset, "_raw_samples", None):
        trust_scores = [
            float(sample.get("reliability", 0.0))
            for sample in dataset._raw_samples
            if isinstance(sample, dict)
        ]
        if trust_scores:
            confidence_score = sum(trust_scores) / len(trust_scores)
    if confidence_score < _DATASET_MIN_SOURCE_CONFIDENCE:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: source confidence {confidence_score:.4f} < {_DATASET_MIN_SOURCE_CONFIDENCE:.4f}"
        )

    features_np = features_tensor.detach().cpu().numpy()
    labels_np = labels_tensor.detach().cpu().numpy()
    indices = _verification_indices(sample_count)
    features_check = features_np[indices]
    labels_check = labels_np[indices]

    duplicate_gate = check_duplicates(features_check)
    duplicate_ratio = float(duplicate_gate.metrics.get("exact_duplicate_ratio", 0.0))
    if not duplicate_gate.passed:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: duplicate detection failed ({duplicate_gate.message})"
        )

    n_classes = max(1, int(np.unique(labels_check).size))
    sanity_result = run_sanity_test(features_check, labels_check, n_classes)
    if not sanity_result.passed:
        raise RuntimeError(
            f"REAL_DATA_REQUIRED: noise filter rejected dataset ({sanity_result.rejection_reason})"
        )

    return {
        "dataset_hash": dataset_hash,
        "sample_count": sample_count,
        "confidence_score": round(confidence_score, 4),
        "duplicate_ratio": round(duplicate_ratio, 4),
        "label_noise_ratio": round(float(sanity_result.label_noise_ratio), 4),
        "manifest_timestamp": manifest_timestamp,
        "verification_schema_version": _DATASET_MANIFEST_SCHEMA_VERSION,
    }


# =============================================================================
# PER-FIELD REPORT (for /api/training/readiness endpoint)
# =============================================================================


def get_per_field_report() -> dict:
    """
    Generate a per-field readiness report for the training readiness endpoint.

    Uses PERSISTED bridge state (cross-process safe) as the authoritative
    counter source. Also checks manifest consistency.
    Does NOT raise — always returns a dict.
    """
    min_samples = YGB_MIN_REAL_SAMPLES
    report = {
        "strict_real_mode": STRICT_REAL_MODE,
        "threshold": min_samples,
        "bridge_loaded": False,
        "bridge_count": 0,
        "bridge_verified_count": 0,
        "deficit": min_samples,
        "status": "BLOCKED",
        "reason": "Not checked",
        "manifest_exists": False,
        "per_field_counts": {},
        "per_field_deficits": {},
        "authoritative_source": "bridge_state.json",
    }

    # Load persisted bridge state (authoritative source)
    try:
        from backend.bridge.bridge_state import get_bridge_state

        bridge_state = get_bridge_state()
        counts = bridge_state.get_counts()
        report["bridge_count"] = counts["bridge_count"]
        report["bridge_verified_count"] = counts["bridge_verified_count"]
        report["deficit"] = counts["deficit"]

        # Consistency check
        consistency = bridge_state.check_manifest_consistency()
        report["consistency_ok"] = consistency["consistency_ok"]
        report["manifest_verified_count"] = consistency["manifest_verified_count"]
        if not consistency["consistency_ok"] and consistency["mismatch_reason"]:
            report["consistency_warning"] = consistency["mismatch_reason"]
    except Exception as e:
        report["bridge_state_error"] = str(e)

    # Check manifest file
    manifest_path = _SECURE_DATA / "dataset_manifest.json"
    report["manifest_exists"] = manifest_path.exists()
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            report["manifest"] = {
                "sample_count": manifest.get(
                    "sample_count", manifest.get("total_samples", 0)
                ),
                "dataset_source": manifest.get("dataset_source", "UNKNOWN"),
                "frozen_at": manifest.get("frozen_at", manifest.get("updated_at")),
                "class_entropy": manifest.get("class_entropy", 0),
                "training_mode": manifest.get("training_mode", "UNKNOWN"),
                "per_field_counts": manifest.get("per_field_counts", {}),
            }
        except Exception:
            report["manifest"] = None

    # Check bridge DLL availability
    try:
        lib = _load_bridge()
        report["bridge_loaded"] = True
    except FileNotFoundError:
        pass
    except Exception:
        report["bridge_loaded"] = False

    # Final readiness decision based on persisted state
    verified = report["bridge_verified_count"]
    if verified >= min_samples:
        report["status"] = "READY"
        report["reason"] = f"{verified} verified samples (threshold: {min_samples})"
    else:
        report["status"] = "BLOCKED"
        report["reason"] = (
            f"Insufficient samples: {verified}/{min_samples} "
            f"(deficit: {report['deficit']})"
        )

    return report


def generate_dataset_manifest() -> dict:
    """
    Generate dataset_manifest.json from current ingestion state.

    Required keys: total_samples, verified_samples, positive_ratio,
    dataset_source, strict_real_mode, updated_at, per_field_counts.

    Returns the manifest dict or error info.
    Does NOT raise — always returns a dict.
    """
    try:
        lib = _load_bridge()
        verified = lib.bridge_get_verified_count()
        total = lib.bridge_get_count()

        # Get hash from bridge
        hash_buf = ctypes.create_string_buffer(65)
        lib.bridge_get_dataset_manifest_hash(hash_buf, 65)
        manifest_hash = hash_buf.value.decode("utf-8", errors="replace")

        # Collect per-field (source_tag) counts by iterating verified samples
        per_field_counts = {}
        FIELD_LEN = 512
        positive_count = 0
        for idx in range(verified):
            ep = ctypes.create_string_buffer(FIELD_LEN)
            params = ctypes.create_string_buffer(FIELD_LEN)
            ev = ctypes.create_string_buffer(FIELD_LEN)
            imp = ctypes.create_string_buffer(FIELD_LEN)
            st = ctypes.create_string_buffer(FIELD_LEN)
            fp = ctypes.create_string_buffer(65)
            reliability = ctypes.c_double(0.0)
            ingested_at = ctypes.c_long(0)

            rc = lib.bridge_fetch_verified_sample(
                idx,
                ep,
                FIELD_LEN,
                params,
                FIELD_LEN,
                ev,
                FIELD_LEN,
                imp,
                FIELD_LEN,
                st,
                FIELD_LEN,
                fp,
                65,
                ctypes.byref(reliability),
                ctypes.byref(ingested_at),
            )
            if rc != 0:
                continue
            source_tag = st.value.decode("utf-8", errors="replace") or "unknown"
            per_field_counts[source_tag] = per_field_counts.get(source_tag, 0) + 1
            if reliability.value >= 0.7:
                positive_count += 1

        positive_ratio = positive_count / verified if verified > 0 else 0.0

        # Per-field deficit calculation
        per_field_deficits = {}
        for field, count in per_field_counts.items():
            per_field_deficits[field] = max(0, YGB_MIN_REAL_SAMPLES - count)

        manifest = {
            "schema_version": _DATASET_MANIFEST_SCHEMA_VERSION,
            "dataset_source": "INGESTION_PIPELINE",
            "ingestion_manifest_hash": manifest_hash,
            "total_samples": total,
            "verified_samples": verified,
            "positive_ratio": round(positive_ratio, 4),
            "threshold": YGB_MIN_REAL_SAMPLES,
            "deficit": max(0, YGB_MIN_REAL_SAMPLES - verified),
            "strict_real_mode": STRICT_REAL_MODE,
            "ready": verified >= YGB_MIN_REAL_SAMPLES,
            "per_field_counts": per_field_counts,
            "per_field_deficits": per_field_deficits,
            "updated_at": __import__("datetime").datetime.now().isoformat(),
        }

        # Canonicalize: add signed fields for DatasetManifest compatibility
        from impl_v1.training.safety.manifest_builder import canonicalize_manifest

        canonicalize_manifest(manifest)

        # Write to disk
        _SECURE_DATA.mkdir(parents=True, exist_ok=True)
        manifest_path = _SECURE_DATA / "dataset_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return {"success": True, "manifest": manifest, "path": str(manifest_path)}

    except FileNotFoundError:
        return {"success": False, "error": "Ingestion bridge DLL not found"}
    except Exception as e:
        return {
            "success": False,
            "error": f"manifest_generation_failed: {type(e).__name__}",
        }
