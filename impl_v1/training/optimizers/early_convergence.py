"""
early_convergence.py — Early Convergence Detection

If:
  val_accuracy plateaus for N epochs (default 5)
  AND loss_delta < threshold (default 0.001)

Then:
  Stop training early.

Saves epochs compared to max training budget.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConvergenceState:
    """Convergence tracking state."""
    patience: int = 5
    loss_threshold: float = 0.001
    acc_threshold: float = 0.001
    best_accuracy: float = 0.0
    best_loss: float = float('inf')
    plateau_count: int = 0
    converged: bool = False
    converged_at_epoch: int = -1
    history: List[dict] = None

    def __post_init__(self):
        if self.history is None:
            self.history = []


class EarlyConvergenceDetector:
    """Detect when training has converged and should stop early."""

    def __init__(
        self,
        patience: int = 5,
        loss_threshold: float = 0.001,
        acc_threshold: float = 0.001,
    ):
        """
        Args:
            patience: Epochs to wait after plateau before stopping.
            loss_threshold: Minimum loss improvement to reset patience.
            acc_threshold: Minimum accuracy improvement to reset patience.
        """
        self._state = ConvergenceState(
            patience=patience,
            loss_threshold=loss_threshold,
            acc_threshold=acc_threshold,
        )

    @property
    def should_stop(self) -> bool:
        return self._state.converged

    @property
    def converged_at(self) -> int:
        return self._state.converged_at_epoch

    @property
    def plateau_count(self) -> int:
        return self._state.plateau_count

    def check_epoch(
        self,
        epoch: int,
        val_accuracy: float,
        val_loss: float,
    ) -> bool:
        """Check if training should stop after this epoch.

        Args:
            epoch: Current epoch number.
            val_accuracy: Validation accuracy.
            val_loss: Validation loss.

        Returns:
            True if training should stop.
        """
        self._state.history.append({
            'epoch': epoch,
            'val_accuracy': val_accuracy,
            'val_loss': val_loss,
        })

        # Check for improvement
        acc_improved = (val_accuracy - self._state.best_accuracy) > self._state.acc_threshold
        loss_improved = (self._state.best_loss - val_loss) > self._state.loss_threshold

        if acc_improved or loss_improved:
            # Reset plateau counter
            self._state.plateau_count = 0
            self._state.best_accuracy = max(self._state.best_accuracy, val_accuracy)
            self._state.best_loss = min(self._state.best_loss, val_loss)
        else:
            # Plateau
            self._state.plateau_count += 1

        if self._state.plateau_count >= self._state.patience:
            self._state.converged = True
            self._state.converged_at_epoch = epoch - self._state.patience
            logger.info(
                f"[CONVERGE] Early stop at epoch {epoch}: "
                f"plateau for {self._state.patience} epochs, "
                f"best_acc={self._state.best_accuracy:.4f}, "
                f"best_loss={self._state.best_loss:.4f}"
            )
            return True

        return False

    def get_savings(self, max_epochs: int) -> dict:
        """Compute savings from early stopping.

        Args:
            max_epochs: Maximum planned training epochs.

        Returns:
            Savings report dict.
        """
        actual = self._state.converged_at_epoch + 1 if self._state.converged else len(self._state.history)
        saved = max_epochs - actual

        return {
            'max_epochs': max_epochs,
            'actual_epochs': actual,
            'saved_epochs': max(saved, 0),
            'savings_pct': round(max(saved, 0) / max(max_epochs, 1) * 100, 1),
            'converged': self._state.converged,
            'best_accuracy': self._state.best_accuracy,
        }
