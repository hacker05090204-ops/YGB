"""
═══════════════════════════════════════════════════════════════════════
  run_cluster_authority.py — Execute 7-Phase Cluster Authority Protocol
═══════════════════════════════════════════════════════════════════════

  Runs all 7 phases using real RTX 3050 telemetry data.
  Outputs structured JSON to reports/cluster_authority_report.json.
═══════════════════════════════════════════════════════════════════════
"""
import sys, os, json, hashlib, logging, time

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AUTHORITY] %(message)s",
)
log = logging.getLogger("cluster_authority_runner")

from impl_v1.training.distributed.cluster_authority import (
    ClusterAuthority,
    NodeRegistration,
    NodeStatus,
)


# ═══════════════════════════════════════════════════════════════════════
# LOAD TELEMETRY FROM PREVIOUS NODE RUN
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ Loading RTX 3050 telemetry ═══")

telemetry_path = os.path.join("reports", "speed_telemetry.json")
if os.path.exists(telemetry_path):
    with open(telemetry_path) as f:
        telem = json.load(f)
    log.info(f"  Loaded telemetry from {telemetry_path}")
else:
    log.error(f"  Telemetry not found at {telemetry_path} — run run_real_training.py first")
    sys.exit(1)

node_info = telem["node_info"]
capacity_report = telem["capacity_report"]
dataset_meta = telem["dataset_meta"]

# Parse CUDA version
cuda_parts = node_info["cuda_version"].split(".")
cuda_major = int(cuda_parts[0])
cuda_minor = int(cuda_parts[1]) if len(cuda_parts) > 1 else 0

# Parse compute capability
cc_parts = node_info["compute_capability"].split(".")
cc_major = int(cc_parts[0])
cc_minor = int(cc_parts[1]) if len(cc_parts) > 1 else 0

# Parse driver capability
drv_parts = node_info["driver_capability"].split(".")
drv_major = int(drv_parts[0])
drv_minor = int(drv_parts[1]) if len(drv_parts) > 1 else 0

# Build label distribution from dataset
from impl_v1.training.data.scaled_dataset import DatasetConfig
from impl_v1.training.data.real_dataset_loader import RealTrainingDataset

config = DatasetConfig(total_samples=50000)
dataset = RealTrainingDataset(config=config)
features = dataset._features_tensor.numpy()
labels = dataset._labels_tensor.numpy()

unique_labels, counts = np.unique(labels, return_counts=True)
label_dist = {str(int(k)): int(v) for k, v in zip(unique_labels, counts)}


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — CUDA VERIFICATION
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  CLUSTER AUTHORITY — 7-PHASE PROTOCOL")
print(f"{'='*60}\n")

log.info("═══ PHASE 1: CUDA Verification ═══")

authority = ClusterAuthority(
    reference_cuda_major=cuda_major,
    reference_compute_major=cc_major,
    reference_compute_minor=cc_minor,
    reference_driver_major=drv_major,
    reference_driver_minor=drv_minor,
)

primary_node = NodeRegistration(
    node_id=node_info["node_id"],
    gpu_name=node_info["gpu_name"],
    cuda_major=cuda_major,
    cuda_minor=cuda_minor,
    compute_major=cc_major,
    compute_minor=cc_minor,
    fp16_supported=node_info["fp16_supported"],
    driver_major=drv_major,
    driver_minor=drv_minor,
    vram_mb=node_info["vram_mb"],
    sm_count=node_info["sm_count"],
    optimal_batch=capacity_report["optimal_batch"],
    capacity_score=capacity_report["capacity_score"],
    throughput_sps=capacity_report["throughput_samples_sec"],
    dataset_hash=dataset_meta["hash"],
    sample_count=dataset_meta["samples"],
    feature_dim=dataset_meta["feature_dim"],
    label_distribution=label_dist,
)

result = authority.verify_cuda_node(primary_node)
log.info(f"  Node {result.node_id}: {result.status.value}")

# Simulate a second node attempt with matching specs (for multi-node demo)
sim_node = NodeRegistration(
    node_id="RTX2050-sim-01",
    gpu_name="NVIDIA GeForce RTX 2050 (Simulated)",
    cuda_major=cuda_major,
    cuda_minor=cuda_minor,
    compute_major=cc_major,
    compute_minor=cc_minor,
    fp16_supported=True,
    driver_major=drv_major,
    driver_minor=drv_minor,
    vram_mb=2048.0,
    sm_count=12,
    optimal_batch=8192,
    capacity_score=3.5,
    throughput_sps=45000.0,
    dataset_hash=dataset_meta["hash"],
    sample_count=dataset_meta["samples"],
    feature_dim=dataset_meta["feature_dim"],
    label_distribution=label_dist,
)

result2 = authority.verify_cuda_node(sim_node)
log.info(f"  Node {result2.node_id}: {result2.status.value}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 — DATASET LOCK
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ PHASE 2: Dataset Lock ═══")

passed, reason = authority.enforce_dataset_lock()
log.info(f"  Result: {'PASS' if passed else 'FAIL'} — {reason}")

if not passed:
    log.error("  FATAL: Dataset lock failed — aborting")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 — WORLD SIZE LOCK
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ PHASE 3: World Size Lock ═══")

ok, ws = authority.lock_world_size()
log.info(f"  Locked world_size = {ws}")

shard_props = authority.get_shard_proportions()
for nid, prop in shard_props.items():
    log.info(f"  Shard: {nid} → {prop:.4f} ({prop*100:.1f}%)")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4 — SCALING LIMIT
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ PHASE 4: Scaling Limit ═══")

single_sps = capacity_report["throughput_samples_sec"]
cluster_sps = telem["total_samples_per_sec"]

passed, eff, disabled = authority.enforce_scaling_limit(
    single_gpu_sps=single_sps,
    cluster_sps=cluster_sps,
)
log.info(f"  Scaling efficiency: {eff}")
log.info(f"  Disabled nodes: {disabled if disabled else 'none'}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — MPS SAFETY
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ PHASE 5: MPS Safety ═══")

# Simulate an MPS node delta check
mps_ok, mps_reason = authority.validate_mps_delta(
    node_id="MPS-M1-sim",
    delta_norm=3.2,
    loss_before=0.5,
    loss_after=0.42,
    val_acc_before=0.92,
    val_acc_after=0.91,
)
log.info(f"  MPS check: {'PASS' if mps_ok else 'FAIL'} — {mps_reason}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 6 — DATA QUALITY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ PHASE 6: Data Quality Enforcement ═══")

# Quick sanity accuracy: train a small model for 1 epoch
import torch
import torch.nn as nn

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
torch.manual_seed(42)
np.random.seed(42)

# Use a subset for sanity check
idx = np.random.permutation(len(labels))
n_sanity = min(5000, len(labels))
sx = torch.tensor(features[idx[:n_sanity]], dtype=torch.float32)
sy = torch.tensor(labels[idx[:n_sanity]], dtype=torch.long)

sanity_model = nn.Sequential(
    nn.Linear(features.shape[1], 64), nn.ReLU(),
    nn.Linear(64, 2),
)
opt = torch.optim.Adam(sanity_model.parameters(), lr=0.01)
crit = nn.CrossEntropyLoss()

sanity_model.train()
for _ in range(5):
    opt.zero_grad()
    loss = crit(sanity_model(sx), sy)
    loss.backward()
    opt.step()

sanity_model.eval()
with torch.no_grad():
    preds = sanity_model(sx).argmax(1)
    sanity_acc = (preds == sy).float().mean().item()

log.info(f"  Sanity accuracy: {sanity_acc:.4f}")

dq_passed, dq_report = authority.enforce_data_quality(
    features, labels, sanity_accuracy=sanity_acc,
)
log.info(f"  Data quality: {'PASS' if dq_passed else 'BLOCKED'}")
for k, v in dq_report.items():
    if k != "block_reasons":
        log.info(f"    {k}: {v}")


# ═══════════════════════════════════════════════════════════════════════
# START TRAINING
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ Starting Training ═══")

ok, msg = authority.start_training()
log.info(f"  {msg}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 7 — METRIC REPORTING (simulated epoch)
# ═══════════════════════════════════════════════════════════════════════

log.info("═══ PHASE 7: Metric Reporting ═══")

# Use existing telemetry data
weight_hash = telem.get("merged_weight_hash", "unknown")
dataset_consensus = telem.get("dataset_hash_consensus", "unknown")

per_node_batch = {}
for nid in authority.nodes:
    per_node_batch[nid] = authority.nodes[nid].optimal_batch

authority.report_epoch_metrics(
    epoch=1,
    cluster_sps=cluster_sps,
    per_node_batch=per_node_batch,
    merged_weight_hash=weight_hash,
    dataset_hash_consensus=dataset_consensus,
    scaling_efficiency=eff if isinstance(eff, float) else 1.0,
)


# ═══════════════════════════════════════════════════════════════════════
# SAVE REPORT
# ═══════════════════════════════════════════════════════════════════════

report = authority.get_full_report()

os.makedirs("reports", exist_ok=True)
report_path = os.path.join("reports", "cluster_authority_report.json")
with open(report_path, "w") as f:
    json.dump(report, f, indent=2)

log.info(f"  Report saved to {report_path}")

# Summary output
print(f"\n{'='*60}")
print("  CLUSTER AUTHORITY — FINAL REPORT")
print(f"{'='*60}")
summary = {
    "world_size": report["authority_state"]["locked_world_size"],
    "training_active": report["authority_state"]["training_active"],
    "aborted": report["authority_state"]["aborted"],
    "nodes_registered": len(report["nodes"]),
    "dataset_locked": report["dataset_lock"] is not None,
    "dataset_hash": report["dataset_lock"]["dataset_hash"] if report["dataset_lock"] else None,
    "shard_proportions": report["shard_proportions"],
    "data_quality_passed": dq_passed,
    "sanity_accuracy": round(sanity_acc, 4),
    "scaling_efficiency": eff,
    "mps_check": "PASS" if mps_ok else "FAIL",
    "epoch_metrics_logged": len(report["epoch_logs"]),
}
print(json.dumps(summary, indent=2))
