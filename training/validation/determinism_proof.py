"""
Phase 3: Replay Determinism Proof.

Runs 3 identical training runs with torch.use_deterministic_algorithms(True).
Same seed=42, same dataset, same batch order.

PASS if:
  - All 3 weight hashes match
  - All 3 final losses match to 6 decimal places
  - All 3 final accuracies match

GOVERNANCE: MODE-A only. Zero decision authority.
"""
import sys
import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch
import torch.nn as nn

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [DETERMINISM] %(message)s')
logger = logging.getLogger(__name__)

N_RUNS = 3
SEED = 42
EPOCHS = 10


@dataclass
class RunResult:
    run_id: int
    weight_hash: str
    final_loss: float
    final_accuracy: float
    epoch_losses: List[float] = field(default_factory=list)


@dataclass
class DeterminismProofResult:
    passed: bool = True
    hashes_match: bool = False
    losses_match: bool = False
    accuracies_match: bool = False
    runs: List[dict] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    timestamp: str = ""


def set_full_determinism(seed):
    """Maximum determinism enforcement."""
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'


def build_model(dim=256):
    return nn.Sequential(
        nn.Linear(dim, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    )


def compute_weight_hash(model):
    """SHA-256 hash of all model parameters concatenated."""
    h = hashlib.sha256()
    for param in model.parameters():
        h.update(param.data.cpu().numpy().tobytes())
    return h.hexdigest()


def run_single_training(features, labels, run_id, seed=SEED, epochs=EPOCHS):
    """One deterministic training run."""
    set_full_determinism(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    N = len(labels)
    # Deterministic split
    np.random.seed(seed)
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]

    model = build_model(features.shape[1]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    epoch_losses = []

    for ep in range(epochs):
        model.train()
        # Deterministic batch order
        np.random.seed(seed + ep)
        perm = np.random.permutation(len(train_l))
        total_loss = 0.0
        n_batches = 0

        for i in range(0, len(train_l), 256):
            end = min(i + 256, len(train_l))
            bx = torch.tensor(train_f[perm[i:end]], dtype=torch.float32).to(device)
            by = torch.tensor(train_l[perm[i:end]], dtype=torch.long).to(device)
            logits = model(bx)
            loss = criterion(logits, by)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        epoch_losses.append(round(avg_loss, 6))

    # Final evaluation
    model.eval()
    with torch.no_grad():
        tx = torch.tensor(test_f, dtype=torch.float32).to(device)
        tl = torch.tensor(test_l, dtype=torch.long).to(device)
        test_logits = model(tx)
        test_loss = criterion(test_logits, tl).item()
        test_acc = (test_logits.argmax(1) == tl).float().mean().item()

    weight_hash = compute_weight_hash(model)

    return RunResult(
        run_id=run_id,
        weight_hash=weight_hash,
        final_loss=round(test_loss, 6),
        final_accuracy=round(test_acc, 6),
        epoch_losses=epoch_losses,
    )


def run_determinism_proof(features, labels):
    """Run 3 identical training sessions and compare."""
    logger.info("=" * 60)
    logger.info("REPLAY DETERMINISM PROOF")
    logger.info("=" * 60)
    logger.info(f"Runs: {N_RUNS}, Seed: {SEED}, Epochs: {EPOCHS}")
    logger.info(f"Dataset: {features.shape[0]} samples, {features.shape[1]}D")

    result = DeterminismProofResult(
        timestamp=datetime.now(timezone.utc).isoformat())

    runs = []
    for r in range(N_RUNS):
        logger.info(f"\n--- Run {r+1}/{N_RUNS} ---")
        run_result = run_single_training(features, labels, r + 1)
        runs.append(run_result)
        logger.info(f"  Hash:     {run_result.weight_hash[:32]}...")
        logger.info(f"  Loss:     {run_result.final_loss}")
        logger.info(f"  Accuracy: {run_result.final_accuracy}")

    result.runs = [asdict(r) for r in runs]

    # Compare
    hashes = [r.weight_hash for r in runs]
    losses = [r.final_loss for r in runs]
    accs = [r.final_accuracy for r in runs]

    result.hashes_match = len(set(hashes)) == 1
    result.losses_match = all(abs(l - losses[0]) < 1e-6 for l in losses)
    result.accuracies_match = all(abs(a - accs[0]) < 1e-6 for a in accs)

    if not result.hashes_match:
        result.failures.append(
            f"Weight hashes differ: {[h[:16] for h in hashes]}")
    if not result.losses_match:
        result.failures.append(f"Losses differ: {losses}")
    if not result.accuracies_match:
        result.failures.append(f"Accuracies differ: {accs}")

    result.passed = result.hashes_match and result.losses_match and \
                     result.accuracies_match

    logger.info(f"\n{'=' * 60}")
    logger.info(f"RESULT: {'PASS' if result.passed else 'FAIL'}")
    logger.info(f"  Hashes match:     {result.hashes_match}")
    logger.info(f"  Losses match:     {result.losses_match}")
    logger.info(f"  Accuracies match: {result.accuracies_match}")
    logger.info(f"{'=' * 60}")

    if result.failures:
        for f in result.failures:
            logger.info(f"  [!] {f}")

    return result


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    from backend.training.representation_bridge import RepresentationExpander

    orig_config = DatasetConfig(total_samples=18000)
    orig_ds = RealTrainingDataset(config=orig_config, seed=42)
    orig_f = orig_ds._features_tensor.numpy()
    orig_l = orig_ds._labels_tensor.numpy()

    exp = RepresentationExpander(seed=42)
    exp_f, exp_l = exp.generate_expanded_dataset(8000)

    features = np.concatenate([orig_f, exp_f], axis=0)
    labels = np.concatenate([orig_l, exp_l], axis=0)

    rng = np.random.RandomState(42)
    perm = rng.permutation(len(labels))
    features, labels = features[perm], labels[perm]

    result = run_determinism_proof(features, labels)

    report_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    rp = os.path.join(report_dir, 'determinism_proof.json')
    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(asdict(result), f, indent=2)
    logger.info(f"Report saved: {rp}")
    sys.exit(0 if result.passed else 1)
