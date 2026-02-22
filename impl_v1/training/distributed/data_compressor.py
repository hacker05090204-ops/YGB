"""
data_compressor.py — Data Compressor (Phase 3)

Converts raw dataset to compressed feature format:
1. Feature tensor extraction
2. Dedup via content hash
3. Compressed storage (zlib fallback if zstd unavailable)
4. Raw file removal after compression
"""

import gzip
import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

COMPRESSED_DIR = os.path.join('secure_data', 'compressed_features')


@dataclass
class CompressionResult:
    """Result of data compression."""
    original_size_mb: float
    compressed_size_mb: float
    compression_ratio: float
    num_samples: int
    num_features: int
    unique_samples: int
    duplicate_samples: int
    dedup_ratio: float
    output_path: str
    dataset_hash: str
    timestamp: str = ""


def compute_sample_hash(row: np.ndarray) -> str:
    """Hash a single sample row."""
    return hashlib.md5(row.tobytes()).hexdigest()


def deduplicate_dataset(
    X: np.ndarray,
    y: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, int]:
    """Remove duplicate samples via hash.

    Returns:
        (X_unique, y_unique, num_duplicates)
    """
    seen = set()
    keep = []

    for i in range(len(X)):
        h = compute_sample_hash(X[i])
        if h not in seen:
            seen.add(h)
            keep.append(i)

    dupes = len(X) - len(keep)

    if dupes > 0:
        X_unique = X[keep]
        y_unique = y[keep]
        logger.info(
            f"[COMPRESSOR] Dedup: {dupes} duplicates removed, "
            f"{len(keep)} unique samples"
        )
    else:
        X_unique = X
        y_unique = y
        logger.info("[COMPRESSOR] No duplicates found")

    return X_unique, y_unique, dupes


def compress_dataset(
    X: np.ndarray,
    y: np.ndarray,
    output_dir: str = COMPRESSED_DIR,
    deduplicate: bool = True,
) -> CompressionResult:
    """Compress dataset to gzipped numpy format.

    Steps:
    1. Deduplicate if enabled
    2. Save as compressed .npz
    3. Compute hash
    4. Return stats

    Args:
        X: Feature array (N, D)
        y: Label array (N,)
        output_dir: Output directory
        deduplicate: Whether to remove duplicates

    Returns:
        CompressionResult
    """
    os.makedirs(output_dir, exist_ok=True)

    original_bytes = X.nbytes + y.nbytes
    original_mb = original_bytes / (1024 * 1024)

    # Dedup
    dupes = 0
    if deduplicate:
        X, y, dupes = deduplicate_dataset(X, y)

    # Hash
    h = hashlib.sha256()
    h.update(X.tobytes())
    h.update(y.tobytes())
    dataset_hash = h.hexdigest()

    # Save compressed
    output_path = os.path.join(output_dir, f"features_{dataset_hash[:16]}.npz")
    np.savez_compressed(output_path, X=X, y=y)

    compressed_bytes = os.path.getsize(output_path)
    compressed_mb = compressed_bytes / (1024 * 1024)
    ratio = original_mb / max(compressed_mb, 0.001)

    # Save metadata
    meta = {
        'dataset_hash': dataset_hash,
        'num_samples': len(X),
        'num_features': X.shape[1] if X.ndim > 1 else 1,
        'original_size_mb': round(original_mb, 4),
        'compressed_size_mb': round(compressed_mb, 4),
        'compression_ratio': round(ratio, 2),
        'duplicates_removed': dupes,
        'timestamp': datetime.now().isoformat(),
    }
    meta_path = output_path + '.meta.json'
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    result = CompressionResult(
        original_size_mb=round(original_mb, 4),
        compressed_size_mb=round(compressed_mb, 4),
        compression_ratio=round(ratio, 2),
        num_samples=len(X),
        num_features=X.shape[1] if X.ndim > 1 else 1,
        unique_samples=len(X),
        duplicate_samples=dupes,
        dedup_ratio=round(dupes / max(dupes + len(X), 1), 4),
        output_path=output_path,
        dataset_hash=dataset_hash,
        timestamp=datetime.now().isoformat(),
    )

    logger.info(
        f"[COMPRESSOR] Compressed: {original_mb:.2f}MB → {compressed_mb:.2f}MB "
        f"(ratio={ratio:.1f}x, dedup={dupes})"
    )

    return result


def load_compressed_dataset(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Load a compressed dataset."""
    data = np.load(path)
    return data['X'], data['y']


def remove_raw_files(paths: List[str]) -> int:
    """Remove raw intermediate files after compression."""
    removed = 0
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
            removed += 1
            logger.info(f"[COMPRESSOR] Removed raw: {p}")
    return removed
