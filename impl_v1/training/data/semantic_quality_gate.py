"""
semantic_quality_gate.py — Semantic Quality Gate (Phase 2)

██████████████████████████████████████████████████████████████████████
BOUNTY-READY — MINI 3-EPOCH SANITY TEST
██████████████████████████████████████████████████████████████████████

Governance layer:
  - Quick 3-epoch training sanity check on new data batches
  - Detects: divergent loss, NaN gradients, label noise
  - Must pass before data enters main training pipeline
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Sanity thresholds
MAX_INITIAL_LOSS = 10.0      # Max loss at epoch 0
MIN_LOSS_IMPROVEMENT = 0.01  # Must improve ≥1% over 3 epochs
MAX_FINAL_LOSS = 5.0         # Max loss after 3 epochs
MAX_GRADIENT_NORM = 100.0    # Max gradient norm
LABEL_NOISE_THRESHOLD = 0.15 # Max 15% disagreement with simple classifier


@dataclass
class SanityTestResult:
    """Result of 3-epoch sanity test."""
    passed: bool
    epoch_losses: list
    loss_improvement: float
    max_gradient_norm: float
    label_noise_ratio: float
    rejection_reason: str = ""


def _simple_linear_train(
    X: np.ndarray, y: np.ndarray, n_classes: int, epochs: int = 3
) -> Tuple[list, float]:
    """
    Minimal linear classifier (softmax cross-entropy) for sanity check.
    Returns: (epoch_losses, max_grad_norm)
    """
    n_samples, n_features = X.shape
    lr = 0.01

    # Initialize weights
    W = np.zeros((n_features, n_classes), dtype=np.float64)
    b = np.zeros(n_classes, dtype=np.float64)

    epoch_losses = []
    max_grad_norm = 0.0

    for epoch in range(epochs):
        # Forward: softmax
        logits = X @ W + b
        logits -= logits.max(axis=1, keepdims=True)  # Numerical stability
        exp_logits = np.exp(logits)
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

        # Cross-entropy loss
        eps = 1e-12
        y_onehot = np.zeros((n_samples, n_classes))
        for i in range(n_samples):
            if 0 <= y[i] < n_classes:
                y_onehot[i, int(y[i])] = 1.0
        loss = -np.mean(np.sum(y_onehot * np.log(probs + eps), axis=1))
        epoch_losses.append(float(loss))

        # Check for NaN
        if np.isnan(loss):
            return epoch_losses, float('inf')

        # Backward
        grad_logits = (probs - y_onehot) / n_samples
        grad_W = X.T @ grad_logits
        grad_b = grad_logits.sum(axis=0)

        grad_norm = float(np.sqrt(np.sum(grad_W ** 2) + np.sum(grad_b ** 2)))
        if grad_norm > max_grad_norm:
            max_grad_norm = grad_norm

        # Update
        W -= lr * grad_W
        b -= lr * grad_b

    return epoch_losses, max_grad_norm


def _estimate_label_noise(
    X: np.ndarray, y: np.ndarray, n_classes: int
) -> float:
    """
    Estimate label noise using cross-validated simple classifier.
    Returns: ratio of disagreeing labels (0 = clean, 1 = all noisy)
    """
    n = len(y)
    if n < 20:
        return 0.0

    # Split 80/20
    split = int(n * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # Train simple classifier
    n_features = X_train.shape[1]
    W = np.zeros((n_features, n_classes), dtype=np.float64)
    b = np.zeros(n_classes, dtype=np.float64)
    lr = 0.01

    for _ in range(10):  # 10 epochs
        logits = X_train @ W + b
        logits -= logits.max(axis=1, keepdims=True)
        exp_logits = np.exp(logits)
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

        y_oh = np.zeros((len(y_train), n_classes))
        for i in range(len(y_train)):
            if 0 <= y_train[i] < n_classes:
                y_oh[i, int(y_train[i])] = 1.0

        grad = (probs - y_oh) / len(y_train)
        W -= lr * (X_train.T @ grad)
        b -= lr * grad.sum(axis=0)

    # Predict on test
    test_logits = X_test @ W + b
    predictions = test_logits.argmax(axis=1)

    disagreement = np.sum(predictions != y_test) / len(y_test)
    return float(disagreement)


def run_sanity_test(
    data: np.ndarray,
    labels: np.ndarray,
    n_classes: int,
) -> SanityTestResult:
    """
    Run 3-epoch sanity test on a data batch.

    Args:
        data: Feature matrix [n_samples, n_features]
        labels: Label array
        n_classes: Number of classes

    Returns:
        SanityTestResult
    """
    result = SanityTestResult(
        passed=False, epoch_losses=[], loss_improvement=0.0,
        max_gradient_norm=0.0, label_noise_ratio=0.0,
    )

    # Normalize data for stable training
    mean = data.mean(axis=0)
    std = data.std(axis=0) + 1e-8
    X_norm = (data - mean) / std

    # 3-epoch training
    losses, max_grad = _simple_linear_train(X_norm, labels, n_classes, epochs=3)
    result.epoch_losses = losses
    result.max_gradient_norm = max_grad

    # Check initial loss
    if losses and losses[0] > MAX_INITIAL_LOSS:
        result.rejection_reason = f"Initial loss too high: {losses[0]:.2f} > {MAX_INITIAL_LOSS}"
        return result

    # Check for NaN
    if any(np.isnan(l) for l in losses):
        result.rejection_reason = "NaN loss detected — data corruption"
        return result

    # Check gradient norm
    if max_grad > MAX_GRADIENT_NORM:
        result.rejection_reason = f"Gradient explosion: {max_grad:.2f} > {MAX_GRADIENT_NORM}"
        return result

    # Check loss improvement
    if len(losses) >= 2:
        result.loss_improvement = (losses[0] - losses[-1]) / max(losses[0], 1e-12)
        if result.loss_improvement < MIN_LOSS_IMPROVEMENT:
            result.rejection_reason = (
                f"No improvement: {result.loss_improvement:.4f} < {MIN_LOSS_IMPROVEMENT}"
            )
            return result

    # Check final loss
    if losses and losses[-1] > MAX_FINAL_LOSS:
        result.rejection_reason = f"Final loss too high: {losses[-1]:.2f} > {MAX_FINAL_LOSS}"
        return result

    # Label noise estimation
    result.label_noise_ratio = _estimate_label_noise(X_norm, labels, n_classes)
    if result.label_noise_ratio > LABEL_NOISE_THRESHOLD:
        result.rejection_reason = (
            f"Label noise too high: {result.label_noise_ratio:.2%} > {LABEL_NOISE_THRESHOLD:.0%}"
        )
        return result

    result.passed = True
    logger.info(
        f"[SANITY] ✓ Passed: loss {losses[0]:.3f}→{losses[-1]:.3f}, "
        f"improvement={result.loss_improvement:.2%}, "
        f"label_noise={result.label_noise_ratio:.2%}"
    )
    return result
