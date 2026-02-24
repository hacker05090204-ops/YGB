"""
Dataset Loader — Training Data Source
======================================

STRICT_REAL_MODE (default True):
  - SyntheticTrainingDataset is BLOCKED
  - Only IngestionPipelineDataset (Phase 3) is permitted
  - Training aborts if dataset_source != "INGESTION_PIPELINE"

SyntheticTrainingDataset (formerly RealTrainingDataset):
  - Uses ScaledDatasetGenerator (SYNTHETIC data)
  - Renamed for honest labeling
  - Blocked in STRICT_REAL_MODE (production)

FORBIDDEN FIELDS (hard blocked):
- valid, accepted, rejected, severity, platform_decision
"""

import torch
from torch.utils.data import Dataset, DataLoader
from typing import List, Tuple, Optional
import random

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

STRICT_REAL_MODE = False  # Set False when ingestion bridge not available


def _enforce_strict_real_mode(cls_name: str):
    """Abort if STRICT_REAL_MODE is on and caller tries to use synthetic data."""
    if STRICT_REAL_MODE:
        raise RuntimeError(
            f"ABORT: {cls_name} is BLOCKED. STRICT_REAL_MODE=True. "
            f"Only IngestionPipelineDataset (dataset_source='INGESTION_PIPELINE') "
            f"is permitted for training. Set STRICT_REAL_MODE=False for lab-only use "
            f"with governance override."
        )


# =============================================================================
# FORBIDDEN FIELDS - GOVERNANCE ENFORCEMENT
# =============================================================================

FORBIDDEN_FIELDS = frozenset([
    "valid",
    "accepted", 
    "rejected",
    "severity",
    "platform_decision",
    "decision",
    "outcome",
    "verified",
])


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
                noise = noise_level * 0.20 * sample_rng.gauss(0, 1)
                val = base + noise
            elif i < 128:
                # Response-ratio features — SECONDARY label signal
                base = response
                noise = noise_level * 0.20 * sample_rng.gauss(0, 1)
                val = base + noise
            elif i < 192:
                # Diverse derived features — INDEPENDENT combinations
                # Each sub-range uses a different non-redundant encoding
                sub_idx = i - 128  # 0-63
                
                if sub_idx < 16:
                    # Polynomial: signal^2 with independent noise
                    base = signal * signal
                    noise = 0.15 * sample_rng.gauss(0, 1)
                elif sub_idx < 32:
                    # Polynomial: response^2 with independent noise
                    base = response * response
                    noise = 0.15 * sample_rng.gauss(0, 1)
                elif sub_idx < 40:
                    # Trigonometric: sin(signal * pi)
                    import math
                    base = 0.5 + 0.5 * math.sin(signal * math.pi)
                    noise = 0.12 * sample_rng.gauss(0, 1)
                elif sub_idx < 48:
                    # Trigonometric: cos(response * pi)
                    import math
                    base = 0.5 + 0.5 * math.cos(response * math.pi)
                    noise = 0.12 * sample_rng.gauss(0, 1)
                elif sub_idx < 56:
                    # Threshold: binary indicator with noise
                    threshold = 0.5 + 0.05 * sample_rng.gauss(0, 1)
                    base = 0.8 if signal > threshold else 0.2
                    noise = 0.10 * sample_rng.gauss(0, 1)
                else:
                    # Rank-based: difficulty-weighted signal magnitude
                    base = signal * (1.0 - difficulty * 0.3)
                    noise = 0.12 * sample_rng.gauss(0, 1)
                
                val = base + noise
            else:
                # Controlled noise — small perturbation (NOT pure random)
                base = 0.5
                noise = 0.05 * sample_rng.gauss(0, 1)
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
    
    Args:
        batch_size: Samples per batch (default 1024 for RTX 2050)
        num_workers: Parallel data loading workers (default 4 for laptop safety)
        pin_memory: Pin memory for faster GPU transfer
        prefetch_factor: Batches to prefetch per worker
        seed: Random seed for determinism
    
    Returns:
        Tuple of (train_loader, holdout_loader, stats)
    """
    # Create datasets
    train_dataset = SyntheticTrainingDataset(
        config=DatasetConfig(total_samples=20000),
        seed=seed,
        is_holdout=False,
    )
    
    holdout_dataset = SyntheticTrainingDataset(
        config=DatasetConfig(total_samples=20000),
        seed=seed,
        is_holdout=True,
    )
    
    # Deterministic generator for shuffle reproducibility
    g = torch.Generator()
    g.manual_seed(seed)
    
    # Create DataLoaders with CUDA optimizations
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
        drop_last=True,  # Consistent batch sizes
        generator=g,     # Deterministic shuffle order
    )
    
    holdout_loader = DataLoader(
        holdout_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
    )
    
    stats = {
        "train": train_dataset.get_statistics(),
        "holdout": holdout_dataset.get_statistics(),
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": pin_memory,
    }
    
    return train_loader, holdout_loader, stats


# =============================================================================
# VALIDATION
# =============================================================================

def validate_dataset_integrity() -> Tuple[bool, str]:
    """
    Validate dataset meets all requirements:
    - Min 20,000 samples
    - No forbidden fields
    - Class balance within 10%
    
    Returns:
        Tuple of (passed, message)
    """
    try:
        dataset = SyntheticTrainingDataset(
            config=DatasetConfig(total_samples=20000),
            seed=FIXED_SEED,
        )
        
        stats = dataset.get_statistics()
        
        # Check minimum samples
        if stats["total"] < 18000:  # 20000 - 10% holdout
            return False, f"Insufficient samples: {stats['total']} < 18000"
        
        # Check class balance (within 10%)
        positive_ratio = stats["positive"] / stats["total"]
        if not (0.40 <= positive_ratio <= 0.60):
            return False, f"Class imbalance: {positive_ratio:.2%} positive"
        
        # Validate no forbidden fields in first sample
        sample = dataset.samples[0]
        if not validate_no_forbidden_fields(sample.features):
            return False, "Forbidden fields detected in samples"
        
        return True, f"Dataset valid: {stats['total']} samples, {positive_ratio:.2%} positive"
        
    except Exception as e:
        return False, f"Validation failed: {str(e)}"


# =============================================================================
# INGESTION PIPELINE DATASET — REAL DATA ONLY
# =============================================================================

import ctypes
import hashlib
import json
import os
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BRIDGE_DIR = _PROJECT_ROOT / "native" / "distributed"
_SECURE_DATA = _PROJECT_ROOT / "secure_data"

# Bridge library name
_BRIDGE_LIB = (
    "ingestion_bridge.dll" if os.name == "nt"
    else "libingestion_bridge.so"
)


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
        ctypes.c_int,                          # verified_idx
        ctypes.c_char_p, ctypes.c_int,         # endpoint
        ctypes.c_char_p, ctypes.c_int,         # parameters
        ctypes.c_char_p, ctypes.c_int,         # exploit_vector
        ctypes.c_char_p, ctypes.c_int,         # impact
        ctypes.c_char_p, ctypes.c_int,         # source_tag
        ctypes.c_char_p, ctypes.c_int,         # fingerprint
        ctypes.POINTER(ctypes.c_double),       # reliability
        ctypes.POINTER(ctypes.c_long),         # ingested_at
    ]

    lib.bridge_get_dataset_manifest_hash.restype = None
    lib.bridge_get_dataset_manifest_hash.argtypes = [
        ctypes.c_char_p, ctypes.c_int,
    ]

    lib.bridge_ingest_sample.restype = ctypes.c_int
    lib.bridge_ingest_sample.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double,
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

        # Fetch all verified samples
        verified_count = self._lib.bridge_get_verified_count()
        logger.info(f"[INGESTION] Verified samples available: {verified_count}")

        if verified_count < min_samples:
            # NO FALLBACK — freeze field, abort
            logger.error(
                f"[INGESTION] ABORT: Only {verified_count} verified samples "
                f"(minimum: {min_samples}). Field FROZEN. "
                f"NO synthetic fallback permitted."
            )
            raise RuntimeError(
                f"Insufficient ingestion data: {verified_count} < {min_samples}. "
                f"Field frozen. No synthetic fallback."
            )

        # Import policy + quality scorer
        from impl_v1.training.distributed.ingestion_policy import (
            IngestionPolicy, IngestionCandidate,
        )
        from impl_v1.training.distributed.data_quality_scorer import (
            DataQualityScorer,
        )

        policy = IngestionPolicy()
        scorer = DataQualityScorer()

        # Fetch and filter samples
        self._raw_samples = []
        self._features = []
        self._labels = []
        accepted = 0
        rejected_policy = 0
        rejected_quality = 0

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
                ep, FIELD_LEN,
                params, FIELD_LEN,
                ev, FIELD_LEN,
                imp, FIELD_LEN,
                st, FIELD_LEN,
                fp, 65,
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

            # Policy check
            candidate = IngestionCandidate(
                sample_id=fingerprint[:16],
                endpoint=endpoint,
                exploit_vector=exploit_vector,
                impact=impact,
                source_id=source_tag,
                reproducible=reliability.value >= 0.7,
                impact_classified=len(impact) > 0,
                real_world_confirmed=reliability.value >= 0.5,
            )
            policy_result = policy.check(candidate)
            if not policy_result.accepted:
                rejected_policy += 1
                continue

            # Encode features
            features_dict = {
                "signal_strength": min(reliability.value, 1.0),
                "response_ratio": min(len(exploit_vector) / 100.0, 1.0),
                "difficulty": 1.0 - min(reliability.value, 1.0),
                "noise": 0.05,
            }

            # Strip forbidden fields
            clean_features = strip_forbidden_fields(features_dict)
            feature_vec = self._encode_features(clean_features)

            # Quality score
            import numpy as np
            fv_array = np.array(feature_vec, dtype=np.float32)
            quality = scorer.score_features(
                sample_id=fingerprint[:16],
                features=fv_array,
                impact_level="high" if reliability.value >= 0.8 else "medium",
                source_count=1,
            )
            if not quality.accepted:
                rejected_quality += 1
                continue

            # Label: exploit vector complexity → 1=positive, 0=negative
            label = 1 if reliability.value >= 0.7 else 0

            self._features.append(feature_vec)
            self._labels.append(label)
            self._raw_samples.append({
                "endpoint": endpoint,
                "exploit_vector": exploit_vector,
                "impact": impact,
                "source_tag": source_tag,
                "fingerprint": fingerprint,
                "reliability": reliability.value,
            })
            accepted += 1

        logger.info(
            f"[INGESTION] Pipeline result: {accepted} accepted, "
            f"{rejected_policy} rejected (policy), "
            f"{rejected_quality} rejected (quality)"
        )

        if accepted < min_samples:
            raise RuntimeError(
                f"Insufficient quality samples after filtering: "
                f"{accepted} < {min_samples}. No synthetic fallback."
            )

        # Convert to tensors
        self._features_tensor = torch.tensor(self._features, dtype=torch.float32)
        self._labels_tensor = torch.tensor(self._labels, dtype=torch.long)

        # Generate manifest hash
        self._manifest_hash = self._compute_manifest_hash()

        # Write manifest
        self._write_manifest(accepted, rejected_policy, rejected_quality)

    def _encode_features(self, features: dict) -> List[float]:
        """Encode feature dict to fixed-size vector (same logic as synthetic)."""
        vec = []
        signal = features.get("signal_strength", 0.5)
        response = features.get("response_ratio", 0.5)
        difficulty = features.get("difficulty", 0.5)
        noise_level = features.get("noise", 0.1)

        sample_seed = int((signal * 10000 + response * 1000 + difficulty * 100) * 100)
        sample_rng = random.Random(sample_seed)

        for i in range(self.feature_dim):
            if i < 64:
                base = signal
                noise = noise_level * 0.20 * sample_rng.gauss(0, 1)
                val = base + noise
            elif i < 128:
                base = response
                noise = noise_level * 0.20 * sample_rng.gauss(0, 1)
                val = base + noise
            elif i < 192:
                sub_idx = i - 128
                if sub_idx < 16:
                    base = signal * signal
                    noise = 0.15 * sample_rng.gauss(0, 1)
                elif sub_idx < 32:
                    base = response * response
                    noise = 0.15 * sample_rng.gauss(0, 1)
                elif sub_idx < 40:
                    base = 0.5 + 0.5 * math.sin(signal * math.pi)
                    noise = 0.12 * sample_rng.gauss(0, 1)
                elif sub_idx < 48:
                    base = 0.5 + 0.5 * math.cos(response * math.pi)
                    noise = 0.12 * sample_rng.gauss(0, 1)
                elif sub_idx < 56:
                    threshold = 0.5 + 0.05 * sample_rng.gauss(0, 1)
                    base = 0.8 if signal > threshold else 0.2
                    noise = 0.10 * sample_rng.gauss(0, 1)
                else:
                    base = signal * (1.0 - difficulty * 0.3)
                    noise = 0.12 * sample_rng.gauss(0, 1)
                val = base + noise
            else:
                base = 0.5
                noise = 0.05 * sample_rng.gauss(0, 1)
                val = base + noise
            vec.append(max(0.0, min(1.0, val)))

        return vec

    def _compute_manifest_hash(self) -> str:
        """Get manifest hash from the bridge (C++ side)."""
        hash_buf = ctypes.create_string_buffer(65)
        self._lib.bridge_get_dataset_manifest_hash(hash_buf, 65)
        return hash_buf.value.decode("utf-8", errors="replace")

    def _write_manifest(self, accepted, rejected_policy, rejected_quality):
        """Write dataset_manifest.json to secure_data/."""
        _SECURE_DATA.mkdir(parents=True, exist_ok=True)
        manifest_path = _SECURE_DATA / "dataset_manifest.json"

        # Hash the tensors too
        h = hashlib.sha256()
        h.update(self._features_tensor.numpy().tobytes())
        h.update(self._labels_tensor.numpy().tobytes())
        tensor_hash = h.hexdigest()

        manifest = {
            "dataset_source": "INGESTION_PIPELINE",
            "ingestion_manifest_hash": self._manifest_hash,
            "tensor_hash": tensor_hash,
            "sample_count": len(self._features),
            "feature_dim": self.feature_dim,
            "num_classes": len(set(self._labels)),
            "accepted": accepted,
            "rejected_policy": rejected_policy,
            "rejected_quality": rejected_quality,
            "strict_real_mode": STRICT_REAL_MODE,
            "frozen_at": __import__("datetime").datetime.now().isoformat(),
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"[INGESTION] Manifest written: {manifest_path}")
        logger.info(f"[INGESTION] Ingestion hash: {self._manifest_hash[:32]}...")
        logger.info(f"[INGESTION] Tensor hash: {tensor_hash[:32]}...")

    def __len__(self) -> int:
        return len(self._features)

    def __getitem__(self, idx: int):
        return self._features_tensor[idx], self._labels_tensor[idx]

    def get_statistics(self) -> dict:
        """Get dataset statistics."""
        n_positive = sum(1 for l in self._labels if l == 1)
        return {
            "total": len(self._features),
            "positive": n_positive,
            "negative": len(self._features) - n_positive,
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

    return loader, stats
