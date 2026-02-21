"""
dataset_manifest.py — Signed Dataset Manifest Hard Guarantee

Requires dataset_manifest.json:
{
  "dataset_hash": "...",
  "signed_by": authority_key_hash,
  "version": "...",
  "total_samples": N,
  "created_at": "..."
}

If missing or invalid → block training.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

MANIFEST_PATH = os.path.join('secure_data', 'dataset_manifest.json')


@dataclass
class DatasetManifest:
    """Signed dataset manifest."""
    dataset_hash: str
    signed_by: str       # SHA-256 of authority key
    version: str
    total_samples: int
    created_at: str
    signature_hash: str  # SHA-256 of (dataset_hash + signed_by + version)


def create_manifest(
    dataset_hash: str,
    authority_key: str,
    version: str,
    total_samples: int,
    path: str = MANIFEST_PATH,
) -> DatasetManifest:
    """Create and save a signed dataset manifest.

    Args:
        dataset_hash: SHA-256 hash of the dataset.
        authority_key: Authority signing key.
        version: Dataset version string.
        total_samples: Number of samples.
        path: Save path.

    Returns:
        Created DatasetManifest.
    """
    signed_by = hashlib.sha256(authority_key.encode('utf-8')).hexdigest()
    sig_input = f"{dataset_hash}|{signed_by}|{version}"
    signature_hash = hashlib.sha256(sig_input.encode('utf-8')).hexdigest()

    manifest = DatasetManifest(
        dataset_hash=dataset_hash,
        signed_by=signed_by,
        version=version,
        total_samples=total_samples,
        created_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        signature_hash=signature_hash,
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(asdict(manifest), f, indent=2)

    logger.info(f"[MANIFEST] Created: hash={dataset_hash[:16]}..., version={version}")
    return manifest


def validate_manifest(
    expected_dataset_hash: str = None,
    path: str = MANIFEST_PATH,
) -> Tuple[bool, str, Optional[DatasetManifest]]:
    """Validate dataset manifest before training.

    Args:
        expected_dataset_hash: Expected hash to verify against (optional).
        path: Manifest file path.

    Returns:
        Tuple of (valid, reason, manifest_or_None).
    """
    # Check existence
    if not os.path.exists(path):
        logger.error("[MANIFEST] BLOCKED: dataset_manifest.json missing")
        return False, "manifest_missing", None

    # Load
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        manifest = DatasetManifest(**data)
    except Exception as e:
        logger.error(f"[MANIFEST] BLOCKED: invalid manifest format — {e}")
        return False, "invalid_format", None

    # Verify signature integrity
    sig_input = f"{manifest.dataset_hash}|{manifest.signed_by}|{manifest.version}"
    expected_sig = hashlib.sha256(sig_input.encode('utf-8')).hexdigest()

    if manifest.signature_hash != expected_sig:
        logger.error("[MANIFEST] BLOCKED: signature verification failed")
        return False, "signature_invalid", None

    # Verify dataset hash if expected is provided
    if expected_dataset_hash and manifest.dataset_hash != expected_dataset_hash:
        logger.error(
            f"[MANIFEST] BLOCKED: dataset hash mismatch "
            f"(manifest={manifest.dataset_hash[:16]}... vs "
            f"expected={expected_dataset_hash[:16]}...)"
        )
        return False, "dataset_hash_mismatch", None

    # Verify signed_by is not empty
    if not manifest.signed_by or len(manifest.signed_by) != 64:
        logger.error("[MANIFEST] BLOCKED: invalid authority signature")
        return False, "no_authority", None

    logger.info(
        f"[MANIFEST] VALID: hash={manifest.dataset_hash[:16]}..., "
        f"version={manifest.version}, signed_by={manifest.signed_by[:16]}..."
    )
    return True, "valid", manifest
