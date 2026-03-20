"""
═══════════════════════════════════════════════════════════════════════
  CUDA NODE RTX3050 — Distributed Training Protocol
═══════════════════════════════════════════════════════════════════════

  ROLE: CUDA compute node (RTX 3050 Laptop GPU)
  GOAL: Maximize compute while maintaining determinism.

  PROTOCOL:
    1. Verify CUDA + driver
    2. Validate dataset + feature_dim
    3. Adaptive batch scaling → optimal_batch_3050
    4. Send GPU capacity score to authority
    5. Authority calculates shard proportion
    6. Join NCCL DDP (single-GPU fallback)
    7. Train: grad_clip=1.0, cosine_warm_restart, encoder_freeze
    8. Post-epoch telemetry
═══════════════════════════════════════════════════════════════════════
"""
import sys, os, time, json, hashlib, logging
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from torch.amp import autocast, GradScaler

from impl_v1.training.distributed.hash_utils import hash_model_weights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NODE-RTX3050] %(message)s",
)
log = logging.getLogger("cuda_node")

# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — VERIFY CUDA + DRIVER
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 1: Verify CUDA + Driver ═══")

assert torch.cuda.is_available(), "FATAL: CUDA not available — node cannot participate"
device = torch.device("cuda:0")

gpu_props = torch.cuda.get_device_properties(0)
gpu_name = gpu_props.name
gpu_vram_mb = gpu_props.total_memory / (1024 ** 2)
gpu_sm_count = gpu_props.multi_processor_count
gpu_compute = f"{gpu_props.major}.{gpu_props.minor}"
cuda_version = torch.version.cuda
driver_version = torch.cuda.get_device_capability(0)

node_info = {
    "node_id": f"RTX3050-{hashlib.sha256(gpu_name.encode()).hexdigest()[:8]}",
    "gpu_name": gpu_name,
    "vram_mb": round(gpu_vram_mb, 1),
    "sm_count": gpu_sm_count,
    "compute_capability": gpu_compute,
    "cuda_version": cuda_version,
    "driver_capability": f"{driver_version[0]}.{driver_version[1]}",
    "amp_supported": True,
    "fp16_supported": gpu_props.major >= 7,
    "tensor_cores": gpu_props.major >= 7,
}

log.info(f"  GPU: {gpu_name}")
log.info(f"  VRAM: {gpu_vram_mb:.0f} MB")
log.info(f"  SMs: {gpu_sm_count}, Compute: {gpu_compute}")
log.info(f"  CUDA: {cuda_version}")
log.info(f"  Node ID: {node_info['node_id']}")
log.info("  ✅ CUDA + Driver VERIFIED")

# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — VALIDATE DATASET + FEATURE_DIM
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 2: Validate Dataset + Feature Dim ═══")

# Training profile: deterministic (default) or fast
TRAINING_PROFILE = os.environ.get("YGB_TRAINING_PROFILE", "deterministic").lower()
FORCE_FRESH = os.environ.get("YGB_FORCE_FRESH_TRAIN", "0") == "1"

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
torch.manual_seed(42)
torch.cuda.manual_seed_all(42)
np.random.seed(42)

if TRAINING_PROFILE == "fast":
    torch.backends.cudnn.deterministic = False
    torch.backends.cudnn.benchmark = True
    torch.use_deterministic_algorithms(False)
    log.info(f"  Training profile: FAST (benchmark=True, deterministic=False)")
else:
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)
    log.info(f"  Training profile: DETERMINISTIC (benchmark=False, deterministic=True)")

if FORCE_FRESH:
    log.info("  ⚡ FORCE_FRESH_TRAIN=1 — starting from scratch (no checkpoint resume)")

from impl_v1.training.data.real_dataset_loader import (
    RealTrainingDataset,
    validate_dataset_integrity,
)

min_real_samples = int(os.environ.get("YGB_MIN_REAL_SAMPLES", "125000"))
preflight_ok, preflight_msg = validate_dataset_integrity(
    feature_dim=256,
    min_samples=min_real_samples,
    seed=42,
)
if not preflight_ok:
    raise RuntimeError(f"FATAL: Dataset preflight failed: {preflight_msg}")
log.info(f"  ✅ Dataset preflight: {preflight_msg}")

dataset = RealTrainingDataset(
    feature_dim=256,
    min_samples=min_real_samples,
    seed=42,
)
features = dataset._features_tensor.numpy()
labels = dataset._labels_tensor.numpy()

FEATURE_DIM = features.shape[1]
N_SAMPLES = len(labels)
N_CLASSES = len(np.unique(labels))
dataset_hash = hashlib.sha256(features.tobytes() + labels.tobytes()).hexdigest()[:16]

# Integrity checks
assert FEATURE_DIM == 256, f"FATAL: Expected feature_dim=256, got {FEATURE_DIM}"
assert N_CLASSES == 2, f"FATAL: Expected 2 classes, got {N_CLASSES}"
assert N_SAMPLES > 0, "FATAL: Empty dataset"
assert not np.isnan(features).any(), "FATAL: NaN in features"
assert not np.isinf(features).any(), "FATAL: Inf in features"

# Class balance check
class_counts = np.bincount(labels)
balance_ratio = min(class_counts) / max(class_counts)

dataset_meta = {
    "samples": N_SAMPLES,
    "feature_dim": FEATURE_DIM,
    "classes": N_CLASSES,
    "class_balance": round(balance_ratio, 4),
    "hash": dataset_hash,
    "dtype": str(features.dtype),
    "range": [round(float(features.min()), 4), round(float(features.max()), 4)],
}

log.info(f"  Samples: {N_SAMPLES}, Dim: {FEATURE_DIM}, Classes: {N_CLASSES}")
log.info(f"  Balance: {balance_ratio:.4f}")
log.info(f"  Hash: {dataset_hash}")
log.info("  ✅ Dataset VALIDATED")

# Train/test split
idx = np.random.permutation(N_SAMPLES)
split = int(0.8 * N_SAMPLES)
train_f, train_l = features[idx[:split]], labels[idx[:split]]
test_f, test_l = features[idx[split:]], labels[idx[split:]]

# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — ADAPTIVE BATCH SCALING → optimal_batch_3050
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 3: Adaptive Batch Scaling ═══")


class MaxPowerEncoder(nn.Module):
    """8-layer model with freezable encoder head."""
    def __init__(self, input_dim=256, freeze_encoder=False):
        super().__init__()
        # Encoder (layers 0-5, freezable)
        self.encoder = nn.Sequential(
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
        )
        # Classifier head (always trainable)
        self.head = nn.Sequential(
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
        if freeze_encoder:
            self.freeze_encoder()

    def freeze_encoder(self):
        for p in self.encoder.parameters():
            p.requires_grad = False
        log.info("  Encoder FROZEN (head-only training)")

    def unfreeze_encoder(self):
        for p in self.encoder.parameters():
            p.requires_grad = True

    def forward(self, x):
        return self.head(self.encoder(x))


def find_optimal_batch(model, feature_dim, device, real_features, real_labels, max_vram_pct=0.85):
    """
    Search for largest batch size that fits in VRAM using REAL dataset slices.
    Target: use up to max_vram_pct of total GPU memory.
    """
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    total_mem = torch.cuda.get_device_properties(0).total_memory
    target_mem = total_mem * max_vram_pct

    batch_sizes = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768]
    optimal = 256
    scaler = GradScaler('cuda')
    criterion = nn.CrossEntropyLoss()

    if len(real_features) == 0 or len(real_labels) == 0:
        raise RuntimeError("FATAL: No real data available for batch calibration")

    for bs in batch_sizes:
        try:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()

            effective_bs = min(bs, len(real_features))
            batch_x = torch.as_tensor(real_features[:effective_bs], device=device, dtype=torch.float32)
            batch_y = torch.as_tensor(real_labels[:effective_bs], device=device, dtype=torch.long)

            model.train()
            with autocast('cuda', dtype=torch.float16):
                out = model(batch_x)
                loss = criterion(out, batch_y)
            scaler.scale(loss).backward()

            peak = torch.cuda.max_memory_allocated()
            if peak < target_mem:
                optimal = effective_bs
                log.info(f"  batch={effective_bs:6d} → VRAM={peak / 1024**2:.0f} MB — OK")
            else:
                log.info(f"  batch={effective_bs:6d} → VRAM={peak / 1024**2:.0f} MB — EXCEEDS {max_vram_pct*100:.0f}%")
                break

            del batch_x, batch_y, out, loss
            model.zero_grad(set_to_none=True)

        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                log.info(f"  batch={bs:6d} → OOM")
                torch.cuda.empty_cache()
                break
            raise

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    return optimal


# Build model for batch calibration
_calib_model = MaxPowerEncoder(FEATURE_DIM, freeze_encoder=False).to(device)
param_count = sum(p.numel() for p in _calib_model.parameters())
trainable_count = sum(p.numel() for p in _calib_model.parameters() if p.requires_grad)
log.info(f"  Model: {param_count:,} params ({trainable_count:,} trainable)")

optimal_batch_3050 = find_optimal_batch(
    _calib_model,
    FEATURE_DIM,
    device,
    train_f,
    train_l,
    max_vram_pct=0.85,
)
log.info(f"  ✅ optimal_batch_3050 = {optimal_batch_3050}")

# Discard calibration model to prevent gradient/state leak into training
del _calib_model
torch.cuda.empty_cache()

# ═══════════════════════════════════════════════════════════════════════
# STEP 4 — GPU CAPACITY SCORE → AUTHORITY
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 4: GPU Capacity Score ═══")

# Benchmark: measure actual throughput at optimal batch
# Use a fresh model for benchmark to avoid calibration state leak
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
model = MaxPowerEncoder(FEATURE_DIM, freeze_encoder=False).to(device)
model.train()
scaler = GradScaler('cuda')
criterion = nn.CrossEntropyLoss()
optimizer = optim.AdamW(model.parameters(), lr=0.001)

bench_x = torch.randn(optimal_batch_3050, FEATURE_DIM, device=device)
bench_y = torch.randint(0, 2, (optimal_batch_3050,), device=device)

# Warmup
for _ in range(3):
    with autocast('cuda', dtype=torch.float16):
        out = model(bench_x)
        loss = criterion(out, bench_y)
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
    optimizer.zero_grad(set_to_none=True)
torch.cuda.synchronize()

# Timed run
t0 = time.perf_counter()
BENCH_ITERS = 20
for _ in range(BENCH_ITERS):
    with autocast('cuda', dtype=torch.float16):
        out = model(bench_x)
        loss = criterion(out, bench_y)
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
    optimizer.zero_grad(set_to_none=True)
torch.cuda.synchronize()
bench_time = time.perf_counter() - t0

throughput = (optimal_batch_3050 * BENCH_ITERS) / bench_time
vram_peak_bench = torch.cuda.max_memory_allocated() / (1024 ** 2)

# Capacity score: composite of VRAM + throughput + SM count
capacity_score = round(
    (gpu_vram_mb / 1000) * 0.3 +          # VRAM weight
    (throughput / 10000) * 0.5 +           # Throughput weight
    (gpu_sm_count / 10) * 0.2,            # SM weight
    4
)

capacity_report = {
    "node_id": node_info["node_id"],
    "gpu": gpu_name,
    "vram_mb": round(gpu_vram_mb, 1),
    "optimal_batch": optimal_batch_3050,
    "throughput_samples_sec": round(throughput, 2),
    "vram_peak_mb": round(vram_peak_bench, 2),
    "sm_count": gpu_sm_count,
    "capacity_score": capacity_score,
}

log.info(f"  Throughput: {throughput:.0f} samples/sec at batch={optimal_batch_3050}")
log.info(f"  VRAM peak: {vram_peak_bench:.0f} MB / {gpu_vram_mb:.0f} MB")
log.info(f"  Capacity score: {capacity_score}")
log.info("  ✅ Capacity report ready for authority")

del bench_x, bench_y, out, loss
torch.cuda.empty_cache()

# ═══════════════════════════════════════════════════════════════════════
# STEP 5 — AUTHORITY CALCULATES SHARD PROPORTION
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 5: Authority Shard Calculation ═══")

# Single-node: this node gets 100% of the shard
total_capacity = capacity_score  # Sum of all nodes in cluster
shard_proportion = capacity_score / total_capacity  # = 1.0 for single node

shard_samples = int(len(train_l) * shard_proportion)
log.info(f"  Shard proportion: {shard_proportion:.4f}")
log.info(f"  Shard samples: {shard_samples} / {len(train_l)}")
log.info("  ✅ Shard assigned")

# ═══════════════════════════════════════════════════════════════════════
# STEP 6 — JOIN NCCL DDP
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 6: DDP Initialization ═══")

gpu_count = torch.cuda.device_count()
USE_DDP = gpu_count > 1

if USE_DDP:
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel as DDP
    dist.init_process_group(backend="nccl")
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local_rank)
    device = torch.device(f"cuda:{local_rank}")
    log.info(f"  NCCL DDP initialized — rank {local_rank}/{gpu_count}")
else:
    local_rank = 0
    log.info(f"  Single GPU mode — DDP not required (gpu_count={gpu_count})")

world_size = gpu_count

# Re-initialize model fresh for training (deterministic init)
torch.manual_seed(42)
torch.cuda.manual_seed_all(42)
model = MaxPowerEncoder(FEATURE_DIM, freeze_encoder=False).to(device)

if USE_DDP:
    model = DDP(model, device_ids=[local_rank])

log.info(f"  World size: {world_size}")
log.info("  ✅ DDP ready")

# ═══════════════════════════════════════════════════════════════════════
# STEP 7 — TRAINING: grad_clip=1.0, cosine_warm_restart, encoder_freeze
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 7: Training Protocol ═══")

GRAD_CLIP = 1.0
EPOCHS = 30
GRAD_ACCUM = 8
ENCODER_FREEZE_EPOCHS = 0  # Set > 0 to freeze encoder for first N epochs
T_0 = 10          # Cosine warm restart period
T_MULT = 2        # Period multiplier after each restart
ETA_MIN = 1e-6    # Minimum LR
WEIGHT_HASH_MODE = os.environ.get("YGB_WEIGHT_HASH_MODE", "sampled").strip().lower()
EVAL_EVERY = max(1, int(os.environ.get("YGB_EVAL_EVERY", "1")))
MAX_EVAL_SAMPLES = max(0, int(os.environ.get("YGB_MAX_EVAL_SAMPLES", "4096")))

optimizer = optim.AdamW(
    filter(lambda p: p.requires_grad, model.parameters()),
    lr=0.001, weight_decay=1e-4,
)
scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
    optimizer, T_0=T_0, T_mult=T_MULT, eta_min=ETA_MIN,
)
criterion = nn.CrossEntropyLoss()
scaler = GradScaler('cuda')

# Build DataLoader with optimal batch
train_ds = TensorDataset(
    torch.tensor(train_f[:shard_samples], dtype=torch.float32),
    torch.tensor(train_l[:shard_samples], dtype=torch.long),
)
# Seeded DataLoader generator keeps shuffle deterministic without first-batch probe overhead
_dl_num_workers = 2 if sys.platform == 'win32' else 4
_dl_persistent = _dl_num_workers > 0
_dl_prefetch = 2 if _dl_num_workers > 0 else None
_dl_generator = torch.Generator()
_dl_generator.manual_seed(42)


def _seed_worker(worker_id):
    worker_seed = 42 + worker_id
    np.random.seed(worker_seed)
    torch.manual_seed(worker_seed)


try:
    train_loader = DataLoader(
        train_ds, batch_size=optimal_batch_3050, shuffle=True,
        num_workers=_dl_num_workers, pin_memory=True, drop_last=False,
        persistent_workers=_dl_persistent,
        prefetch_factor=_dl_prefetch,
        generator=_dl_generator,
        worker_init_fn=_seed_worker,
    )
    log.info(f"  DataLoader: num_workers={_dl_num_workers}, persistent={_dl_persistent}")
except Exception as e:
    log.warning(f"  DataLoader with workers={_dl_num_workers} failed: {e}")
    log.warning(f"  Retrying with num_workers=0")
    _dl_num_workers = 0
    _dl_persistent = False
    _dl_prefetch = None
    train_loader = DataLoader(
        train_ds, batch_size=optimal_batch_3050, shuffle=True,
        num_workers=0, pin_memory=True, drop_last=False,
        generator=_dl_generator,
    )
    log.info(f"  DataLoader: num_workers=0 (fallback)")

log.info(f"  Batch: {optimal_batch_3050}, Grad accum: {GRAD_ACCUM}")
log.info(f"  Effective batch: {optimal_batch_3050 * GRAD_ACCUM}")
log.info(f"  Grad clip: {GRAD_CLIP}")
log.info(f"  Scheduler: CosineAnnealingWarmRestarts(T_0={T_0}, T_mult={T_MULT})")
log.info(f"  Encoder freeze epochs: {ENCODER_FREEZE_EPOCHS}")
log.info(f"  Weight hash mode: {WEIGHT_HASH_MODE}")

torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()

# Pre-allocate test tensors on GPU (avoid per-epoch CPU→GPU transfer)
if MAX_EVAL_SAMPLES > 0 and len(test_l) > MAX_EVAL_SAMPLES:
    eval_f = test_f[:MAX_EVAL_SAMPLES]
    eval_l = test_l[:MAX_EVAL_SAMPLES]
else:
    eval_f = test_f
    eval_l = test_l

log.info(f"  Eval cadence: every {EVAL_EVERY} epoch(s), samples={len(eval_l)}")

test_features_gpu = torch.tensor(eval_f, dtype=torch.float32, device=device)
test_labels_gpu = torch.tensor(eval_l, dtype=torch.long, device=device)

epoch_reports = []
t_total = time.perf_counter()

for epoch in range(EPOCHS):
    ep_start = time.perf_counter()

    # Encoder freeze logic
    raw_model = model.module if USE_DDP else model
    if ENCODER_FREEZE_EPOCHS > 0:
        if epoch < ENCODER_FREEZE_EPOCHS:
            raw_model.freeze_encoder()
        elif epoch == ENCODER_FREEZE_EPOCHS:
            raw_model.unfreeze_encoder()
            # Re-add encoder params to optimizer
            optimizer = optim.AdamW(
                filter(lambda p: p.requires_grad, model.parameters()),
                lr=0.001, weight_decay=1e-4,
            )
            scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
                optimizer, T_0=T_0, T_mult=T_MULT, eta_min=ETA_MIN,
            )
            log.info(f"  Epoch {epoch+1}: Encoder UNFROZEN, optimizer re-initialized")

    model.train()
    # Accumulate metrics on GPU to avoid per-batch GPU→CPU sync stalls
    total_loss_gpu = torch.zeros(1, device=device)
    total_correct_gpu = torch.zeros(1, dtype=torch.long, device=device)
    total_samples = 0
    max_grad_norm = 0.0
    optimizer.zero_grad(set_to_none=True)

    for b_idx, (bx, by) in enumerate(train_loader):
        bx = bx.to(device, non_blocking=True)
        by = by.to(device, non_blocking=True)

        with autocast('cuda', dtype=torch.float16):
            logits = model(bx)
            loss = criterion(logits, by) / GRAD_ACCUM

        scaler.scale(loss).backward()

        if (b_idx + 1) % GRAD_ACCUM == 0:
            # Unscale before clipping
            scaler.unscale_(optimizer)
            grad_norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), max_norm=GRAD_CLIP
            )
            max_grad_norm = max(max_grad_norm, grad_norm.item())
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)

        total_loss_gpu += loss.detach().float() * GRAD_ACCUM * bx.size(0)
        total_correct_gpu += (logits.detach().float().argmax(1) == by).sum()
        total_samples += bx.size(0)

    # Flush remaining
    if (b_idx + 1) % GRAD_ACCUM != 0:
        scaler.unscale_(optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(
            model.parameters(), max_norm=GRAD_CLIP
        )
        max_grad_norm = max(max_grad_norm, grad_norm.item())
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)

    scheduler.step(epoch + 1)

    # Eval (using pre-allocated GPU tensors + AMP)
    should_eval = ((epoch + 1) % EVAL_EVERY == 0) or (epoch == EPOCHS - 1)
    if should_eval:
        model.eval()
        with torch.no_grad():
            with autocast('cuda', dtype=torch.float16):
                test_logits = model(test_features_gpu)
            test_acc = (test_logits.argmax(1) == test_labels_gpu).float().mean().item()
            del test_logits
    else:
        test_acc = epoch_reports[-1]["test_acc"] if epoch_reports else 0.0

    ep_time = time.perf_counter() - ep_start
    # Single GPU→CPU sync point per epoch (instead of per-batch)
    avg_loss = total_loss_gpu.item() / max(total_samples, 1)
    train_acc = total_correct_gpu.item() / max(total_samples, 1)
    vram_now = torch.cuda.max_memory_allocated() / (1024 ** 2)
    sps = total_samples / max(ep_time, 0.001)
    lr_now = optimizer.param_groups[0]["lr"]

    log.info(
        f"  E{epoch+1:3d}/{EPOCHS}: "
        f"train={train_acc:.4f} test={test_acc:.4f} "
        f"loss={avg_loss:.4f} "
        f"grad={max_grad_norm:.3f} "
        f"lr={lr_now:.2e} "
        f"VRAM={vram_now:.0f}MB "
        f"speed={sps:.0f}s/s "
        f"time={ep_time:.1f}s"
    )

    epoch_reports.append({
        "epoch": epoch + 1,
        "train_acc": round(train_acc, 4),
        "test_acc": round(test_acc, 4),
        "loss": round(avg_loss, 6),
        "max_grad_norm": round(max_grad_norm, 4),
        "lr": round(lr_now, 8),
        "vram_mb": round(vram_now, 2),
        "samples_per_sec": round(sps, 2),
        "epoch_time_sec": round(ep_time, 2),
    })

total_time = time.perf_counter() - t_total
vram_peak_final = torch.cuda.max_memory_allocated() / (1024 ** 2)
final_sps = (total_samples * EPOCHS) / max(total_time, 0.001)

log.info("  ✅ Training COMPLETE")

# ═══════════════════════════════════════════════════════════════════════
# STEP 8 — POST-EPOCH TELEMETRY REPORT
# ═══════════════════════════════════════════════════════════════════════
log.info("═══ STEP 8: Post-Epoch Telemetry ═══")

# Compute merged weight hash
raw_model = model.module if USE_DDP else model
merged_weight_hash = hash_model_weights(raw_model, mode=WEIGHT_HASH_MODE)[:16]

# Determinism check (3 single-epoch runs)
log.info("  Running determinism verification (3 runs)...")
det_hashes = []
for run_i in range(3):
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    np.random.seed(42)
    # Create a fresh DataLoader with a seeded generator for deterministic shuffle
    _det_gen = torch.Generator()
    _det_gen.manual_seed(42)
    _det_loader = DataLoader(
        train_ds, batch_size=optimal_batch_3050, shuffle=True,
        num_workers=0, pin_memory=True, drop_last=False,
        generator=_det_gen,
    )
    m = MaxPowerEncoder(FEATURE_DIM).to(device)
    opt = optim.AdamW(m.parameters(), lr=0.001, weight_decay=1e-4)
    sc = GradScaler('cuda')
    cr = nn.CrossEntropyLoss()
    m.train()
    opt.zero_grad(set_to_none=True)
    for b_idx, (bx, by) in enumerate(_det_loader):
        bx, by = bx.to(device, non_blocking=True), by.to(device, non_blocking=True)
        with autocast('cuda', dtype=torch.float16):
            out = m(bx)
            l = cr(out, by) / GRAD_ACCUM
        sc.scale(l).backward()
        if (b_idx + 1) % GRAD_ACCUM == 0:
            sc.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(m.parameters(), max_norm=GRAD_CLIP)
            sc.step(opt)
            sc.update()
            opt.zero_grad(set_to_none=True)
    if (b_idx + 1) % GRAD_ACCUM != 0:
        sc.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(m.parameters(), max_norm=GRAD_CLIP)
        sc.step(opt)
        sc.update()
        opt.zero_grad(set_to_none=True)
    wh = hash_model_weights(m, mode=WEIGHT_HASH_MODE)[:16]
    det_hashes.append(wh)
    log.info(f"    Run {run_i+1}: {wh}")
    del m, opt, sc, cr, _det_loader, _det_gen

det_match = len(set(det_hashes)) == 1
log.info(f"  Determinism: {'PASS' if det_match else 'FAIL'}")

# Dataset hash consensus (single node = self-consensus)
dataset_hash_consensus = dataset_hash

# Final telemetry
telemetry = {
    "world_size": world_size,
    "total_samples_per_sec": round(final_sps, 2),
    "per_node_batch": optimal_batch_3050,
    "effective_batch": optimal_batch_3050 * GRAD_ACCUM,
    "merged_weight_hash": merged_weight_hash,
    "dataset_hash_consensus": dataset_hash_consensus,
    "node_info": node_info,
    "capacity_report": capacity_report,
    "dataset_meta": dataset_meta,
    "training_config": {
        "epochs": EPOCHS,
        "grad_clip": GRAD_CLIP,
        "grad_accumulation": GRAD_ACCUM,
        "scheduler": "CosineAnnealingWarmRestarts",
        "T_0": T_0,
        "T_mult": T_MULT,
        "eta_min": ETA_MIN,
        "encoder_freeze_epochs": ENCODER_FREEZE_EPOCHS,
        "amp_enabled": True,
        "training_profile": TRAINING_PROFILE,
        "cudnn_benchmark": torch.backends.cudnn.benchmark,
        "cudnn_deterministic": torch.backends.cudnn.deterministic,
        "force_fresh_train": FORCE_FRESH,
        "num_workers": _dl_num_workers,
        "persistent_workers": _dl_persistent,
        "weight_hash_mode": WEIGHT_HASH_MODE,
        "eval_every": EVAL_EVERY,
        "eval_samples": int(test_labels_gpu.numel()),
    },
    "results": {
        "total_time_sec": round(total_time, 2),
        "vram_peak_mb": round(vram_peak_final, 2),
        "vram_utilization_pct": round(vram_peak_final / gpu_vram_mb * 100, 1),
        "final_train_acc": epoch_reports[-1]["train_acc"],
        "final_test_acc": epoch_reports[-1]["test_acc"],
        "final_loss": epoch_reports[-1]["loss"],
        "model_params": param_count,
    },
    "determinism": {
        "match": det_match,
        "hash_run1": det_hashes[0],
        "hash_run2": det_hashes[1],
        "hash_run3": det_hashes[2],
    },
    "epoch_reports": epoch_reports,
}

# Save
os.makedirs("reports", exist_ok=True)
with open("reports/speed_telemetry.json", "w") as f:
    json.dump(telemetry, f, indent=2)
with open("reports/training_session_result.json", "w") as f:
    json.dump(telemetry, f, indent=2)

log.info(f"  Weight hash: {merged_weight_hash}")
log.info(f"  Dataset consensus: {dataset_hash_consensus}")
log.info(f"  Total time: {total_time:.1f}s")
log.info(f"  VRAM peak: {vram_peak_final:.0f} MB / {gpu_vram_mb:.0f} MB ({vram_peak_final/gpu_vram_mb*100:.1f}%)")
log.info(f"  Throughput: {final_sps:.0f} samples/sec")
log.info(f"  Final accuracy: {epoch_reports[-1]['test_acc']:.4f}")

print(f"\n{'='*60}")
print("NODE RTX3050 — FINAL TELEMETRY")
print(f"{'='*60}")
print(json.dumps({
    "world_size": telemetry["world_size"],
    "total_samples_per_sec": telemetry["total_samples_per_sec"],
    "per_node_batch": telemetry["per_node_batch"],
    "merged_weight_hash": telemetry["merged_weight_hash"],
    "dataset_hash_consensus": telemetry["dataset_hash_consensus"],
    "vram_peak_mb": telemetry["results"]["vram_peak_mb"],
    "vram_utilization_pct": telemetry["results"]["vram_utilization_pct"],
    "determinism_match": telemetry["determinism"]["match"],
    "final_accuracy": telemetry["results"]["final_test_acc"],
}, indent=2))
