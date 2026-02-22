"""
wipe_protection.py — SSD Wipe Protection (Phase 6)

If no local weights found:
1. Auto restore from Git snapshot
2. Validate model hash
3. Continue cluster mode
"""

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join('secure_data', 'model_versions')
SNAPSHOT_BRANCH = "main"


@dataclass
class RestoreResult:
    """Result of wipe protection restore."""
    weights_found: bool
    restored_from_git: bool
    hash_valid: bool
    version_id: str
    weight_hash: str
    error: str = ""


def check_local_weights(model_dir: str = MODEL_DIR) -> bool:
    """Check if local model weights exist."""
    if not os.path.exists(model_dir):
        return False

    for d in os.listdir(model_dir):
        weights_path = os.path.join(model_dir, d, "model_fp16.pt")
        if os.path.exists(weights_path):
            return True

    return False


def restore_from_git(
    repo_dir: str = ".",
    model_dir: str = MODEL_DIR,
    branch: str = SNAPSHOT_BRANCH,
) -> Tuple[bool, str]:
    """Attempt to restore model weights from Git.

    Checks out latest model version files from the specified branch.

    Returns:
        (success, message)
    """
    try:
        # Fetch latest
        subprocess.run(
            ['git', 'fetch', 'origin', branch],
            cwd=repo_dir, capture_output=True, timeout=30,
        )

        # Check if model_versions exist in git
        result = subprocess.run(
            ['git', 'ls-tree', '-r', '--name-only',
             f'origin/{branch}', '--', 'secure_data/model_versions/'],
            cwd=repo_dir, capture_output=True, text=True, timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return False, "No model weights in Git repository"

        # Checkout model files
        files = result.stdout.strip().split('\n')
        for f in files:
            subprocess.run(
                ['git', 'checkout', f'origin/{branch}', '--', f],
                cwd=repo_dir, capture_output=True, timeout=10,
            )

        logger.info(f"[WIPE_PROTECT] Restored {len(files)} files from Git")
        return True, f"Restored {len(files)} files"

    except Exception as e:
        return False, f"Git restore failed: {e}"


def validate_weight_hash(
    weights_path: str,
    expected_hash: str = "",
) -> Tuple[bool, str]:
    """Validate model weight file integrity.

    If expected_hash is empty, just compute the hash.
    """
    try:
        import torch
        state_dict = torch.load(weights_path, map_location='cpu',
                                weights_only=True)

        h = hashlib.sha256()
        for k in sorted(state_dict.keys()):
            h.update(state_dict[k].numpy().tobytes())
        actual_hash = h.hexdigest()

        if expected_hash and actual_hash != expected_hash:
            return False, (
                f"Hash mismatch: {actual_hash[:16]} != {expected_hash[:16]}"
            )

        return True, actual_hash

    except Exception as e:
        return False, f"Validation error: {e}"


def run_wipe_protection(
    repo_dir: str = ".",
    model_dir: str = MODEL_DIR,
) -> RestoreResult:
    """Full wipe protection sequence.

    1. Check if local weights exist
    2. If not, restore from Git
    3. Validate hash
    """
    # Step 1: Check local
    found = check_local_weights(model_dir)

    if found:
        logger.info("[WIPE_PROTECT] Local weights intact")
        return RestoreResult(
            weights_found=True,
            restored_from_git=False,
            hash_valid=True,
            version_id="local",
            weight_hash="",
        )

    logger.warning("[WIPE_PROTECT] No local weights — attempting restore")

    # Step 2: Restore from Git
    restored, msg = restore_from_git(repo_dir, model_dir)

    if not restored:
        logger.error(f"[WIPE_PROTECT] Restore failed: {msg}")
        return RestoreResult(
            weights_found=False,
            restored_from_git=False,
            hash_valid=False,
            version_id="",
            weight_hash="",
            error=msg,
        )

    # Step 3: Validate
    version_id = ""
    weight_hash = ""
    hash_valid = False

    if os.path.exists(model_dir):
        for d in sorted(os.listdir(model_dir)):
            weights_path = os.path.join(model_dir, d, "model_fp16.pt")
            meta_path = os.path.join(model_dir, d, "metadata.json")
            if os.path.exists(weights_path):
                expected = ""
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                    expected = meta.get('merged_weight_hash', '')
                    version_id = meta.get('version_id', d)

                valid, result = validate_weight_hash(weights_path, expected)
                hash_valid = valid
                weight_hash = result if valid else ""
                break

    logger.info(
        f"[WIPE_PROTECT] Restore complete: "
        f"version={version_id}, valid={hash_valid}"
    )

    return RestoreResult(
        weights_found=True,
        restored_from_git=True,
        hash_valid=hash_valid,
        version_id=version_id,
        weight_hash=weight_hash,
    )
