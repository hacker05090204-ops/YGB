"""
MAX GPU POWER — Push RTX 3050 to full utilization.

Changes vs previous run:
  - batch_size: 256 → 4096 (16x)
  - model: deeper & wider (256→1024→2048→1024→512→256→128→2)
  - dataset: 18K → 50K samples
  - grad_accum: 2 → 8
  - epochs: 20 → 30
  - DataLoader workers: 4, pin_memory, prefetch
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
    json.dump(result, f, indent=2)

print(f"\n{'='*60}")
print("FINAL RESULTS")
print(f"{'='*60}")
print(json.dumps(result, indent=2))
