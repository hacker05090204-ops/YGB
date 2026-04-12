from __future__ import annotations

import pytest
import torch

from backend.training.training_optimizer import (
    EarlyStopping,
    HardNegativeMiner,
    WarmupCosineScheduler,
)


def test_warmup_cosine_scheduler_increases_then_decays():
    parameter = torch.nn.Parameter(torch.tensor([1.0], dtype=torch.float32))
    optimizer = torch.optim.SGD([parameter], lr=0.1)
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=6,
        warmup_steps=2,
        min_lr=0.001,
        warmup_start_factor=0.1,
    )

    learning_rates = [optimizer.param_groups[0]["lr"]]
    for _ in range(6):
        optimizer.step()
        scheduler.step()
        learning_rates.append(optimizer.param_groups[0]["lr"])

    assert learning_rates[0] < learning_rates[1] < learning_rates[2]
    assert learning_rates[2] > learning_rates[3] > learning_rates[4]
    assert learning_rates[-1] >= 0.001


def test_hard_negative_miner_returns_highest_loss_negative_samples():
    miner = HardNegativeMiner(max_hard_examples=2)

    hard_indices = miner.mine(
        losses=[0.30, 1.40, 1.10, 0.25],
        labels=[0, 0, 0, 1],
        positive_probabilities=[0.99, 0.40, 0.80, 0.10],
        dataset_indices=[10, 11, 12, 13],
    )

    assert hard_indices == [11, 12]


def test_early_stopping_triggers_on_plateau():
    early_stopper = EarlyStopping(patience=2, min_delta=0.0)

    assert early_stopper.step(1.0) is False
    assert early_stopper.step(1.0) is False
    assert early_stopper.step(1.0) is True

