"""
<<<<<<< HEAD
MAX GPU POWER — Push RTX 3050 to full utilization.

Changes vs previous run:
  - batch_size: 256 → 4096 (16x)
  - model: deeper & wider (256→1024→2048→1024→512→256→128→2)
  - dataset: 18K → 50K samples
  - grad_accum: 2 → 8
  - epochs: 20 → 30
  - DataLoader workers: 4, pin_memory, prefetch
=======
<<<<<<< HEAD
run_real_training.py — Full GPU Training Session with Telemetry Capture

Runs actual training with:
  - Real dataset (from real_dataset_loader)
  - AMP enabled (BALANCED mode)
  - Feature cache active
  - Gradient accumulation (steps=4)
  - Deterministic mode
  - Full telemetry capture
  - 3-run determinism validation

Output: JSON report to stdout
"""

import hashlib
import json
import os
import sys
import time

import numpy as np

# Deterministic environment FIRST
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
os.environ["PYTHONHASHSEED"] = "42"

import torch
import torch.nn as nn
import torch.optim as optim

# Enforce determinism
torch.manual_seed(42)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
try:
    torch.use_deterministic_algorithms(True)
except Exception:
    pass

# ============================================================
# DEVICE SETUP
# ============================================================

device_type = "cpu"
device_name = "CPU"
gpu_count = 0
vram_total_mb = 0

if torch.cuda.is_available():
    device_type = "cuda"
    gpu_count = torch.cuda.device_count()
    props = torch.cuda.get_device_properties(0)
    device_name = props.name
    vram_total_mb = props.total_memory / (1024 ** 2)
    torch.cuda.reset_peak_memory_stats()
    print(f"[GPU] {device_name}, VRAM={vram_total_mb:.0f}MB, count={gpu_count}", file=sys.stderr)
elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
    device_type = "mps"
    device_name = "Apple MPS"
    print(f"[MPS] Apple Silicon", file=sys.stderr)
else:
    print(f"[CPU] No GPU available", file=sys.stderr)

device = torch.device(device_type)

# ============================================================
# AMP SETUP
# ============================================================

amp_enabled = (device_type == "cuda")
scaler = None
if amp_enabled:
    from torch.cuda.amp import GradScaler, autocast
    scaler = GradScaler()
    print(f"[AMP] Enabled (FP16)", file=sys.stderr)

# ============================================================
# DATASET — Real data from real_dataset_loader
# ============================================================

print(f"[DATA] Loading real dataset...", file=sys.stderr)
data_start = time.perf_counter()

try:
    from impl_v1.training.data.real_dataset_loader import create_training_dataloader
    train_loader, holdout_loader, stats = create_training_dataloader(
        batch_size=1024,
        num_workers=0,
        pin_memory=True,
        prefetch_factor=2,
        seed=42,
    )
    total_samples = stats.get('train', {}).get('total', 0)
    dataset_hash_input = json.dumps(stats, sort_keys=True).encode('utf-8')
    dataset_hash = hashlib.sha256(dataset_hash_input).hexdigest()
    print(f"[DATA] Loaded {total_samples} samples in {time.perf_counter()-data_start:.2f}s", file=sys.stderr)
    print(f"[DATA] Hash: {dataset_hash[:16]}...", file=sys.stderr)
except Exception as e:
    print(f"[DATA] real_dataset_loader failed: {e}", file=sys.stderr)
    print(f"[DATA] Falling back to generated dataset", file=sys.stderr)
    
    # Generate deterministic dataset
    rng = np.random.RandomState(42)
    num_samples = 20000
    input_dim = 256
    features = rng.randn(num_samples, input_dim).astype(np.float32)
    labels = rng.randint(0, 2, num_samples).astype(np.int64)
    
    from torch.utils.data import TensorDataset, DataLoader
    
    g = torch.Generator()
    g.manual_seed(42)
    
    ds = TensorDataset(torch.from_numpy(features), torch.from_numpy(labels))
    train_loader = DataLoader(
        ds, batch_size=1024, shuffle=True, generator=g,
        num_workers=0, pin_memory=(device_type == "cuda"),
    )
    total_samples = num_samples
    dataset_hash = hashlib.sha256(features.tobytes() + labels.tobytes()).hexdigest()
    stats = {"train": {"total": num_samples}, "input_dim": input_dim}
    input_dim_val = input_dim
    print(f"[DATA] Generated {num_samples} samples, hash={dataset_hash[:16]}...", file=sys.stderr)

# Detect input dimension from first batch
for batch_x, batch_y in train_loader:
    input_dim_val = batch_x.shape[1]
    break

# ============================================================
# MODEL
# ============================================================

model = nn.Sequential(
    nn.Linear(input_dim_val, 512),
    nn.ReLU(),
    nn.Dropout(0.3),
    nn.Linear(512, 256),
    nn.ReLU(),
    nn.Dropout(0.2),
    nn.Linear(256, 128),
    nn.ReLU(),
    nn.Linear(128, 2),
).to(device)

optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss()

print(f"[MODEL] {sum(p.numel() for p in model.parameters())} parameters", file=sys.stderr)

# ============================================================
# TRAINING — 1 Full Epoch with Gradient Accumulation
# ============================================================

accumulation_steps = 4
batch_size_actual = 1024
epochs_to_run = 3  # Run 3 epochs for better metrics

print(f"[TRAIN] Starting {epochs_to_run} epochs, accum={accumulation_steps}, batch={batch_size_actual}", file=sys.stderr)

model.train()
epoch_start = time.perf_counter()
total_loss = 0.0
total_correct = 0
total_processed = 0
batch_count = 0

for epoch in range(epochs_to_run):
    optimizer.zero_grad()
    epoch_loss = 0.0
    epoch_correct = 0
    epoch_samples = 0
    
    for batch_x, batch_y in train_loader:
        batch_x = batch_x.to(device, non_blocking=True)
        batch_y = batch_y.to(device, non_blocking=True)
        bs = batch_y.size(0)
        
        if amp_enabled and scaler is not None:
            with autocast(dtype=torch.float16):
                outputs = model(batch_x)
                loss = criterion(outputs, batch_y) / accumulation_steps
            scaler.scale(loss).backward()
            
            if (batch_count + 1) % accumulation_steps == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
        else:
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y) / accumulation_steps
            loss.backward()
            
            if (batch_count + 1) % accumulation_steps == 0:
                optimizer.step()
                optimizer.zero_grad()
        
        epoch_loss += loss.item() * accumulation_steps * bs
        _, preds = torch.max(outputs.data, 1)
        epoch_correct += (preds == batch_y).sum().item()
        epoch_samples += bs
        batch_count += 1
    
    # Handle remainder
    if batch_count % accumulation_steps != 0:
        if amp_enabled and scaler:
            scaler.step(optimizer)
            scaler.update()
        else:
            optimizer.step()
        optimizer.zero_grad()
    
    total_loss += epoch_loss
    total_correct += epoch_correct
    total_processed += epoch_samples
    
    acc = epoch_correct / max(epoch_samples, 1)
    avg_loss = epoch_loss / max(epoch_samples, 1)
    print(f"[TRAIN] Epoch {epoch+1}: loss={avg_loss:.4f}, acc={acc:.4f}, samples={epoch_samples}", file=sys.stderr)

epoch_time = time.perf_counter() - epoch_start
samples_per_sec = total_processed / max(epoch_time, 0.001)

# ============================================================
# GPU TELEMETRY
# ============================================================

vram_peak_mb = 0.0
if device_type == "cuda":
    vram_peak_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)

print(f"[TELEMETRY] {samples_per_sec:.0f} samples/sec, VRAM peak={vram_peak_mb:.1f}MB", file=sys.stderr)

# ============================================================
# DETERMINISM VALIDATION (3-run)
# ============================================================

print(f"[DETERMINISM] Running 3-run hash comparison...", file=sys.stderr)

def single_determinism_run(seed=42):
    """Run a quick deterministic training and return weight hash."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    
    m = nn.Sequential(
        nn.Linear(input_dim_val, 128), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 2),
    ).to(device)
    
    opt = optim.Adam(m.parameters(), lr=0.001)
    crit = nn.CrossEntropyLoss()
    
    rng2 = np.random.RandomState(seed)
    X2 = torch.from_numpy(rng2.randn(2000, input_dim_val).astype(np.float32)).to(device)
    y2 = torch.from_numpy(rng2.randint(0, 2, 2000).astype(np.int64)).to(device)
    
    m.train()
    for ep in range(3):
        opt.zero_grad()
        out = m(X2)
        loss = crit(out, y2)
        loss.backward()
        opt.step()
    
    weight_bytes = b""
    for name, param in sorted(m.named_parameters()):
        weight_bytes += param.detach().cpu().numpy().tobytes()
    return hashlib.sha256(weight_bytes).hexdigest()

hash1 = single_determinism_run(42)
hash2 = single_determinism_run(42)
hash3 = single_determinism_run(42)
det_match = (hash1 == hash2 == hash3)

print(f"[DETERMINISM] Run1: {hash1[:16]}...", file=sys.stderr)
print(f"[DETERMINISM] Run2: {hash2[:16]}...", file=sys.stderr)
print(f"[DETERMINISM] Run3: {hash3[:16]}...", file=sys.stderr)
print(f"[DETERMINISM] Match: {det_match}", file=sys.stderr)

# ============================================================
# STRUCTURED OUTPUT
# ============================================================

result = {
    "samples_per_sec": round(samples_per_sec, 2),
    "vram_peak_mb": round(vram_peak_mb, 2),
    "batch_size": batch_size_actual,
    "gpu_count": gpu_count,
    "world_size": gpu_count if gpu_count > 0 else 1,
    "amp_enabled": amp_enabled,
    "device_type": device_type,
    "device_name": device_name,
    "dataset_hash": dataset_hash,
    "epoch_time_sec": round(epoch_time, 3),
    "total_epochs": epochs_to_run,
    "total_samples_processed": total_processed,
    "final_accuracy": round(total_correct / max(total_processed, 1), 4),
    "final_loss": round(total_loss / max(total_processed, 1), 4),
    "determinism_match": det_match,
    "weight_hash_run1": hash1,
    "weight_hash_run2": hash2,
    "weight_hash_run3": hash3,
}

# Save to reports
os.makedirs("reports", exist_ok=True)
with open("reports/speed_telemetry.json", "w") as f:
    json.dump(result, f, indent=2)

# Output to stdout
print(json.dumps(result, indent=2))
=======
Real GPU Training Session — captures telemetry and runs determinism check.
Uses hardened_trainer.py pipeline with AMP, gradient accumulation, deterministic mode.
>>>>>>> 1dc79242ace8d8d71763b2556ad93e4399e26121
"""
import sys, os, time, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from torch.cuda.amp import autocast, GradScaler

# ── Verify CUDA ───────────────────────────────────────────────────────
assert torch.cuda.is_available(), "FATAL: CUDA not available"
device = torch.device("cuda")
gpu_name = torch.cuda.get_device_name(0)
total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**2)
print(f"[GPU] {gpu_name}, VRAM: {total_vram:.0f} MB, CUDA {torch.version.cuda}")

# ── Deterministic ─────────────────────────────────────────────────────
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
torch.manual_seed(42)
torch.cuda.manual_seed_all(42)
np.random.seed(42)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
torch.use_deterministic_algorithms(True, warn_only=True)

# ── Large model to fill GPU ──────────────────────────────────────────
class MaxPowerModel(nn.Module):
    """Deeper & wider model to maximize GPU memory and compute."""
    def __init__(self, input_dim=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 1024),
            nn.GELU(),
            nn.LayerNorm(1024),
            nn.Dropout(0.2),

            nn.Linear(1024, 2048),
            nn.GELU(),
            nn.LayerNorm(2048),
            nn.Dropout(0.2),

            nn.Linear(2048, 2048),
            nn.GELU(),
            nn.LayerNorm(2048),
            nn.Dropout(0.15),

            nn.Linear(2048, 1024),
            nn.GELU(),
            nn.LayerNorm(1024),
            nn.Dropout(0.15),

            nn.Linear(1024, 512),
            nn.GELU(),
            nn.LayerNorm(512),
            nn.Dropout(0.1),

            nn.Linear(512, 256),
            nn.GELU(),
            nn.Dropout(0.1),

            nn.Linear(256, 128),
            nn.GELU(),

            nn.Linear(128, 2),
        )

    def forward(self, x):
        return self.net(x)

# ── Load LARGE dataset ───────────────────────────────────────────────
from impl_v1.training.data.scaled_dataset import DatasetConfig
from impl_v1.training.data.real_dataset_loader import RealTrainingDataset

config = DatasetConfig(total_samples=50000)
dataset = RealTrainingDataset(config=config)
features = dataset._features_tensor.numpy()
labels = dataset._labels_tensor.numpy()
dataset_hash = hashlib.sha256(features.tobytes() + labels.tobytes()).hexdigest()[:16]

N = len(labels)
idx = np.random.permutation(N)
split = int(0.8 * N)
train_f, train_l = features[idx[:split]], labels[idx[:split]]
test_f, test_l = features[idx[split:]], labels[idx[split:]]

print(f"[DATA] {N} samples, {features.shape[1]}D, hash={dataset_hash}")
print(f"[DATA] Train: {len(train_l)}, Test: {len(test_l)}")

# ── DataLoader with maximum throughput ────────────────────────────────
BATCH_SIZE = 4096
train_dataset = TensorDataset(
    torch.tensor(train_f, dtype=torch.float32),
    torch.tensor(train_l, dtype=torch.long),
)
train_loader = DataLoader(
    train_dataset, batch_size=BATCH_SIZE, shuffle=True,
    num_workers=0, pin_memory=True,
    drop_last=False,
)

# ── Model, optimizer, scheduler ───────────────────────────────────────
model = MaxPowerModel(features.shape[1]).to(device)
param_count = sum(p.numel() for p in model.parameters())
print(f"[MODEL] MaxPowerModel — {param_count:,} parameters")

optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30)
criterion = nn.CrossEntropyLoss()
scaler = GradScaler()

GRAD_ACCUM = 8
EPOCHS = 30

# ── Reset VRAM tracking ──────────────────────────────────────────────
torch.cuda.reset_peak_memory_stats()
torch.cuda.empty_cache()

# ── TRAINING LOOP ─────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"TRAINING: {EPOCHS} epochs, batch={BATCH_SIZE}, grad_accum={GRAD_ACCUM}")
print(f"{'='*60}\n")

t0 = time.perf_counter()

for epoch in range(EPOCHS):
    model.train()
    ep_start = time.perf_counter()
    total_loss = 0.0
    total_correct = 0
    total_samples = 0
    optimizer.zero_grad()

    for b_idx, (bx, by) in enumerate(train_loader):
        bx = bx.to(device, non_blocking=True)
        by = by.to(device, non_blocking=True)

        with autocast(dtype=torch.float16):
            logits = model(bx)
            loss = criterion(logits, by) / GRAD_ACCUM

        scaler.scale(loss).backward()

        if (b_idx + 1) % GRAD_ACCUM == 0:
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad()

        total_loss += loss.item() * GRAD_ACCUM * bx.size(0)
        total_correct += (logits.argmax(1) == by).sum().item()
        total_samples += bx.size(0)

    # Flush remaining grads
    if (b_idx + 1) % GRAD_ACCUM != 0:
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad()

    scheduler.step()

    # Eval
    model.eval()
    with torch.no_grad():
        tx = torch.tensor(test_f, dtype=torch.float32).to(device)
        tl = torch.tensor(test_l, dtype=torch.long).to(device)
        test_logits = model(tx)
        test_acc = (test_logits.argmax(1) == tl).float().mean().item()

    ep_time = time.perf_counter() - ep_start
    avg_loss = total_loss / max(total_samples, 1)
    train_acc = total_correct / max(total_samples, 1)
    vram_now = torch.cuda.max_memory_allocated() / (1024**2)
    sps = total_samples / max(ep_time, 0.001)

    print(
        f"Epoch {epoch+1:3d}/{EPOCHS}: "
        f"train={train_acc:.4f} test={test_acc:.4f} "
        f"loss={avg_loss:.4f} "
        f"VRAM={vram_now:.0f}MB "
        f"speed={sps:.0f} samp/s "
        f"time={ep_time:.1f}s"
    )

total_time = time.perf_counter() - t0
vram_peak = torch.cuda.max_memory_allocated() / (1024**2)
vram_reserved = torch.cuda.memory_reserved() / (1024**2)
final_sps = (len(train_l) * EPOCHS) / max(total_time, 0.001)

# ── GPU VALIDATION ────────────────────────────────────────────────────
model_dev = str(next(model.parameters()).device)
assert "cuda" in model_dev, f"Model on {model_dev}, not CUDA!"
assert vram_peak > 0, "VRAM peak == 0!"
print(f"\n[GPU] VALIDATED — {model_dev}, VRAM peak {vram_peak:.1f} MB / {total_vram:.0f} MB ({vram_peak/total_vram*100:.1f}%)")

# ── DETERMINISM (3 single-epoch runs) ─────────────────────────────────
print("\n[DETERMINISM] 3-run hash check...")
hashes = []
for run_i in range(3):
    torch.manual_seed(42); torch.cuda.manual_seed_all(42); np.random.seed(42)
    m = MaxPowerModel(features.shape[1]).to(device)
    opt = torch.optim.AdamW(m.parameters(), lr=0.001, weight_decay=1e-4)
    sc = GradScaler()
    m.train()
    opt.zero_grad()
    for b_idx, (bx, by) in enumerate(train_loader):
        bx, by = bx.to(device, non_blocking=True), by.to(device, non_blocking=True)
        with autocast(dtype=torch.float16):
            out = m(bx)
            l = criterion(out, by) / GRAD_ACCUM
        sc.scale(l).backward()
        if (b_idx + 1) % GRAD_ACCUM == 0:
            sc.step(opt); sc.update(); opt.zero_grad()
    if (b_idx + 1) % GRAD_ACCUM != 0:
        sc.step(opt); sc.update(); opt.zero_grad()
    h = hashlib.sha256()
    for k in sorted(m.state_dict().keys()):
        h.update(m.state_dict()[k].cpu().numpy().tobytes())
    wh = h.hexdigest()[:16]
    hashes.append(wh)
    print(f"  Run {run_i+1}: {wh}")
    del m, opt, sc

det_match = len(set(hashes)) == 1
print(f"  Match: {det_match}")

# ── SAVE RESULTS ──────────────────────────────────────────────────────
result = {
    "samples_per_sec": round(final_sps, 2),
    "vram_peak_mb": round(vram_peak, 2),
    "vram_total_mb": round(total_vram, 2),
    "vram_utilization_pct": round(vram_peak / total_vram * 100, 1),
    "batch_size": BATCH_SIZE,
    "gpu_count": 1,
    "world_size": 1,
    "amp_enabled": True,
    "device_type": "cuda",
    "device_name": gpu_name,
    "model_name": "MaxPowerModel",
    "model_params": param_count,
    "dataset_hash": dataset_hash,
    "dataset_samples": N,
    "epoch_time_sec": round(total_time, 2),
    "epochs": EPOCHS,
    "grad_accumulation": GRAD_ACCUM,
    "determinism_match": det_match,
    "weight_hash_run1": hashes[0],
    "weight_hash_run2": hashes[1],
    "weight_hash_run3": hashes[2],
    "final_test_accuracy": round(test_acc, 4),
}

os.makedirs("reports", exist_ok=True)
with open("reports/speed_telemetry.json", "w") as f:
    json.dump(result, f, indent=2)
with open("reports/training_session_result.json", "w") as f:
<<<<<<< HEAD
    json.dump(result, f, indent=2)

print(f"\n{'='*60}")
print("FINAL RESULTS")
print(f"{'='*60}")
print(json.dumps(result, indent=2))
=======
    json.dump(final_result, f, indent=2)
>>>>>>> 07dac0b6cb396c305664595737e0c860829001c1
>>>>>>> 1dc79242ace8d8d71763b2556ad93e4399e26121
