"""Utilities and instructions for Colab bootstrap flows."""

from __future__ import annotations

from typing import Any

from scripts.device_manager import resolve_device_configuration


_TORCH_SENTINEL = object()

COLAB_SETUP_CODE = '''
# Cell 1: Environment setup
import os, subprocess, sys

# Clone/pull latest
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
os.environ["JWT_SECRET"] = "colab-benchmark-jwt-32chars-minimum"
os.environ["YGB_VIDEO_JWT_SECRET"] = "colab-video-jwt-32chars-min"
os.environ["YGB_LEDGER_KEY"] = "colab-ledger-key-for-testing"
os.environ["YGB_REQUIRE_ENCRYPTION"] = "false"

# Detect device
from scripts.device_manager import get_config, print_config
cfg = get_config()
print_config(cfg)

# Cell 2: Claim expert and train
from scripts.expert_task_queue import ExpertTaskQueue
from training_controller import train_single_expert

queue = ExpertTaskQueue()
queue.print_status()

expert = queue.claim_next_expert()
if expert is None:
    print("All experts claimed or trained!")
else:
    print(f"Claimed expert {expert.expert_id}: {expert.field_name}")
    result = train_single_expert(expert.expert_id, expert.field_name)
    print(f"Done: val_f1={result.val_f1:.4f} status={result.status}")
    queue.release_expert(expert.expert_id, result.val_f1,
                        result.checkpoint_path,
                        success=result.val_f1 >= 0.50)
    queue.print_status()
'''

def build_colab_setup_summary(
    *,
    validate_imports: bool = True,
    torch_module: Any = _TORCH_SENTINEL,
) -> dict[str, Any]:
    device_configuration = resolve_device_configuration(
        torch_module=torch_module,
        configure_runtime=False,
    )
    imports = {
        "scripts.device_manager": True,
        "scripts.expert_task_queue": True,
        "training_controller": True,
    }
    if validate_imports:
        for module_name in tuple(imports.keys()):
            try:
                __import__(module_name)
            except Exception:
                imports[module_name] = False

    return {
        "is_colab": device_configuration.is_colab,
        "device": device_configuration.to_dict(),
        "imports": imports,
        "recommended_commands": {
            "dry_run_training": "python scripts/run_ybg_training_colab.py --dry-run",
            "claim_and_train": "python -c \"from training_controller import train_single_expert\"",
        },
        "bootstrap_cell": COLAB_SETUP_CODE,
    }


if __name__ == "__main__":
    print("=" * 70)
    print("GOOGLE COLAB SETUP INSTRUCTIONS")
    print("=" * 70)
    print("\n1. Open Google Colab: https://colab.research.google.com/")
    print("2. Create a new notebook")
    print("3. Copy the code below into the first cell:")
    print("\n" + "=" * 70)
    print(COLAB_SETUP_CODE)
    print("=" * 70)
    print("\n4. Run the cell and wait for training to complete")
    print("5. Repeat Cell 2 to train additional experts")
    print("\nNote: Each Colab session can train 1-3 experts depending on GPU type")
