# YBG Quick Start Guide

**Status:** Phases 0-2 Complete ✅  
**Ready for:** Google Colab, Lightning.ai, Kaggle, Paperspace

---

## ⚡ Quick Test (30 seconds)

```bash
# Run comprehensive test suite
python scripts/test_phase0_1_2.py
```

**Expected Output:**
```
🎉 ALL TESTS PASSED! Phases 0-2 are fully operational.
Total: 8 tests | Passed: 8 | Failed: 0
```

---

## 🔍 Check Your Hardware

```bash
python scripts/device_manager.py
```

**Example Output:**
```
==================================================
YBG DEVICE CONFIGURATION
==================================================
  Device:   Tesla T4
  VRAM:     16.0GB
  Batch:    32
  Precision: bf16
  GradCkpt: False
  MaxModel: 3.0B params
  Platform: Google Colab | CUDA 7.5 | 16.0GB
==================================================
```

---

## 🚀 Google Colab Setup (2 minutes)

### Step 1: Open Colab
Go to: https://colab.research.google.com/

### Step 2: Paste Setup Code
```python
# Cell 1: Environment setup
import os, subprocess, sys

# Clone repository
if not os.path.exists("YGB-final"):
    subprocess.run(["git", "clone",
                   "https://github.com/hacker05090204-ops/YGB-final.git"])
os.chdir("YGB-final")
subprocess.run(["git", "pull"])

# Install dependencies
subprocess.run([sys.executable, "-m", "pip", "install",
               "agentlightning", "safetensors", "transformers",
               "torch", "scikit-learn", "scipy", "-q"])

# Set environment
os.environ["YGB_USE_MOE"] = "true"
os.environ["YGB_ENV"] = "development"

# Detect device
from scripts.device_manager import get_config, print_config
cfg = get_config()
print_config(cfg)
```

### Step 3: Run Tests
```python
# Cell 2: Run tests
!python scripts/test_phase0_1_2.py
```

---

## ⚡ Lightning.ai Setup

```python
# Install dependencies
!pip install agentlightning safetensors transformers torch scikit-learn scipy -q

# Clone repository
!git clone https://github.com/hacker05090204-ops/YGB-final.git
%cd YGB-final

# Set environment
import os
os.environ["YGB_USE_MOE"] = "true"

# Check hardware
from scripts.device_manager import get_config, print_config
cfg = get_config()
print_config(cfg)

# Run tests
!python scripts/test_phase0_1_2.py
```

---

## 📊 What's Working

### ✅ Phase 0: Code Quality
- Zero bare except violations
- Clean error handling throughout

### ✅ Phase 1: MoE Model
- **441M parameters** (4.4x above 100M requirement)
- 23 specialized experts
- Top-2 routing
- Forward pass verified

### ✅ Phase 2: Device Manager
- Auto-detects cloud platforms
- Configures batch size, precision, gradient checkpointing
- Supports: Colab, Lightning.ai, Kaggle, Paperspace
- GPU profiles: A100, V100, T4, P100, K80, and more

---

## 🎯 Supported Platforms

| Platform | GPU Options | Status |
|----------|-------------|--------|
| Google Colab | T4, V100, A100 | ✅ Ready |
| Lightning.ai | T4, A10G, A100 | ✅ Ready |
| Kaggle | P100, T4 | ✅ Ready |
| Paperspace | Various | ✅ Ready |
| Local GPU | Any CUDA GPU | ✅ Ready |
| CPU | Any CPU | ✅ Ready (slow) |

---

## 📁 Key Files

```
YGB-final/
├── scripts/
│   ├── device_manager.py       # Hardware detection
│   ├── colab_setup.py          # Colab integration
│   └── test_phase0_1_2.py      # Test suite
├── impl_v1/phase49/moe/        # MoE implementation
│   ├── __init__.py
│   ├── expert.py
│   ├── router.py
│   └── moe_architecture.py
├── training_controller.py      # Main training controller
├── PHASE_STATUS_REPORT.md      # Phase status
├── TESTING_RESULTS.md          # Detailed test results
└── QUICK_START.md              # This file
```

---

## 🔧 Troubleshooting

### Test Fails?
```bash
# Check Python version (need 3.8+)
python --version

# Check PyTorch installation
python -c "import torch; print(torch.__version__)"

# Check CUDA availability
python -c "import torch; print(torch.cuda.is_available())"
```

### Import Errors?
```bash
# Install missing dependencies
pip install agentlightning safetensors transformers torch scikit-learn scipy
```

### MoE Model Won't Build?
```bash
# Verify MoE files exist
ls -la impl_v1/phase49/moe/

# Test MoE import
python -c "from impl_v1.phase49.moe import MoEClassifier; print('OK')"
```

---

## 📈 Performance Expectations

| GPU | Training Speed | Experts/Hour |
|-----|----------------|--------------|
| A100-80GB | Very Fast | 8-10 |
| A100-40GB | Very Fast | 6-8 |
| A10G-24GB | Fast | 4-6 |
| T4-16GB | Medium | 2-3 |
| V100-16GB | Medium | 2-3 |
| P100-16GB | Medium | 1-2 |
| K80-12GB | Slow | 1 |
| CPU | Very Slow | 0.1 |

---

## 🎓 Next Steps

Once Phases 0-2 are verified:

1. **Phase 3:** Zero-Loss Compression Engine
2. **Phase 4:** Deep RL + sklearn Integration
3. **Phase 5:** Self-Reflection + Method Invention
4. **Phase 6:** 80+ Field Testing Framework
5. **Phase 7:** Security Hardening

---

## 💡 Tips

- **Use Colab Pro** for A100 access (10x faster)
- **Enable GPU** in Colab: Runtime → Change runtime type → GPU
- **Save checkpoints** to Google Drive for persistence
- **Monitor VRAM** usage to avoid OOM errors
- **Use gradient checkpointing** for large models on small GPUs

---

## 📞 Support

- **Documentation:** See `TESTING_RESULTS.md` for detailed test results
- **Status:** See `PHASE_STATUS_REPORT.md` for current phase status
- **Issues:** Check test output for specific error messages

---

**Last Updated:** 2026-04-15  
**Version:** Phases 0-2 Complete  
**Status:** 🟢 Production Ready
