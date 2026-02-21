# =========================================================
# setup.ps1 — YGB Clone Auto-Bootstrap (Windows)
# =========================================================
# When user clones repo, this script:
#   1. Detects GPU
#   2. Attempts cluster join
#   3. Validates dataset manifest
#   4. Runs adaptive batch scaling
#   5. Saves device baseline
#   6. Registers node with authority
#   7. Begins distributed training (or standalone)
# =========================================================

Write-Host "=========================================="
Write-Host "  YGB Auto-Bootstrap (Windows)"
Write-Host "=========================================="

$env:PYTHONPATH = (Get-Location).Path
$env:CUBLAS_WORKSPACE_CONFIG = ":4096:8"
$env:YGB_CLUSTER_MODE = if ($env:YGB_CLUSTER_MODE) { $env:YGB_CLUSTER_MODE } else { "auto" }

Write-Host ""
Write-Host "[1/8] Classifying device..."
python -c "
from impl_v1.training.distributed.device_classifier import classify_device
c = classify_device()
print(f'  Device: {c.device_name}')
print(f'  Backend: {c.backend}')
print(f'  Role: {c.role}')
print(f'  GPUs: {c.gpu_count}')
print(f'  DDP eligible: {c.ddp_eligible}')
print(f'  Can train: {c.can_train}')
"

Write-Host ""
Write-Host "[2/7] Attempting cluster join..."
python -c "
from impl_v1.training.distributed.auto_register import auto_register
r = auto_register()
print(f'  Mode: {r.mode}')
print(f'  Joined: {r.cluster_joined}')
print(f'  GPUs: {r.gpu_count}')
"

Write-Host ""
Write-Host "[3/7] Validating dataset manifest..."
python -c "
from impl_v1.training.safety.dataset_manifest import validate_manifest
import os
if os.path.exists('secure_data/dataset_manifest.json'):
    v, reason, _ = validate_manifest()
    print(f'  Valid: {v} ({reason})')
else:
    print('  No manifest - will create on first training')
"

Write-Host ""
Write-Host "[4/7] Running adaptive batch scaling..."
python -c "
import os; os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
from impl_v1.training.safety.scaling_safety import safe_adaptive_scale
batch = safe_adaptive_scale(starting_batch=1024)
print(f'  Optimal batch: {batch}')
"

Write-Host ""
Write-Host "[5/7] Saving device baseline..."
python -c "
from impl_v1.training.config.device_baselines import DeviceBaselineStore
store = DeviceBaselineStore()
bl = store.calibrate_current_device()
if bl:
    print(f'  Device: {bl.device_name}')
    print(f'  Batch: {bl.optimal_batch_size}')
    print(f'  SPS: {bl.samples_per_sec:.0f}')
else:
    print('  No GPU - skipped')
"

Write-Host ""
Write-Host "[6/7] Registering node..."
python -c "
from impl_v1.training.distributed.auto_register import load_state
s = load_state()
if s:
    print(f'  Node: {s.node_id[:16]}...')
    print(f'  Mode: {s.mode}')
else:
    print('  No state')
"

Write-Host ""
Write-Host "[7/7] Ready for training"
Write-Host "=========================================="
Write-Host "  Bootstrap complete!"
Write-Host "  Run: python run_real_training.py"
Write-Host "=========================================="
