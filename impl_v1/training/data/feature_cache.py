"""
feature_cache.py — SHA-256 Feature Cache for Training Acceleration

Pre-computes feature vectors once and caches them in HDF5 format.
Never recomputes features per epoch — loads from cache if hash matches.

Cache key: SHA256(dataset_config + seed + feature_dim)
Cache location: secure_data/feature_cache/{hash}.h5

Deterministic: Same config + seed always produces same cache.
"""

import hashlib
import json
import os
import time
import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
CACHE_DIR = os.path.join(PROJECT_ROOT, 'secure_data', 'feature_cache')


# =============================================================================
# HASH COMPUTATION
# =============================================================================

def compute_dataset_hash(
    total_samples: int = 20000,
    seed: int = 42,
    feature_dim: int = 256,
    extra_config: dict = None,
) -> str:
    """Compute SHA-256 hash of dataset configuration.
    
    Args:
        total_samples: Number of samples in dataset.
        seed: Random seed for reproducibility.
        feature_dim: Feature vector dimensionality.
        extra_config: Optional additional config dict.
    
    Returns:
        Hex string of SHA-256 hash (64 chars).
    """
    config = {
        'total_samples': total_samples,
        'seed': seed,
        'feature_dim': feature_dim,
    }
    if extra_config:
        config.update(extra_config)
    
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.sha256(config_str.encode('utf-8')).hexdigest()


# =============================================================================
# CACHE OPERATIONS
# =============================================================================

def _cache_path(dataset_hash: str) -> str:
    """Get cache file path for a given dataset hash."""
    return os.path.join(CACHE_DIR, f'{dataset_hash}.npz')


def cache_exists(dataset_hash: str) -> bool:
    """Check if cached feature vectors exist for the given config hash."""
    return os.path.exists(_cache_path(dataset_hash))


def save_to_cache(
    dataset_hash: str,
    features: np.ndarray,
    labels: np.ndarray,
    metadata: dict = None,
) -> str:
    """Save feature vectors to cache.
    
    Args:
        dataset_hash: SHA-256 hash of dataset config.
        features: Feature array (N, D).
        labels: Label array (N,).
        metadata: Optional metadata dict.
    
    Returns:
        Path to saved cache file.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(dataset_hash)
    
    save_dict = {
        'features': features,
        'labels': labels,
        'hash': np.array([dataset_hash], dtype='U64'),
        'created_at': np.array([time.time()]),
    }
    
    if metadata:
        save_dict['metadata'] = np.array([json.dumps(metadata)], dtype='U1024')
    
    np.savez_compressed(path, **save_dict)
    
    logger.info(
        f"[CACHE] Saved features to cache: {path} "
        f"({features.shape[0]} samples, {features.shape[1]} dims)"
    )
    return path


def load_from_cache(dataset_hash: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Load cached feature vectors.
    
    Args:
        dataset_hash: SHA-256 hash of dataset config.
    
    Returns:
        Tuple of (features, labels) or None if cache miss.
    """
    path = _cache_path(dataset_hash)
    if not os.path.exists(path):
        logger.info(f"[CACHE] Cache miss: {dataset_hash[:16]}...")
        return None
    
    try:
        data = np.load(path, allow_pickle=False)
        features = data['features']
        labels = data['labels']
        stored_hash = str(data['hash'][0])
        
        # Verify hash integrity
        if stored_hash != dataset_hash:
            logger.warning(f"[CACHE] Hash mismatch — invalidating cache")
            os.remove(path)
            return None
        
        logger.info(
            f"[CACHE] Cache hit: {dataset_hash[:16]}... "
            f"({features.shape[0]} samples, {features.shape[1]} dims)"
        )
        return features, labels
        
    except Exception as e:
        logger.warning(f"[CACHE] Failed to load cache: {e}")
        return None


def invalidate_cache(dataset_hash: str = None) -> int:
    """Invalidate cache entries.
    
    Args:
        dataset_hash: Specific hash to invalidate. If None, clears all.
    
    Returns:
        Number of cache files removed.
    """
    if not os.path.exists(CACHE_DIR):
        return 0
    
    count = 0
    if dataset_hash:
        path = _cache_path(dataset_hash)
        if os.path.exists(path):
            os.remove(path)
            count = 1
    else:
        for f in os.listdir(CACHE_DIR):
            if f.endswith('.npz'):
                os.remove(os.path.join(CACHE_DIR, f))
                count += 1
    
    logger.info(f"[CACHE] Invalidated {count} cache entries")
    return count


def get_or_compute_features(
    total_samples: int = 20000,
    seed: int = 42,
    feature_dim: int = 256,
) -> Tuple[np.ndarray, np.ndarray, str]:
    """Get features from cache or compute and cache them.
    
    Args:
        total_samples: Number of dataset samples.
        seed: Random seed.
        feature_dim: Feature vector dimensionality.
    
    Returns:
        Tuple of (features, labels, dataset_hash).
    """
    dataset_hash = compute_dataset_hash(total_samples, seed, feature_dim)
    
    # Check cache
    cached = load_from_cache(dataset_hash)
    if cached is not None:
        return cached[0], cached[1], dataset_hash
    
    # Compute features
    logger.info(f"[CACHE] Computing features ({total_samples} samples)...")
    start = time.perf_counter()
    
    try:
        from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
        from impl_v1.training.data.scaled_dataset import DatasetConfig
        
        dataset = RealTrainingDataset(
            config=DatasetConfig(total_samples=total_samples),
            seed=seed,
            feature_dim=feature_dim,
            is_holdout=False,
        )
        
        features = np.zeros((len(dataset), feature_dim), dtype=np.float32)
        labels = np.zeros(len(dataset), dtype=np.int64)
        
        for i in range(len(dataset)):
            feat, lbl = dataset[i]
            features[i] = feat.numpy() if hasattr(feat, 'numpy') else feat
            labels[i] = lbl.item() if hasattr(lbl, 'item') else lbl
        
        elapsed = time.perf_counter() - start
        logger.info(f"[CACHE] Computed features in {elapsed:.2f}s")
        
    except ImportError:
        # Fallback: synthetic for testing
        logger.warning("[CACHE] Dataset not available, using synthetic data")
        rng = np.random.RandomState(seed)
        features = rng.randn(total_samples, feature_dim).astype(np.float32)
        labels = rng.randint(0, 2, total_samples).astype(np.int64)
    
    # Save to cache
    save_to_cache(dataset_hash, features, labels, {
        'total_samples': total_samples,
        'seed': seed,
        'feature_dim': feature_dim,
    })
    
    return features, labels, dataset_hash
