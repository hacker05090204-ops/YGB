from __future__ import annotations

import pytest
import torch

from backend.training.adaptive_learner import (
    AdaptiveLearner,
    DistributionMonitor,
    EWCRegularizer,
)


def test_distribution_monitor_does_not_flag_stable_history() -> None:
    monitor = DistributionMonitor(history_size=4, shift_threshold=0.2)

    first = monitor.observe({"NEGATIVE": 50, "POSITIVE": 50})
    second = monitor.observe({"NEGATIVE": 50, "POSITIVE": 50})
    third = monitor.observe({"NEGATIVE": 49, "POSITIVE": 51})

    assert first.shift_detected is False
    assert second.shift_detected is False
    assert third.shift_detected is False
    assert third.js_distance < third.threshold


def test_distribution_monitor_does_not_flag_uniform_severity_distribution() -> None:
    monitor = DistributionMonitor(history_size=4, shift_threshold=0.2)

    first = monitor.observe({"LOW": 25, "MEDIUM": 25, "HIGH": 25, "CRITICAL": 25})
    second = monitor.observe({"LOW": 24, "MEDIUM": 26, "HIGH": 25, "CRITICAL": 25})
    third = monitor.observe({"LOW": 25, "MEDIUM": 25, "HIGH": 24, "CRITICAL": 26})

    assert first.shift_detected is False
    assert second.shift_detected is False
    assert third.shift_detected is False
    assert third.js_distance < third.threshold


def test_distribution_monitor_flags_sudden_skew() -> None:
    monitor = DistributionMonitor(history_size=4, shift_threshold=0.2)
    monitor.observe({"NEGATIVE": 50, "POSITIVE": 50})
    monitor.observe({"NEGATIVE": 51, "POSITIVE": 49})
    monitor.observe({"NEGATIVE": 50, "POSITIVE": 50})

    shifted = monitor.observe({"NEGATIVE": 95, "POSITIVE": 5})

    assert shifted.shift_detected is True
    assert shifted.js_distance > shifted.threshold


def test_distribution_monitor_flags_sudden_critical_spike() -> None:
    monitor = DistributionMonitor(history_size=4, shift_threshold=0.2)
    monitor.observe({"LOW": 30, "MEDIUM": 35, "HIGH": 25, "CRITICAL": 10})
    monitor.observe({"LOW": 31, "MEDIUM": 34, "HIGH": 25, "CRITICAL": 10})
    monitor.observe({"LOW": 29, "MEDIUM": 36, "HIGH": 25, "CRITICAL": 10})

    shifted = monitor.observe({"LOW": 5, "MEDIUM": 10, "HIGH": 10, "CRITICAL": 75})

    assert shifted.shift_detected is True
    assert shifted.current_distribution["CRITICAL"] > shifted.baseline_distribution["CRITICAL"]
    assert shifted.js_distance > shifted.threshold


def test_distribution_monitor_detect_shift_uses_js_divergence_threshold() -> None:
    monitor = DistributionMonitor(history_size=4, shift_threshold=0.15)
    monitor.observe({"NEGATIVE": 50, "POSITIVE": 50})
    monitor.observe({"NEGATIVE": 51, "POSITIVE": 49})

    assert monitor.detect_shift({"NEGATIVE": 95, "POSITIVE": 5}) is True


def test_ewc_regularizer_loss_zero_without_fisher_and_positive_after_drift(tmp_path) -> None:
    model = torch.nn.Linear(2, 2)
    regularizer = EWCRegularizer(
        lambda_weight=1.0,
        state_path=tmp_path / "adaptive_ewc_state.safetensors",
    )
    dataset = torch.utils.data.TensorDataset(
        torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32),
        torch.tensor([0, 1], dtype=torch.long),
    )
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=False)

    assert float(regularizer.ewc_loss(model).item()) == pytest.approx(0.0)

    sample_count = regularizer.compute_fisher(model, dataloader)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.add_(0.5)

    assert sample_count == 2
    assert float(regularizer.ewc_loss(model).item()) > 0.0


def test_adaptive_learner_records_and_persists_shift_events(tmp_path) -> None:
    state_path = tmp_path / "adaptive_learning_state.json"
    ewc_state_path = tmp_path / "adaptive_ewc_state.safetensors"
    model = torch.nn.Linear(2, 2)
    dataset = torch.utils.data.TensorDataset(
        torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32),
        torch.tensor([0, 1], dtype=torch.long),
    )
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=False)
    learner = AdaptiveLearner(
        state_path=state_path,
        ewc_state_path=ewc_state_path,
        history_size=3,
        shift_threshold=0.2,
        ewc_lambda=1.0,
        fisher_max_batches=4,
    )

    initial_event = learner.on_new_grab_cycle(
        {"NEGATIVE": 50, "POSITIVE": 50},
        model=model,
        prev_dataloader=dataloader,
    )
    shifted_event = learner.on_new_grab_cycle(
        {"NEGATIVE": 95, "POSITIVE": 5},
        model=model,
        prev_dataloader=dataloader,
    )

    assert initial_event is None
    assert shifted_event is not None
    assert shifted_event.fisher_sample_count == 2
    assert state_path.exists()
    assert ewc_state_path.exists()

    reloaded = AdaptiveLearner(
        state_path=state_path,
        ewc_state_path=ewc_state_path,
        history_size=3,
        shift_threshold=0.2,
        ewc_lambda=1.0,
        fisher_max_batches=4,
    )
    loaded_events = reloaded.get_events()

    assert len(loaded_events) == 1
    assert loaded_events[0].severity_counts == {"NEGATIVE": 95, "POSITIVE": 5}
    assert loaded_events[0].js_distance == pytest.approx(shifted_event.js_distance)
