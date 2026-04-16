"""Auto-detects hardware and configures optimal training settings.
Same file works on: Google Colab T4/A100, RTX 2050, CPU, VPS.
Call device_manager.get_config() at start of any training script."""

import os
import platform
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("ygb.device_manager")


@dataclass
class DeviceConfig:
    device: str               # "cuda", "cpu", "mps"
    device_name: str          # human readable
    vram_gb: float            # 0.0 for CPU
    batch_size: int           # auto-tuned
    precision: str            # "bf16", "fp16", "fp32"
    gradient_checkpointing: bool
    use_amp: bool
    num_workers: int          # DataLoader workers
    pin_memory: bool
    max_model_params: int     # max params this device can handle
    is_colab: bool
    notes: str


def get_config(target_params: int = 130_430_000) -> DeviceConfig:
    """Detect hardware and return optimal training config.
    
    Args:
        target_params: how many parameters we want to train
        
    Returns:
        DeviceConfig with optimal settings for detected hardware
    """
    try:
        import torch
        has_cuda = torch.cuda.is_available()
        has_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    except ImportError:
        has_cuda = False
        has_mps = False

    is_colab = "COLAB_GPU" in os.environ or "/content" in os.getcwd()

    if has_cuda:
        import torch
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024**3)
        device_name = props.name

        # Determine precision
        # bf16: Ampere+ (compute capability >= 8.0)
        cc_major = props.major
        if cc_major >= 8:
            precision = "bf16"
        elif cc_major >= 7:
            precision = "fp16"
        else:
            precision = "fp32"

        # Batch size based on VRAM
        # Rule: ~4GB per 1B params, batch_size scales with remaining
        params_gb = target_params * 4 / (1024**3)  # float32 bytes
        remaining_gb = max(0.5, vram_gb - params_gb)
        
        if vram_gb >= 40:    # A100
            batch_size = 128
            grad_ckpt = False
            max_params = 10_000_000_000
        elif vram_gb >= 16:  # T4, RTX 3080Ti
            batch_size = 32
            grad_ckpt = target_params > 1_000_000_000
            max_params = 3_000_000_000
        elif vram_gb >= 8:   # RTX 2050, 3060
            batch_size = 16
            grad_ckpt = True
            max_params = 1_000_000_000
        elif vram_gb >= 4:   # Entry GPU
            batch_size = 8
            grad_ckpt = True
            max_params = 500_000_000
        else:
            batch_size = 4
            grad_ckpt = True
            max_params = 130_000_000

        config = DeviceConfig(
            device="cuda",
            device_name=device_name,
            vram_gb=vram_gb,
            batch_size=batch_size,
            precision=precision,
            gradient_checkpointing=grad_ckpt,
            use_amp=True,
            num_workers=min(4, os.cpu_count() or 1),
            pin_memory=True,
            max_model_params=max_params,
            is_colab=is_colab,
            notes=f"CUDA {cc_major}.{props.minor}, {vram_gb:.1f}GB VRAM",
        )

    elif has_mps:
        config = DeviceConfig(
            device="mps",
            device_name="Apple Silicon",
            vram_gb=0.0,
            batch_size=16,
            precision="fp32",  # MPS has limited bf16
            gradient_checkpointing=True,
            use_amp=False,
            num_workers=4,
            pin_memory=False,
            max_model_params=500_000_000,
            is_colab=False,
            notes="Apple MPS backend",
        )

    else:
        cpus = os.cpu_count() or 1
        config = DeviceConfig(
            device="cpu",
            device_name=f"CPU ({cpus} cores)",
            vram_gb=0.0,
            batch_size=8,
            precision="fp32",
            gradient_checkpointing=True,
            use_amp=False,
            num_workers=max(1, cpus // 2),
            pin_memory=False,
            max_model_params=130_000_000,  # CPU can handle 130M slowly
            is_colab=is_colab,
            notes="CPU fallback — training will be slow",
        )

    logger.info(
        "Device: %s | VRAM: %.1fGB | Batch: %d | Precision: %s | "
        "GradCkpt: %s | MaxParams: %dM",
        config.device_name, config.vram_gb, config.batch_size,
        config.precision, config.gradient_checkpointing,
        config.max_model_params // 1_000_000,
    )

    return config


def print_config(config: DeviceConfig):
    """Print device configuration in a readable format."""
    print("\n" + "="*50)
    print("YBG DEVICE CONFIGURATION")
    print("="*50)
    print(f"  Device:   {config.device_name}")
    print(f"  VRAM:     {config.vram_gb:.1f}GB")
    print(f"  Batch:    {config.batch_size}")
    print(f"  Precision:{config.precision}")
    print(f"  GradCkpt: {config.gradient_checkpointing}")
    print(f"  MaxModel: {config.max_model_params/1e9:.1f}B params")
    print(f"  Colab:    {config.is_colab}")
    print(f"  Notes:    {config.notes}")
    print("="*50 + "\n")


if __name__ == "__main__":
    cfg = get_config()
    print_config(cfg)
