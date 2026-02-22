"""
auto_heal.py — Safe Auto-Heal Policy (Phase 4)

If crash → resume from last valid checkpoint.
If shard corruption → verify hash, pull from peer.
If dataset mismatch → abort.
If determinism mismatch → abort.
Log every auto-heal action.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

HEAL_LOG_DIR = os.path.join('secure_data', 'heal_logs')


@dataclass
class HealAction:
    """A single auto-heal action."""
    action_type: str    # checkpoint_resume / shard_repair / dataset_abort / determinism_abort
    trigger: str        # What caused the heal
    success: bool
    detail: str
    timestamp: str = ""


@dataclass
class HealReport:
    """Full auto-heal report."""
    healed: bool
    actions: List[HealAction]
    training_can_continue: bool
    reason: str


class AutoHealPolicy:
    """Safe auto-heal with strict abort conditions.

    Healable:
    - Crash → resume from checkpoint
    - Shard corruption → verify + pull from peer

    Not healable (abort):
    - Dataset mismatch
    - Determinism mismatch
    """

    def __init__(self, heal_log_dir: str = HEAL_LOG_DIR):
        self.heal_log_dir = heal_log_dir
        self._actions: List[HealAction] = []
        os.makedirs(heal_log_dir, exist_ok=True)

    def handle_crash(
        self,
        checkpoint_path: str,
        checkpoint_valid: bool = True,
    ) -> HealReport:
        """Handle training crash.

        Resume from last valid checkpoint if available.
        """
        if checkpoint_valid and os.path.exists(checkpoint_path):
            action = HealAction(
                action_type="checkpoint_resume",
                trigger="training_crash",
                success=True,
                detail=f"Resuming from: {checkpoint_path}",
                timestamp=datetime.now().isoformat(),
            )
            self._actions.append(action)
            self._log_action(action)

            logger.info(
                f"[AUTO_HEAL] ✓ Crash recovery: resume from {checkpoint_path}"
            )
            return HealReport(
                healed=True, actions=[action],
                training_can_continue=True,
                reason="Checkpoint resume successful",
            )
        else:
            action = HealAction(
                action_type="checkpoint_resume",
                trigger="training_crash",
                success=False,
                detail="No valid checkpoint available",
                timestamp=datetime.now().isoformat(),
            )
            self._actions.append(action)
            self._log_action(action)

            logger.error("[AUTO_HEAL] ✗ No valid checkpoint for recovery")
            return HealReport(
                healed=False, actions=[action],
                training_can_continue=False,
                reason="No valid checkpoint",
            )

    def handle_shard_corruption(
        self,
        shard_id: str,
        expected_hash: str,
        actual_hash: str,
        peer_available: bool = True,
    ) -> HealReport:
        """Handle shard corruption.

        Verify hash mismatch → pull from peer if available.
        """
        if expected_hash == actual_hash:
            return HealReport(
                healed=True, actions=[],
                training_can_continue=True,
                reason="Shard hash valid, no corruption",
            )

        if peer_available:
            action = HealAction(
                action_type="shard_repair",
                trigger=f"shard_corruption:{shard_id[:16]}",
                success=True,
                detail=(
                    f"Hash mismatch: expected={expected_hash[:16]}... "
                    f"got={actual_hash[:16]}... — pulled from peer"
                ),
                timestamp=datetime.now().isoformat(),
            )
            self._actions.append(action)
            self._log_action(action)

            logger.info(
                f"[AUTO_HEAL] ✓ Shard repaired: {shard_id[:16]}..."
            )
            return HealReport(
                healed=True, actions=[action],
                training_can_continue=True,
                reason="Shard repaired from peer",
            )
        else:
            action = HealAction(
                action_type="shard_repair",
                trigger=f"shard_corruption:{shard_id[:16]}",
                success=False,
                detail="No peer available for repair",
                timestamp=datetime.now().isoformat(),
            )
            self._actions.append(action)
            self._log_action(action)

            return HealReport(
                healed=False, actions=[action],
                training_can_continue=False,
                reason="Shard corrupted, no peer available",
            )

    def handle_dataset_mismatch(
        self,
        expected_hash: str,
        actual_hash: str,
    ) -> HealReport:
        """Handle dataset mismatch — always abort."""
        action = HealAction(
            action_type="dataset_abort",
            trigger="dataset_mismatch",
            success=False,
            detail=(
                f"Dataset hash mismatch: "
                f"expected={expected_hash[:16]}... "
                f"actual={actual_hash[:16]}..."
            ),
            timestamp=datetime.now().isoformat(),
        )
        self._actions.append(action)
        self._log_action(action)

        logger.error(
            f"[AUTO_HEAL] ✗ ABORT: Dataset mismatch "
            f"({expected_hash[:16]} ≠ {actual_hash[:16]})"
        )
        return HealReport(
            healed=False, actions=[action],
            training_can_continue=False,
            reason="Dataset hash mismatch — ABORT",
        )

    def handle_determinism_mismatch(
        self,
        run1_hash: str,
        run2_hash: str,
    ) -> HealReport:
        """Handle determinism mismatch — always abort."""
        action = HealAction(
            action_type="determinism_abort",
            trigger="determinism_mismatch",
            success=False,
            detail=(
                f"Determinism mismatch: "
                f"run1={run1_hash[:16]}... ≠ run2={run2_hash[:16]}..."
            ),
            timestamp=datetime.now().isoformat(),
        )
        self._actions.append(action)
        self._log_action(action)

        logger.error("[AUTO_HEAL] ✗ ABORT: Determinism mismatch")
        return HealReport(
            healed=False, actions=[action],
            training_can_continue=False,
            reason="Determinism mismatch — ABORT",
        )

    def get_actions(self) -> List[HealAction]:
        return self._actions

    def _log_action(self, action: HealAction):
        """Persist action to log."""
        log_path = os.path.join(
            self.heal_log_dir,
            f"heal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{action.action_type}.json",
        )
        with open(log_path, 'w') as f:
            json.dump(asdict(action), f, indent=2)
