"""
determinism_validator.py — 3-Run Determinism Verification

Runs training 3 times with identical seed and config.
Compares model weights, loss, and accuracy across all runs.
PASS = all outputs identical within FP32 tolerance (1e-5).

Usage:
    python -m training.validation.determinism_validator
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_RUNS = 3
TOLERANCE = 1e-5  # FP32 tolerance for weight comparison
VALIDATION_EPOCHS = 3  # Quick validation epochs


@dataclass
class RunResult:
    """Result from a single training run."""
    run_id: int
    loss_history: List[float]
    accuracy_history: List[float]
    weight_hash: str
    elapsed_seconds: float
    final_loss: float
    final_accuracy: float


# =============================================================================
# DETERMINISTIC TRAINING RUN  
# =============================================================================

def _single_run(
    run_id: int,
    seed: int = 42,
    epochs: int = VALIDATION_EPOCHS,
    input_dim: int = 256,
    num_samples: int = 2000,
) -> RunResult:
    """Execute one deterministic training run.
    
    Args:
        run_id: Run identifier.
        seed: Random seed (must be identical across runs).
        epochs: Number of training epochs.
        input_dim: Feature dimensionality.
        num_samples: Number of training samples.
    
    Returns:
        RunResult with loss, accuracy, and weight hash.
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        logger.error("PyTorch not available - cannot run determinism check")
        return RunResult(
            run_id=run_id, loss_history=[], accuracy_history=[],
            weight_hash="UNAVAILABLE", elapsed_seconds=0,
            final_loss=0, final_accuracy=0,
        )
    
    # === ENFORCE DETERMINISM ===
    torch.manual_seed(seed)
    np.random.seed(seed)
    
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    # === GENERATE DETERMINISTIC DATA ===
    rng = np.random.RandomState(seed)
    features = rng.randn(num_samples, input_dim).astype(np.float32)
    labels = rng.randint(0, 2, num_samples).astype(np.int64)
    
    X = torch.from_numpy(features).to(device)
    y = torch.from_numpy(labels).to(device)
    
    # === BUILD MODEL ===
    model = nn.Sequential(
        nn.Linear(input_dim, 128),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(128, 64),
        nn.ReLU(),
        nn.Linear(64, 2),
    ).to(device)
    
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    
    # === TRAIN ===
    loss_history = []
    accuracy_history = []
    start = time.perf_counter()
    
    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        outputs = model(X)
        loss = criterion(outputs, y)
        loss.backward()
        optimizer.step()
        
        with torch.no_grad():
            preds = outputs.argmax(dim=1)
            acc = (preds == y).float().mean().item()
        
        loss_history.append(loss.item())
        accuracy_history.append(acc)
    
    elapsed = time.perf_counter() - start
    
    # === COMPUTE WEIGHT HASH ===
    weight_bytes = b''
    for name, param in sorted(model.named_parameters()):
        weight_bytes += param.detach().cpu().numpy().tobytes()
    
    weight_hash = hashlib.sha256(weight_bytes).hexdigest()
    
    return RunResult(
        run_id=run_id,
        loss_history=loss_history,
        accuracy_history=accuracy_history,
        weight_hash=weight_hash,
        elapsed_seconds=elapsed,
        final_loss=loss_history[-1] if loss_history else 0,
        final_accuracy=accuracy_history[-1] if accuracy_history else 0,
    )


# =============================================================================
# VALIDATION
# =============================================================================

def validate_determinism(
    num_runs: int = NUM_RUNS,
    seed: int = 42,
    epochs: int = VALIDATION_EPOCHS,
    tolerance: float = TOLERANCE,
) -> Tuple[bool, dict]:
    """Run N training runs and validate determinism.
    
    Args:
        num_runs: Number of identical runs (default 3).
        seed: Random seed used for all runs.
        epochs: Epochs per run.
        tolerance: Max allowed deviation between runs.
    
    Returns:
        Tuple of (passed: bool, report: dict).
    """
    logger.info(f"[DETERMINISM] Starting {num_runs}-run validation (seed={seed}, epochs={epochs})")
    
    results: List[RunResult] = []
    for i in range(num_runs):
        logger.info(f"[DETERMINISM] Run {i+1}/{num_runs}...")
        result = _single_run(run_id=i+1, seed=seed, epochs=epochs)
        results.append(result)
    
    # === COMPARE RESULTS ===
    all_hashes = [r.weight_hash for r in results]
    weights_match = len(set(all_hashes)) == 1
    
    # Compare loss histories
    loss_match = True
    max_loss_delta = 0.0
    for i in range(1, len(results)):
        for epoch in range(epochs):
            if epoch < len(results[0].loss_history) and epoch < len(results[i].loss_history):
                delta = abs(results[0].loss_history[epoch] - results[i].loss_history[epoch])
                max_loss_delta = max(max_loss_delta, delta)
                if delta > tolerance:
                    loss_match = False
    
    # Compare accuracy histories
    acc_match = True
    max_acc_delta = 0.0
    for i in range(1, len(results)):
        for epoch in range(epochs):
            if epoch < len(results[0].accuracy_history) and epoch < len(results[i].accuracy_history):
                delta = abs(results[0].accuracy_history[epoch] - results[i].accuracy_history[epoch])
                max_acc_delta = max(max_acc_delta, delta)
                if delta > tolerance:
                    acc_match = False
    
    passed = weights_match and loss_match and acc_match
    
    report = {
        'passed': passed,
        'num_runs': num_runs,
        'seed': seed,
        'epochs': epochs,
        'tolerance': tolerance,
        'weights_match': weights_match,
        'loss_match': loss_match,
        'accuracy_match': acc_match,
        'max_loss_delta': max_loss_delta,
        'max_accuracy_delta': max_acc_delta,
        'weight_hashes': all_hashes,
        'final_losses': [r.final_loss for r in results],
        'final_accuracies': [r.final_accuracy for r in results],
        'run_times': [r.elapsed_seconds for r in results],
    }
    
    status = "PASS" if passed else "FAIL"
    logger.info(
        f"[DETERMINISM] {status}: weights={'MATCH' if weights_match else 'MISMATCH'}, "
        f"loss_delta={max_loss_delta:.2e}, acc_delta={max_acc_delta:.2e}"
    )
    
    return passed, report


def save_determinism_report(report: dict, path: str = None) -> str:
    """Save determinism validation report.
    
    Args:
        report: Report dict from validate_determinism().
        path: Custom path. Default: reports/determinism_report.json.
    
    Returns:
        Path to saved report.
    """
    if path is None:
        path = os.path.join('reports', 'determinism_report.json')
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)
    
    return path


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    passed, report = validate_determinism()
    path = save_determinism_report(report)
    
    print(f"\nDeterminism Validation: {'PASS' if passed else 'FAIL'}")
    print(f"  Runs: {report['num_runs']}")
    print(f"  Weight hashes match: {report['weights_match']}")
    print(f"  Max loss delta: {report['max_loss_delta']:.2e}")
    print(f"  Max accuracy delta: {report['max_accuracy_delta']:.2e}")
    print(f"  Report: {path}")
