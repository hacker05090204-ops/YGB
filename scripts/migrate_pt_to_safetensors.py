"""
migrate_pt_to_safetensors.py — Migration Script for .pt → .safetensors

Converts existing .pt checkpoints and model versions to .safetensors format.
Supports dry-run mode and generates a rollback log.

Usage:
    python scripts/migrate_pt_to_safetensors.py                   # Full migration
    python scripts/migrate_pt_to_safetensors.py --dry-run         # Preview only
    python scripts/migrate_pt_to_safetensors.py --rollback        # Undo migration
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from impl_v1.training.checkpoints.checkpoint_hardening import HardenedCheckpointManager

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_LOG_PATH = os.path.join(PROJECT_ROOT, "secure_data", "migration_log.json")
BACKUP_DIR = os.path.join(PROJECT_ROOT, "secure_data", "migration_backup")

SCAN_DIRS = [
    os.path.join(PROJECT_ROOT, "secure_data", "model_versions"),
    os.path.join(PROJECT_ROOT, "secure_data", "checkpoints"),
]

MAX_FILES = 10000  # Loop guard


def compute_file_hash(path: str) -> str:
    """SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_pt_files() -> List[str]:
    """Find all .pt files under scan dirs."""
    results = []
    for scan_dir in SCAN_DIRS:
        if not os.path.exists(scan_dir):
            continue
        count = 0
        for root, _dirs, files in os.walk(scan_dir):
            for fname in files:
                if fname.endswith(".pt"):
                    results.append(os.path.join(root, fname))
                    count += 1
                    if count >= MAX_FILES:
                        logger.warning(f"  ⚠ Hit MAX_FILES={MAX_FILES} limit in {scan_dir}")
                        break
            if count >= MAX_FILES:
                break
    return results


def convert_single(pt_path: str, dry_run: bool) -> Optional[Dict]:
    """Convert a single .pt file to .safetensors.

    Returns migration log entry or None on failure.
    """
    import torch
    from safetensors.torch import save_file as st_save_file

    st_path = pt_path.rsplit(".", 1)[0] + ".safetensors"
    entry = {
        "pt_path": pt_path,
        "st_path": st_path,
        "backup_path": "",
        "pt_hash": "",
        "st_hash": "",
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Hash original
        entry["pt_hash"] = compute_file_hash(pt_path)

        if dry_run:
            entry["status"] = "dry_run"
            logger.info(f"  [DRY-RUN] Would convert: {pt_path}")
            logger.info(f"            → {st_path}")
            return entry

        # Load state dict. Legacy `.pt` checkpoints may not yet have SHA-256
        # sidecars, so migration must be able to read them without the hardened
        # safetensors-era verification contract.
        state_dict = torch.load(str(pt_path), map_location="cpu", weights_only=True)

        if isinstance(state_dict, dict) and "state_dict" in state_dict and isinstance(state_dict["state_dict"], dict):
            state_dict = state_dict["state_dict"]

        # Ensure all values are tensors (safetensors requires this)
        tensor_dict = {}
        if not isinstance(state_dict, dict):
            entry["status"] = "skipped_non_mapping"
            logger.warning(f"  ⚠ Loaded checkpoint is not a mapping: {pt_path}")
            return entry

        for k, v in state_dict.items():
            if isinstance(v, torch.Tensor):
                tensor_dict[k] = v
            else:
                logger.warning(f"  ⚠ Skipping non-tensor key '{k}' (type={type(v).__name__})")

        if not tensor_dict:
            entry["status"] = "skipped_no_tensors"
            logger.warning(f"  ⚠ No tensors found in {pt_path}, skipping")
            return entry

        # Backup original
        os.makedirs(BACKUP_DIR, exist_ok=True)
        rel_path = os.path.relpath(pt_path, PROJECT_ROOT)
        backup_path = os.path.join(BACKUP_DIR, rel_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(pt_path, backup_path)
        entry["backup_path"] = backup_path

        # Save as safetensors (atomic)
        _tmp_st = st_path + ".tmp"
        try:
            # Compute tensor hash for metadata
            th = hashlib.sha256()
            for k in sorted(tensor_dict.keys()):
                th.update(tensor_dict[k].cpu().numpy().tobytes())

            st_save_file(tensor_dict, _tmp_st, metadata={
                "tensor_hash": th.hexdigest(),
                "migrated_from": os.path.basename(pt_path),
                "migration_timestamp": datetime.now().isoformat(),
            })
            os.replace(_tmp_st, st_path)
        except Exception:
            try:
                if os.path.exists(_tmp_st):
                    os.unlink(_tmp_st)
            except OSError as cleanup_exc:
                logger.warning(
                    "  ⚠ Failed to remove temporary safetensors file %s: %s",
                    _tmp_st,
                    cleanup_exc,
                    exc_info=True,
                )
            raise

        # Verify
        entry["st_hash"] = compute_file_hash(st_path)
        entry["status"] = "converted"
        logger.info(f"  ✓ Converted: {os.path.basename(pt_path)} → {os.path.basename(st_path)}")

        # Update metadata.json if sibling exists
        meta_path = os.path.join(os.path.dirname(pt_path), "metadata.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                meta["format"] = "safetensors"
                meta["migrated_at"] = datetime.now().isoformat()
                meta["file_hash"] = entry["st_hash"]
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)
                logger.info(f"  ✓ Updated metadata: {meta_path}")
            except Exception as e:
                logger.warning(f"  ⚠ Could not update metadata: {e}")

        return entry

    except Exception as e:
        entry["status"] = f"error: {e}"
        logger.error(f"  ✗ Failed: {pt_path} — {e}")
        return entry


def run_migration(dry_run: bool = False) -> Dict:
    """Run full migration."""
    logger.info("╔══════════════════════════════════════════════════╗")
    logger.info("║  .pt → .safetensors Migration                   ║")
    logger.info(f"║  Mode: {'DRY RUN' if dry_run else 'LIVE'}                                ║")
    logger.info("╚══════════════════════════════════════════════════╝")

    pt_files = find_pt_files()
    logger.info(f"\n  Found {len(pt_files)} .pt file(s) to migrate\n")

    if not pt_files:
        logger.info("  Nothing to migrate.")
        return {"status": "nothing_to_do", "files": []}

    entries = []
    t0 = time.monotonic()
    timeout = 3600  # 1 hour max

    for i, pt_path in enumerate(pt_files):
        elapsed = time.monotonic() - t0
        if elapsed > timeout:
            logger.warning(f"  ⚠ Timeout after {elapsed:.0f}s, stopping at file {i}/{len(pt_files)}")
            break
        entry = convert_single(pt_path, dry_run)
        if entry:
            entries.append(entry)

    # Save migration log
    log_data = {
        "migration_timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "total_files": len(pt_files),
        "converted": sum(1 for e in entries if e["status"] == "converted"),
        "dry_run_count": sum(1 for e in entries if e["status"] == "dry_run"),
        "errors": sum(1 for e in entries if e["status"].startswith("error")),
        "entries": entries,
    }

    os.makedirs(os.path.dirname(MIGRATION_LOG_PATH), exist_ok=True)
    with open(MIGRATION_LOG_PATH, "w") as f:
        json.dump(log_data, f, indent=2)

    logger.info(f"\n  Migration log: {MIGRATION_LOG_PATH}")
    logger.info(f"  Converted: {log_data['converted']}, Errors: {log_data['errors']}")

    return log_data


def run_rollback() -> Dict:
    """Rollback: restore .pt files from backup."""
    logger.info("╔══════════════════════════════════════════════════╗")
    logger.info("║  ROLLBACK — Restore .pt from Backup             ║")
    logger.info("╚══════════════════════════════════════════════════╝")

    if not os.path.exists(MIGRATION_LOG_PATH):
        logger.error("  ✗ No migration log found. Cannot rollback.")
        return {"status": "no_log"}

    with open(MIGRATION_LOG_PATH, "r") as f:
        log_data = json.load(f)

    restored = 0
    errors = 0

    for entry in log_data.get("entries", []):
        if entry["status"] != "converted":
            continue

        backup_path = entry.get("backup_path", "")
        pt_path = entry["pt_path"]

        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, pt_path)
                # Remove the .safetensors file
                st_path = entry["st_path"]
                if os.path.exists(st_path):
                    os.unlink(st_path)
                restored += 1
                logger.info(f"  ✓ Restored: {os.path.basename(pt_path)}")
            except Exception as e:
                errors += 1
                logger.error(f"  ✗ Failed to restore {pt_path}: {e}")
        else:
            errors += 1
            logger.error(f"  ✗ Backup not found for {pt_path}")

    logger.info(f"\n  Restored: {restored}, Errors: {errors}")
    return {"status": "rolled_back", "restored": restored, "errors": errors}


def main():
    parser = argparse.ArgumentParser(
        description="Migrate .pt checkpoints to .safetensors format",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--rollback", action="store_true", help="Restore .pt from backup")
    args = parser.parse_args()

    if args.rollback:
        run_rollback()
    else:
        run_migration(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
