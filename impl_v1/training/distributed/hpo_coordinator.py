"""
hpo_coordinator.py — Cluster-Wide Hyperparameter Search (Phase 4)

Leader-driven distributed HPO:

  1. Generate search space (grid/random)
  2. Assign trials to idle nodes
  3. Collect convergence speed + val accuracy
  4. Select best configuration
  5. Return config for full DDP training
"""

import hashlib
import itertools
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# DATA TYPES
# =============================================================================

@dataclass
class HPOTrial:
    """Single hyperparameter trial."""
    trial_id: str
    hyperparameters: Dict[str, Any]
    assigned_node: str = ""
    status: str = "pending"  # pending, running, completed, failed
    val_accuracy: float = 0.0
    convergence_speed: float = 0.0   # epochs to reach 90% of best acc
    train_loss_final: float = 0.0
    val_loss_final: float = 0.0
    duration_sec: float = 0.0
    timestamp: str = ""


@dataclass
class HPOResult:
    """Overall HPO search result."""
    best_trial_id: str
    best_hyperparameters: Dict[str, Any]
    best_accuracy: float
    total_trials: int
    completed_trials: int
    search_duration_sec: float
    all_trials: List[dict] = field(default_factory=list)


# =============================================================================
# SEARCH SPACE
# =============================================================================

DEFAULT_SEARCH_SPACE = {
    'learning_rate': [0.001, 0.005, 0.01, 0.05],
    'batch_size': [512, 1024, 2048, 4096],
    'weight_decay': [0.0, 1e-4, 1e-3],
    'warmup_steps': [0, 100, 500],
}


def generate_grid_search(
    search_space: Dict[str, List[Any]] = None,
    max_trials: int = 20,
) -> List[Dict[str, Any]]:
    """Generate grid search configurations.

    Args:
        search_space: Dict mapping param name to list of values.
        max_trials: Maximum number of trials to return.

    Returns:
        List of hyperparameter dicts.
    """
    space = search_space or DEFAULT_SEARCH_SPACE
    keys = list(space.keys())
    values = list(space.values())

    configs = []
    for combo in itertools.product(*values):
        if len(configs) >= max_trials:
            break
        configs.append(dict(zip(keys, combo)))

    logger.info(f"[HPO] Generated {len(configs)} grid search configs")
    return configs


def generate_random_search(
    search_space: Dict[str, List[Any]] = None,
    num_trials: int = 10,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Generate random search configurations.

    Args:
        search_space: Dict mapping param name to list of values.
        num_trials: Number of random configs to generate.
        seed: Random seed for reproducibility.

    Returns:
        List of hyperparameter dicts.
    """
    import random
    rng = random.Random(seed)

    space = search_space or DEFAULT_SEARCH_SPACE
    keys = list(space.keys())
    values = list(space.values())

    configs = []
    seen = set()
    for _ in range(num_trials * 3):  # Oversample to find unique
        if len(configs) >= num_trials:
            break
        combo = tuple(rng.choice(v) for v in values)
        if combo not in seen:
            seen.add(combo)
            configs.append(dict(zip(keys, combo)))

    logger.info(f"[HPO] Generated {len(configs)} random search configs")
    return configs


# =============================================================================
# HPO COORDINATOR
# =============================================================================

class HPOCoordinator:
    """Leader-driven distributed hyperparameter search.

    Usage:
      1. coordinator.generate_trials()
      2. coordinator.assign_trials(idle_nodes)
      3. [nodes run trials]
      4. coordinator.report_result(trial_id, ...)
      5. best_config = coordinator.select_best()
    """

    def __init__(self, search_mode: str = "random", max_trials: int = 10):
        self.search_mode = search_mode
        self.max_trials = max_trials
        self.trials: Dict[str, HPOTrial] = {}
        self._start_time = 0.0
        logger.info(f"[HPO] Coordinator initialized: mode={search_mode}")

    def generate_trials(
        self,
        search_space: Dict[str, List[Any]] = None,
        seed: int = 42,
    ) -> List[HPOTrial]:
        """Generate trial configurations.

        Returns list of HPOTrial objects.
        """
        self._start_time = time.perf_counter()

        if self.search_mode == "grid":
            configs = generate_grid_search(search_space, self.max_trials)
        else:
            configs = generate_random_search(search_space, self.max_trials, seed)

        trials = []
        for i, config in enumerate(configs):
            trial_id = hashlib.sha256(
                f"trial-{i}-{config}".encode()
            ).hexdigest()[:12]

            trial = HPOTrial(
                trial_id=trial_id,
                hyperparameters=config,
            )
            self.trials[trial_id] = trial
            trials.append(trial)

        logger.info(f"[HPO] Generated {len(trials)} trials")
        return trials

    def assign_trials(
        self,
        idle_node_ids: List[str],
    ) -> Dict[str, str]:
        """Assign pending trials to idle nodes.

        Returns dict mapping trial_id → node_id.
        """
        pending = [t for t in self.trials.values() if t.status == "pending"]
        assignments = {}

        for trial, node_id in zip(pending, idle_node_ids):
            trial.assigned_node = node_id
            trial.status = "running"
            trial.timestamp = datetime.now().isoformat()
            assignments[trial.trial_id] = node_id

        logger.info(
            f"[HPO] Assigned {len(assignments)} trials to "
            f"{len(idle_node_ids)} nodes"
        )
        return assignments

    def report_result(
        self,
        trial_id: str,
        val_accuracy: float,
        convergence_speed: float,
        train_loss: float = 0.0,
        val_loss: float = 0.0,
        duration_sec: float = 0.0,
    ):
        """Report trial completion."""
        if trial_id not in self.trials:
            logger.error(f"[HPO] Unknown trial: {trial_id}")
            return

        trial = self.trials[trial_id]
        trial.status = "completed"
        trial.val_accuracy = round(val_accuracy, 6)
        trial.convergence_speed = round(convergence_speed, 4)
        trial.train_loss_final = round(train_loss, 6)
        trial.val_loss_final = round(val_loss, 6)
        trial.duration_sec = round(duration_sec, 2)

        logger.info(
            f"[HPO] Trial {trial_id[:8]} completed: "
            f"acc={val_accuracy:.4f}, conv_speed={convergence_speed:.2f}"
        )

    def mark_failed(self, trial_id: str, reason: str = ""):
        """Mark a trial as failed."""
        if trial_id in self.trials:
            self.trials[trial_id].status = "failed"
            logger.warning(f"[HPO] Trial {trial_id[:8]} failed: {reason}")

    def select_best(self) -> Optional[HPOResult]:
        """Select the best hyperparameter configuration.

        Ranks by val_accuracy, then convergence_speed.

        Returns HPOResult or None if no completed trials.
        """
        completed = [
            t for t in self.trials.values() if t.status == "completed"
        ]

        if not completed:
            logger.warning("[HPO] No completed trials")
            return None

        # Sort by accuracy (desc), then convergence speed (asc = faster)
        best = max(completed, key=lambda t: (t.val_accuracy, -t.convergence_speed))

        elapsed = time.perf_counter() - self._start_time

        result = HPOResult(
            best_trial_id=best.trial_id,
            best_hyperparameters=best.hyperparameters,
            best_accuracy=best.val_accuracy,
            total_trials=len(self.trials),
            completed_trials=len(completed),
            search_duration_sec=round(elapsed, 2),
            all_trials=[asdict(t) for t in self.trials.values()],
        )

        logger.info(
            f"[HPO] Best config: {best.hyperparameters} — "
            f"acc={best.val_accuracy:.4f}"
        )

        return result

    def get_pending_count(self) -> int:
        """Number of pending (unassigned) trials."""
        return sum(1 for t in self.trials.values() if t.status == "pending")

    def get_summary(self) -> dict:
        """HPO search summary."""
        statuses = {}
        for t in self.trials.values():
            statuses[t.status] = statuses.get(t.status, 0) + 1

        return {
            'total_trials': len(self.trials),
            'statuses': statuses,
            'search_mode': self.search_mode,
        }
