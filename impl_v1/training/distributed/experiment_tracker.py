"""
experiment_tracker.py — Distributed Experiment Tracking (Phase 2)

Persistent experiment log for all training runs.

Stores per-run:
  run_id, leader_term, world_size, dataset_hash,
  hyperparameters, per_node_batch, cluster_sps,
  scaling_efficiency, energy_per_epoch, final_accuracy,
  merged_weight_hash

Central store: secure_data/experiments/
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXPERIMENTS_DIR = os.path.join('secure_data', 'experiments')


# =============================================================================
# DATA TYPES
# =============================================================================

@dataclass
class EpochLog:
    """Per-epoch metrics within a run."""
    epoch: int
    train_loss: float
    val_loss: float
    val_accuracy: float
    cluster_sps: float
    energy_joules: float
    merged_weight_hash: str
    grad_norm_avg: float = 0.0
    timestamp: str = ""


@dataclass
class ExperimentRun:
    """Full experiment run record."""
    run_id: str
    leader_term: int
    world_size: int
    dataset_hash: str
    hyperparameters: Dict[str, Any]
    per_node_batch: Dict[str, int]

    # Filled during/after training
    cluster_sps: float = 0.0
    scaling_efficiency: float = 0.0
    energy_per_epoch: float = 0.0
    total_energy: float = 0.0
    final_accuracy: float = 0.0
    merged_weight_hash: str = ""
    epochs_completed: int = 0
    epoch_logs: List[dict] = field(default_factory=list)

    # Meta
    status: str = "running"  # running, completed, failed, aborted
    start_time: str = ""
    end_time: str = ""
    duration_sec: float = 0.0


# =============================================================================
# EXPERIMENT TRACKER
# =============================================================================

class ExperimentTracker:
    """Persistent experiment tracker.

    Each run persisted as secure_data/experiments/{run_id}.json.
    """

    def __init__(self, experiments_dir: str = EXPERIMENTS_DIR):
        self.experiments_dir = experiments_dir
        os.makedirs(experiments_dir, exist_ok=True)
        self._current_run: Optional[ExperimentRun] = None
        self._start_time: float = 0
        logger.info("[TRACKER] Experiment tracker initialized")

    # -----------------------------------------------------------------
    # RUN LIFECYCLE
    # -----------------------------------------------------------------

    def start_run(
        self,
        leader_term: int,
        world_size: int,
        dataset_hash: str,
        hyperparameters: Dict[str, Any],
        per_node_batch: Dict[str, int],
        run_id: str = "",
    ) -> str:
        """Start a new experiment run.

        Returns the run_id.
        """
        if not run_id:
            run_id = hashlib.sha256(
                f"run-{time.time()}-{leader_term}".encode()
            ).hexdigest()[:16]

        self._current_run = ExperimentRun(
            run_id=run_id,
            leader_term=leader_term,
            world_size=world_size,
            dataset_hash=dataset_hash,
            hyperparameters=hyperparameters,
            per_node_batch=per_node_batch,
            start_time=datetime.now().isoformat(),
            status="running",
        )
        self._start_time = time.perf_counter()

        self._persist_run(self._current_run)
        logger.info(
            f"[TRACKER] Run started: {run_id} — "
            f"ws={world_size}, hp={hyperparameters}"
        )
        return run_id

    def log_epoch(
        self,
        epoch: int,
        train_loss: float,
        val_loss: float,
        val_accuracy: float,
        cluster_sps: float,
        energy_joules: float,
        merged_weight_hash: str,
        grad_norm_avg: float = 0.0,
    ):
        """Log metrics for one epoch."""
        if not self._current_run:
            logger.warning("[TRACKER] No active run — call start_run first")
            return

        epoch_log = EpochLog(
            epoch=epoch,
            train_loss=round(train_loss, 6),
            val_loss=round(val_loss, 6),
            val_accuracy=round(val_accuracy, 6),
            cluster_sps=round(cluster_sps, 2),
            energy_joules=round(energy_joules, 2),
            merged_weight_hash=merged_weight_hash,
            grad_norm_avg=round(grad_norm_avg, 4),
            timestamp=datetime.now().isoformat(),
        )

        self._current_run.epoch_logs.append(asdict(epoch_log))
        self._current_run.epochs_completed = epoch
        self._current_run.cluster_sps = round(cluster_sps, 2)
        self._current_run.merged_weight_hash = merged_weight_hash
        self._current_run.total_energy += energy_joules

        self._persist_run(self._current_run)

        logger.info(
            f"[TRACKER] Epoch {epoch}: loss={val_loss:.4f}, "
            f"acc={val_accuracy:.4f}, sps={cluster_sps:.0f}, "
            f"energy={energy_joules:.1f}J"
        )

    def complete_run(
        self,
        final_accuracy: float,
        scaling_efficiency: float,
        energy_per_epoch: float,
    ):
        """Complete the current run."""
        if not self._current_run:
            return

        elapsed = time.perf_counter() - self._start_time

        self._current_run.status = "completed"
        self._current_run.final_accuracy = round(final_accuracy, 6)
        self._current_run.scaling_efficiency = round(scaling_efficiency, 4)
        self._current_run.energy_per_epoch = round(energy_per_epoch, 2)
        self._current_run.end_time = datetime.now().isoformat()
        self._current_run.duration_sec = round(elapsed, 2)

        self._persist_run(self._current_run)

        logger.info(
            f"[TRACKER] Run completed: {self._current_run.run_id} — "
            f"acc={final_accuracy:.4f}, eff={scaling_efficiency:.4f}, "
            f"energy/ep={energy_per_epoch:.1f}J, time={elapsed:.1f}s"
        )
        self._current_run = None

    def abort_run(self, reason: str):
        """Abort the current run."""
        if not self._current_run:
            return

        self._current_run.status = "aborted"
        self._current_run.end_time = datetime.now().isoformat()
        self._current_run.duration_sec = round(
            time.perf_counter() - self._start_time, 2
        )

        self._persist_run(self._current_run)
        logger.error(f"[TRACKER] Run aborted: {reason}")
        self._current_run = None

    # -----------------------------------------------------------------
    # QUERIES
    # -----------------------------------------------------------------

    def list_runs(self) -> List[dict]:
        """List all experiment runs (summary only)."""
        runs = []
        for fname in sorted(os.listdir(self.experiments_dir)):
            if not fname.endswith('.json'):
                continue
            try:
                with open(os.path.join(self.experiments_dir, fname), 'r') as f:
                    data = json.load(f)
                runs.append({
                    'run_id': data.get('run_id', ''),
                    'status': data.get('status', ''),
                    'final_accuracy': data.get('final_accuracy', 0),
                    'scaling_efficiency': data.get('scaling_efficiency', 0),
                    'epochs_completed': data.get('epochs_completed', 0),
                    'duration_sec': data.get('duration_sec', 0),
                })
            except Exception:
                continue
        return runs

    def get_run(self, run_id: str) -> Optional[dict]:
        """Get full run data by ID."""
        path = os.path.join(self.experiments_dir, f"{run_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return None

    def get_best_run(self, metric: str = "final_accuracy") -> Optional[dict]:
        """Get the run with the best metric value."""
        runs = self.list_runs()
        completed = [r for r in runs if r.get('status') == 'completed']
        if not completed:
            return None
        return max(completed, key=lambda r: r.get(metric, 0))

    def get_current_run(self) -> Optional[ExperimentRun]:
        """Get the current active run."""
        return self._current_run

    # -----------------------------------------------------------------
    # PERSISTENCE
    # -----------------------------------------------------------------

    def _persist_run(self, run: ExperimentRun):
        """Save run to disk atomically."""
        path = os.path.join(self.experiments_dir, f"{run.run_id}.json")
        tmp = path + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(asdict(run), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
