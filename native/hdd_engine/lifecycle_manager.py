"""
Lifecycle Manager
=================

Manages entity lifecycle states with enforced rules.

States:
    CREATED → ACTIVE → COMPLETED → BACKED_UP → MARKED_FOR_DELETION → DELETED

Deletion guards:
    - status == COMPLETED or BACKED_UP
    - age >= 30 days
    - backup_verified == True
    - integrity_verified == True
    - legal_hold == False

Includes daily sweep thread for auto-deletion.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .hdd_engine import (
    HDDEngine,
    LifecycleState,
    ENTITY_TYPES,
    META_EXT,
    _atomic_write,
    _file_lock_acquire,
    _file_lock_release,
)
from .secure_wiper import secure_wipe_entity

logger = logging.getLogger("lifecycle_manager")

# Deletion age threshold
DELETION_AGE_DAYS = 30

# Daily sweep interval (seconds)
SWEEP_INTERVAL_SECONDS = 86400  # 24 hours

# Valid state transitions
VALID_TRANSITIONS = {
    LifecycleState.CREATED: [LifecycleState.ACTIVE],
    LifecycleState.ACTIVE: [LifecycleState.COMPLETED],
    LifecycleState.COMPLETED: [LifecycleState.BACKED_UP, LifecycleState.MARKED_FOR_DELETION],
    LifecycleState.BACKED_UP: [LifecycleState.MARKED_FOR_DELETION],
    LifecycleState.MARKED_FOR_DELETION: [LifecycleState.DELETED],
    LifecycleState.DELETED: [],  # Terminal state
}


class LifecycleManager:
    """
    Manages entity lifecycle with enforced deletion guards.
    """

    def __init__(self, engine: HDDEngine):
        self._engine = engine
        self._sweep_thread: Optional[threading.Thread] = None
        self._running = False

    def transition(
        self,
        entity_type: str,
        entity_id: str,
        new_state: LifecycleState,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Transition an entity to a new lifecycle state.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            new_state: Target lifecycle state
            force: If True, skip guard checks (admin override)

        Returns:
            Result dict with success/failure info
        """
        meta = self._engine.read_metadata(entity_type, entity_id)
        if not meta:
            return {"success": False, "reason": "Entity not found"}

        current_state = LifecycleState(meta["lifecycle_state"])

        # Check valid transitions
        if new_state not in VALID_TRANSITIONS.get(current_state, []):
            return {
                "success": False,
                "reason": f"Invalid transition: {current_state.value} → {new_state.value}",
                "valid_transitions": [s.value for s in VALID_TRANSITIONS.get(current_state, [])],
            }

        # Deletion guards
        if new_state == LifecycleState.MARKED_FOR_DELETION and not force:
            guard_result = self._check_deletion_guards(meta)
            if not guard_result["passed"]:
                return {
                    "success": False,
                    "reason": "Deletion guards failed",
                    "guards": guard_result,
                }

        # Perform transition
        success = self._engine.update_lifecycle(entity_type, entity_id, new_state)

        if success:
            self._log_transition(entity_type, entity_id, current_state, new_state)

        return {
            "success": success,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_state": current_state.value,
            "new_state": new_state.value,
        }

    def _check_deletion_guards(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check all deletion guards.
        ALL must pass for deletion to proceed.
        """
        guards = {}

        # Guard 1: State must be COMPLETED or BACKED_UP
        state = meta.get("lifecycle_state", "")
        guards["state_eligible"] = state in (
            LifecycleState.COMPLETED.value,
            LifecycleState.BACKED_UP.value,
        )

        # Guard 2: Age >= 30 days
        created_at = meta.get("created_at", "")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at)
                age = datetime.now(timezone.utc) - created
                guards["age_met"] = age.days >= DELETION_AGE_DAYS
                guards["age_days"] = age.days
            except (ValueError, TypeError):
                guards["age_met"] = False
                guards["age_days"] = 0
        else:
            guards["age_met"] = False
            guards["age_days"] = 0

        # Guard 3: Backup verified
        guards["backup_verified"] = meta.get("backup_verified", False)

        # Guard 4: Integrity verified
        guards["integrity_verified"] = meta.get("integrity_verified", False)

        # Guard 5: No legal hold
        guards["no_legal_hold"] = not meta.get("legal_hold", False)

        # Overall
        guards["passed"] = all([
            guards["state_eligible"],
            guards["age_met"],
            guards["backup_verified"],
            guards["integrity_verified"],
            guards["no_legal_hold"],
        ])

        return guards

    def get_deletion_preview(
        self,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Preview which entities are eligible for deletion.
        Does NOT actually delete anything.
        """
        eligible = []
        types_to_check = [entity_type] if entity_type else list(ENTITY_TYPES)

        for et in types_to_check:
            entities = self._engine.list_entities(et, limit=10000)
            for meta in entities:
                if meta.get("lifecycle_state") in (
                    LifecycleState.COMPLETED.value,
                    LifecycleState.BACKED_UP.value,
                ):
                    guards = self._check_deletion_guards(meta)
                    eligible.append({
                        "entity_type": et,
                        "entity_id": meta["entity_id"],
                        "lifecycle_state": meta["lifecycle_state"],
                        "guards": guards,
                        "would_delete": guards["passed"],
                    })

        return eligible

    # =========================================================================
    # DAILY SWEEP
    # =========================================================================

    def start_sweep_thread(self) -> None:
        """Start the background daily sweep thread."""
        if self._sweep_thread and self._sweep_thread.is_alive():
            return

        self._running = True
        self._sweep_thread = threading.Thread(
            target=self._sweep_loop,
            daemon=True,
            name="lifecycle-sweep",
        )
        self._sweep_thread.start()
        logger.info("Lifecycle sweep thread started")

    def stop_sweep_thread(self) -> None:
        """Stop the daily sweep thread."""
        self._running = False
        if self._sweep_thread:
            self._sweep_thread.join(timeout=5)
        logger.info("Lifecycle sweep thread stopped")

    def _sweep_loop(self) -> None:
        """Background loop that runs daily sweep."""
        while self._running:
            try:
                self.run_sweep()
            except Exception as e:
                logger.error(f"Sweep error: {e}")

            # Sleep in small intervals for responsive shutdown
            for _ in range(int(SWEEP_INTERVAL_SECONDS / 10)):
                if not self._running:
                    break
                time.sleep(10)

    def run_sweep(self) -> Dict[str, Any]:
        """
        Run a single lifecycle sweep.
        Finds all entities eligible for deletion and securely wipes them.
        """
        logger.info("Running lifecycle sweep...")
        results = {
            "swept_at": datetime.now(timezone.utc).isoformat(),
            "entities_checked": 0,
            "entities_deleted": 0,
            "entities_skipped": 0,
            "errors": [],
        }

        for entity_type in ENTITY_TYPES:
            if entity_type in ("audit", "indexes"):
                continue  # Never auto-delete audit logs or indexes

            entities = self._engine.list_entities(entity_type, limit=10000)
            for meta in entities:
                results["entities_checked"] += 1

                # Only process completed/backed-up entities
                if meta.get("lifecycle_state") not in (
                    LifecycleState.COMPLETED.value,
                    LifecycleState.BACKED_UP.value,
                ):
                    continue

                guards = self._check_deletion_guards(meta)
                if not guards["passed"]:
                    results["entities_skipped"] += 1
                    continue

                # Mark for deletion
                entity_id = meta["entity_id"]
                self._engine.update_lifecycle(
                    entity_type, entity_id,
                    LifecycleState.MARKED_FOR_DELETION,
                )

                # Secure wipe
                try:
                    entity_dir = str(self._engine._entity_dir(entity_type))
                    audit_dir = str(self._engine.root / "audit")
                    wipe_result = secure_wipe_entity(
                        entity_dir, entity_id, audit_dir,
                    )

                    if wipe_result["all_verified"]:
                        results["entities_deleted"] += 1
                        logger.info(
                            f"SWEPT: {entity_type}/{entity_id} "
                            f"({wipe_result['files_wiped']} files)"
                        )
                    else:
                        results["errors"].append({
                            "entity": f"{entity_type}/{entity_id}",
                            "reason": "Wipe verification failed",
                        })
                except Exception as e:
                    results["errors"].append({
                        "entity": f"{entity_type}/{entity_id}",
                        "reason": str(e),
                    })

        # Log sweep result
        self._log_sweep_result(results)

        logger.info(
            f"Sweep complete: checked={results['entities_checked']}, "
            f"deleted={results['entities_deleted']}, "
            f"skipped={results['entities_skipped']}"
        )

        return results

    def _log_transition(
        self,
        entity_type: str,
        entity_id: str,
        old_state: LifecycleState,
        new_state: LifecycleState,
    ) -> None:
        """Log a lifecycle transition to audit log."""
        audit_dir = self._engine.root / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(audit_dir / "lifecycle.log")

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "LIFECYCLE_TRANSITION",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_state": old_state.value,
            "new_state": new_state.value,
        }

        record_bytes = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        fd = os.open(log_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, record_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _log_sweep_result(self, result: Dict[str, Any]) -> None:
        """Log a sweep result to audit log."""
        audit_dir = self._engine.root / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(audit_dir / "lifecycle.log")

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "LIFECYCLE_SWEEP",
            **result,
        }

        record_bytes = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        fd = os.open(log_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, record_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
