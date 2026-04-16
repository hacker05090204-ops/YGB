# YBG Quick Start Guide

## System Overview

YBG is a **3 billion parameter Mixture-of-Experts (MoE)** vulnerability intelligence system with:
- **23 specialized experts** (130M params each)
- **80+ vulnerability fields** covered
- **9 data sources** (NVD, CISA, ExploitDB, etc.)
- **Hardware-agnostic** (works on Colab, RTX 2050, CPU, etc.)

## Current Status: 90% Complete ✅

The core system is operational. See `SYSTEM_STATUS.md` for details.

## Quick Commands

### Check System Health
```bash
python run_self_analysis.py
```

### Test Device Configuration
```bash
python scripts/device_manager.py
```

### View Expert Training Queue
```python
from scripts.expert_task_queue import ExpertTaskQueue
ExpertTaskQueue().print_status()
```

### Train a Single Expert (Manual)
```python
import os
os.environ['YGB_USE_MOE'] = 'true'

from training_controller import train_single_expert

# Train expert 0 (web_vulns)
result = train_single_expert(
    expert_id=0,
    field_name="web_vulns",
    max_epochs=20,
    patience=5
)

print(f"Val F1: {result.val_f1:.4f}")
print(f"Status: {result.status}")
print(f"Checkpoint: {result.checkpoint_path}")
```

## For Google Colab

```python
# Cell 1: Setup
!git clone https://github.com/hacker05090204-ops/YGB-final.git
%cd YGB-final
!pip install -q agentlightning safetensors transformers torch scikit-learn scipy

import os
os.environ["YGB_USE_MOE"] = "true"
os.environ["YGB_ENV"] = "development"

# Cell 2: Check device
from scripts.device_manager import get_config, print_config
cfg = get_config()
print_config(cfg)

# Cell 3: Train an expert
from scripts.expert_task_queue import ExpertTaskQueue
from training_controller import train_single_expert

queue = ExpertTaskQueue()
expert = queue.claim_next_expert()

if expert:
    print(f"Training expert {expert.expert_id}: {expert.field_name}")
    result = train_single_expert(expert.expert_id, expert.field_name)
    print(f"Done: val_f1={result.val_f1:.4f}")
    queue.release_expert(expert.expert_id, result.val_f1, 
                        result.checkpoint_path, success=result.val_f1 >= 0.50)
else:
    print("All experts claimed or trained!")
```

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                     YBG SYSTEM ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   9 Scrapers │───▶│  Validator   │───▶│    Router    │ │
│  │  (NVD, CISA, │    │  (Quality +  │    │  (Assign to  │ │
│  │   ExploitDB) │    │   Purity)    │    │   Expert)    │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                                         │         │
│         ▼                                         ▼         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           SafeTensors Feature Store                  │  │
│  │         (267-dim features per CVE sample)            │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              MoE Classifier (3B params)              │  │
│  │  ┌────────┐ ┌────────┐       ┌────────┐             │  │
│  │  │Expert 0│ │Expert 1│  ...  │Expert22│             │  │
│  │  │ 130M   │ │ 130M   │       │ 130M   │             │  │
│  │  │Web XSS │ │  SQLi  │       │General │             │  │
│  │  └────────┘ └────────┘       └────────┘             │  │
│  │              ▲                                        │  │
│  │              │ Top-K=2 Routing                       │  │
│  │         ┌────┴────┐                                  │  │
│  │         │ Router  │                                  │  │
│  │         │ Network │                                  │  │
│  │         └─────────┘                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Training with Anti-Overfitting               │  │
│  │  • EWC (Elastic Weight Consolidation)                │  │
│  │  • Class Balancing                                   │  │
│  │  • Label Smoothing                                   │  │
│  │  • Early Stopping                                    │  │
│  │  • AMP (Mixed Precision)                             │  │
│  │  • RL Feedback (Real Outcomes)                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │      Per-Expert Checkpoints (SafeTensors)            │  │
│  │      Compressed 4:1 ratio (1TB → 250GB)              │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

### Core Training
- `training_controller.py` - Main training orchestrator
- `impl_v1/phase49/moe/` - MoE architecture
- `backend/training/incremental_trainer.py` - Training loop with protections

### Data Pipeline
- `backend/ingestion/autograbber.py` - Multi-source CVE fetcher
- `backend/ingestion/scrapers/` - 9 scraper implementations
- `backend/training/safetensors_store.py` - Feature storage

### Infrastructure
- `scripts/device_manager.py` - Hardware auto-detection
- `scripts/expert_task_queue.py` - Distributed training coordination
- `backend/auth/auth_guard.py` - Security layer

## Environment Variables

```bash
# Required
export JWT_SECRET="your-32-char-minimum-secret-here"
export YGB_VIDEO_JWT_SECRET="your-video-jwt-secret-32chars"
export YGB_LEDGER_KEY="your-ledger-encryption-key"

# Optional
export YGB_USE_MOE="true"              # Enable MoE (default: true)
export YGB_ENV="development"            # development | production
export YGB_REQUIRE_ENCRYPTION="false"   # For testing only
```

## Troubleshooting

### "JWT_SECRET must be >= 32 chars"
Set a proper JWT secret:
```bash
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

### "MoE import FAILED"
Ensure you're in the repo root:
```bash
cd YGB-final
python -c "from impl_v1.phase49.moe import MoEClassifier; print('OK')"
```

### "CUDA out of memory"
The system auto-detects VRAM and adjusts batch size. If still failing:
```python
from scripts.device_manager import get_config
cfg = get_config()
print(f"Detected batch size: {cfg.batch_size}")
# Manually reduce if needed
```

### Slow training on CPU
Expected. CPU training takes 48-72 hours per expert. Use Colab or GPU.

## Next Steps

1. **Review Status:** Read `SYSTEM_STATUS.md`
2. **Run Analysis:** `python run_self_analysis.py`
3. **Test Device:** `python scripts/device_manager.py`
4. **Train Expert:** Follow Colab example above
5. **Monitor Progress:** Check expert queue status

## Support

- **Documentation:** See `SYSTEM_STATUS.md` for architecture details
- **Issues:** Check self-analysis output for specific problems
- **Performance:** Device manager auto-tunes for your hardware

---

**Ready to train?** Start with the Colab example above or run `python scripts/device_manager.py` to see your hardware configuration.
