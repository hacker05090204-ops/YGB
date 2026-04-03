"""
manifest_builder.py — Canonical Dataset Manifest Normalizer

Ensures every manifest writer produces a superset schema that includes
the six signed fields required by DatasetManifest:
  dataset_hash, signed_by, version, total_samples, created_at, signature_hash

Legacy keys (sample_count, verified_samples, tensor_hash, accepted, etc.)
are preserved for backward compatibility.
"""

import hashlib
import os
import time
from typing import Dict, Any


_DEFAULT_VERSION = "1.0"
_SCHEMA_VERSION = 1


def _get_authority_key(explicit_key: str | None) -> str:
    auth_key = (explicit_key or os.environ.get("YGB_AUTHORITY_KEY", "")).strip()
    if not auth_key:
        raise RuntimeError(
            "REAL_DATA_REQUIRED: YGB_AUTHORITY_KEY must be set before manifest canonicalization"
        )
    return auth_key


def canonicalize_manifest(
    manifest: Dict[str, Any],
    authority_key: str | None = None,
    version: str | None = None,
) -> Dict[str, Any]:
    """
    Normalize a legacy manifest dict so it contains all six signed fields
    required by DatasetManifest, while preserving every existing key.

    Parameters
    ----------
    manifest : dict
        Raw manifest dict produced by any writer (may have legacy-only keys).
    authority_key : str, optional
        Signing authority key.  Must be provided directly or via YGB_AUTHORITY_KEY.
    version : str, optional
        Dataset version string.  Falls back to "1.0".

    Returns
    -------
    dict
        The same dict (mutated in-place AND returned) with signed keys added.
    """
    auth_key = _get_authority_key(authority_key)
    ver = version or manifest.get("version", _DEFAULT_VERSION)

    manifest.setdefault("schema_version", _SCHEMA_VERSION)

    # --- dataset_hash -----------------------------------------------------------
    # Prefer tensor_hash (most precise), then ingestion_manifest_hash, then compute
    dataset_hash = manifest.get("dataset_hash")
    if not dataset_hash:
        dataset_hash = manifest.get("tensor_hash")
    if not dataset_hash:
        dataset_hash = manifest.get("ingestion_manifest_hash")
    if not dataset_hash:
        raise RuntimeError(
            "REAL_DATA_REQUIRED: dataset_hash, tensor_hash, or ingestion_manifest_hash is required"
        )

    # --- signed_by ---------------------------------------------------------------
    signed_by = manifest.get("signed_by")
    if not signed_by or len(signed_by) != 64:
        signed_by = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

    # --- total_samples -----------------------------------------------------------
    total_samples = manifest.get("total_samples")
    if total_samples is None:
        total_samples = manifest.get("sample_count", 0)
    if total_samples is None:
        total_samples = manifest.get("verified_samples", 0)

    # Also backfill sample_count for legacy readers
    if "sample_count" not in manifest and total_samples:
        manifest["sample_count"] = total_samples

    # --- created_at --------------------------------------------------------------
    created_at = manifest.get("created_at")
    if not created_at:
        created_at = manifest.get("frozen_at") or manifest.get("updated_at")
    if not created_at:
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # --- signature_hash ----------------------------------------------------------
    sig_input = f"{dataset_hash}|{signed_by}|{ver}"
    signature_hash = hashlib.sha256(sig_input.encode("utf-8")).hexdigest()

    # Write the six canonical keys
    manifest["dataset_hash"] = dataset_hash
    manifest["signed_by"] = signed_by
    manifest["version"] = ver
    manifest["total_samples"] = total_samples
    manifest["created_at"] = created_at
    manifest["signature_hash"] = signature_hash

    return manifest
