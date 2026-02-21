"""
Real GPU Training Session — captures telemetry and runs determinism check.
Uses hardened_trainer.py pipeline with AMP, gradient accumulation, deterministic mode.
"""
import sys, os, time, json, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import numpy as np
import torch

# ── STEP 0: Verify CUDA ──────────────────────────────────────────────
assert torch.cuda.is_available(), "FATAL: CUDA not available — aborting"
device = torch.device("cuda")
gpu_name = torch.cuda.get_device_name(0)
gpu_count = torch.cuda.device_count()
print(f"[GPU] {gpu_name} x{gpu_count}, CUDA {torch.version.cuda}")

# ── STEP 1: Run real training ─────────────────────────────────────────
from training.validation.hardened_trainer import train_hardened, set_deterministic
from impl_v1.training.data.scaled_dataset import DatasetConfig
from impl_v1.training.data.real_dataset_loader import RealTrainingDataset

# Load real dataset
config = DatasetConfig(total_samples=18000)
dataset = RealTrainingDataset(config=config)
features = dataset._features_tensor.numpy()
labels = dataset._labels_tensor.numpy()

# Dataset hash for integrity
dataset_bytes = features.tobytes() + labels.tobytes()
dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()[:16]

print(f"[DATA] {len(labels)} samples, {features.shape[1]}D, hash={dataset_hash}")

# Reset VRAM counter
torch.cuda.reset_peak_memory_stats()

# Train
BATCH_SIZE = 256
EPOCHS = 20
t0 = time.perf_counter()

result = train_hardened(
    features, labels,
    epochs=EPOCHS,
    batch_size=BATCH_SIZE,
    grad_accum=2,
    seed=42,
    verbose=True,
)

epoch_time = time.perf_counter() - t0

# ── STEP 2: Capture telemetry ────────────────────────────────────────
vram_peak_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
samples_per_sec = (len(labels) * 0.8 * EPOCHS) / max(epoch_time, 0.001)

telemetry = {
    "samples_per_sec": round(samples_per_sec, 2),
    "vram_peak_mb": round(vram_peak_mb, 2),
    "batch_size": BATCH_SIZE,
    "gpu_count": gpu_count,
    "world_size": gpu_count,
    "amp_enabled": True,
    "device_type": "cuda",
    "model_name": "G38_BugClassifier_Hardened",
    "dataset_hash": dataset_hash,
    "total_epoch_time": round(epoch_time, 2),
    "final_accuracy": result["final_accuracy"],
    "device_name": gpu_name,
}

os.makedirs("reports", exist_ok=True)
with open("reports/speed_telemetry.json", "w") as f:
    json.dump(telemetry, f, indent=2)

print(f"\n[TELEMETRY] Saved to reports/speed_telemetry.json")
print(f"  samples_per_sec = {telemetry['samples_per_sec']}")
print(f"  vram_peak_mb    = {telemetry['vram_peak_mb']}")
print(f"  epoch_time      = {telemetry['total_epoch_time']}s")
print(f"  final_accuracy  = {telemetry['final_accuracy']}")

# ── STEP 3: Validate GPU was used ────────────────────────────────────
assert vram_peak_mb > 0, "FATAL: vram_peak_mb == 0 — GPU was NOT used"
model_device = str(next(result["model"].parameters()).device)
assert "cuda" in model_device, f"FATAL: model on {model_device}, not CUDA"
print(f"\n[GPU VALIDATION] PASS — model on {model_device}, VRAM peak {vram_peak_mb:.1f} MB")

# ── STEP 4: Determinism validator (3-run hash check) ─────────────────
print("\n[DETERMINISM] Running 3-run hash check...")
hashes = []
for run_i in range(3):
    set_deterministic()
    torch.cuda.reset_peak_memory_stats()
    r = train_hardened(features, labels, epochs=1, batch_size=BATCH_SIZE,
                       grad_accum=2, seed=42, verbose=False)
    # Hash all model weights
    state = r["model"].state_dict()
    h = hashlib.sha256()
    for k in sorted(state.keys()):
        h.update(state[k].cpu().numpy().tobytes())
    weight_hash = h.hexdigest()[:16]
    hashes.append(weight_hash)
    print(f"  Run {run_i+1}: {weight_hash}")

determinism_match = len(set(hashes)) == 1
print(f"  Match: {determinism_match}")

# ── STEP 5: Final structured JSON ────────────────────────────────────
final_result = {
    "samples_per_sec": telemetry["samples_per_sec"],
    "vram_peak_mb": telemetry["vram_peak_mb"],
    "batch_size": BATCH_SIZE,
    "gpu_count": gpu_count,
    "world_size": gpu_count,
    "amp_enabled": True,
    "device_type": "cuda",
    "dataset_hash": dataset_hash,
    "epoch_time_sec": telemetry["total_epoch_time"],
    "determinism_match": determinism_match,
    "weight_hash_run1": hashes[0],
    "weight_hash_run2": hashes[1],
    "weight_hash_run3": hashes[2],
}

print("\n" + "=" * 60)
print("FINAL RESULTS")
print("=" * 60)
print(json.dumps(final_result, indent=2))

# Also save to file
with open("reports/training_session_result.json", "w") as f:
    json.dump(final_result, f, indent=2)
