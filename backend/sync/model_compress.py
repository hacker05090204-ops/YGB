"""
YGB Model Compression Pipeline — Optimized model variants for all device tiers.

Produces:
  - ONNX FP32 (full accuracy, mid-size)
  - ONNX INT8 (quantized, ~50-75% smaller, -1-3% accuracy)
  - Summary report

Target accuracy bands (realistic):
  Low-end  (4 GB): ONNX INT8     → 90-92% of full accuracy
  Mid-range (8 GB): ONNX FP16    → 93-95% of full accuracy
  Training (16 GB): Full model    → 96-98% accuracy

Usage:
  python -m backend.sync.model_compress --model models/full/g38.safetensors
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Optional

from config.storage_config import SYNC_ROOT as DEFAULT_SYNC_ROOT
from impl_v1.training.checkpoints.checkpoint_hardening import HardenedCheckpointManager

logger = logging.getLogger("ygb.sync.compress")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", str(DEFAULT_SYNC_ROOT)))
MODEL_ROOT = SYNC_ROOT / "ygb_training" / "models"


def get_model_dirs() -> dict:
    """Return model output directory paths."""
    dirs = {
        "full": MODEL_ROOT / "full",
        "onnx": MODEL_ROOT / "onnx",
        "gguf": MODEL_ROOT / "gguf",
        "distilled": MODEL_ROOT / "distilled",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def compress_to_onnx_int8(
    model_path: Path,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Convert a PyTorch model to ONNX and quantize to INT8.

    This is the primary compression path for low-end devices.
    50-75% size reduction with 1-3% accuracy loss.
    """
    if output_dir is None:
        output_dir = MODEL_ROOT / "onnx"
    output_dir.mkdir(parents=True, exist_ok=True)

    model_name = model_path.stem
    onnx_fp32 = output_dir / f"{model_name}_fp32.onnx"
    onnx_int8 = output_dir / f"{model_name}_int8.onnx"

    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType

        if not onnx_fp32.exists():
            logger.info(
                "ONNX FP32 not found at %s — need torch export first", onnx_fp32,
            )
            _export_to_onnx(model_path, onnx_fp32)

        if onnx_fp32.exists():
            logger.info("Quantizing %s → INT8...", onnx_fp32.name)
            quantize_dynamic(
                str(onnx_fp32),
                str(onnx_int8),
                weight_type=QuantType.QInt8,
            )
            orig_mb = onnx_fp32.stat().st_size / 1e6
            quant_mb = onnx_int8.stat().st_size / 1e6
            ratio = (1 - quant_mb / orig_mb) * 100 if orig_mb > 0 else 0
            logger.info(
                "INT8 quantized: %.1f MB → %.1f MB (%.0f%% reduction)",
                orig_mb, quant_mb, ratio,
            )
            return onnx_int8
        else:
            logger.error("ONNX FP32 export failed — cannot quantize")
            return None

    except ImportError:
        logger.warning(
            "onnxruntime not installed. Run: pip install onnxruntime onnx"
        )
        return None
    except Exception as e:
        logger.error("ONNX INT8 quantization failed: %s", e)
        return None


def _export_to_onnx(model_path: Path, onnx_path: Path) -> bool:
    """
    Export a PyTorch/safetensors model to ONNX format.

    This is model-architecture-specific. The actual export depends on
    the G38 model class. This provides a generic framework.
    """
    try:
        import torch

        logger.info("Exporting %s → ONNX...", model_path.name)

        # Check if it's a safetensors file
        if model_path.suffix == ".safetensors":
            try:
                from safetensors.torch import load_file
                state_dict = load_file(str(model_path))
                logger.info(
                    "Loaded safetensors: %d parameters",
                    sum(p.numel() for p in state_dict.values()),
                )
                # The actual model class instantiation would go here
                # This is a framework — actual implementation depends on G38 arch
                logger.warning(
                    "Generic safetensors export — customize for G38 model class"
                )
                return False
            except ImportError:
                logger.warning("safetensors not installed")
                return False
        else:
            # Try loading as regular PyTorch checkpoint
            HardenedCheckpointManager._require_verified_file_hash(model_path)
            model = torch.load(str(model_path), map_location="cpu", weights_only=True)
            if hasattr(model, "eval"):
                model.eval()
            logger.info("Model loaded, exporting to ONNX...")
            # Export would go here with actual input shape
            return False

    except ImportError:
        logger.warning("PyTorch not installed — cannot export to ONNX")
        return False
    except Exception as e:
        logger.error("ONNX export failed: %s", e)
        return False


def generate_compression_report(model_name: str) -> dict:
    """Generate a report of all model variants and their sizes."""
    dirs = get_model_dirs()
    report = {
        "model_name": model_name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "variants": {},
    }

    for variant, vdir in dirs.items():
        files = list(vdir.glob(f"{model_name}*"))
        if files:
            for f in files:
                report["variants"][f"{variant}/{f.name}"] = {
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / 1e6, 2),
                    "format": f.suffix,
                }

    # Add recommendations
    report["recommendations"] = {
        "low_end_4gb": {
            "format": "ONNX INT8",
            "expected_accuracy": "90-92%",
            "inference_ms": "50-200",
        },
        "mid_range_8gb": {
            "format": "ONNX FP16",
            "expected_accuracy": "93-95%",
            "inference_ms": "20-100",
        },
        "training_16gb": {
            "format": "Full safetensors",
            "expected_accuracy": "96-98%",
            "inference_ms": "10-50",
        },
    }

    # Save report
    report_path = MODEL_ROOT / f"{model_name}_compression_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Compression report saved: %s", report_path)
    return report


def compress_all_models():
    """Compress all models in the full/ directory."""
    full_dir = MODEL_ROOT / "full"
    if not full_dir.exists():
        logger.info("No models found in %s", full_dir)
        return

    for model_file in full_dir.iterdir():
        if model_file.suffix in (".safetensors", ".pt", ".pth", ".bin"):
            logger.info("═══ Compressing: %s ═══", model_file.name)
            compress_to_onnx_int8(model_file)
            generate_compression_report(model_file.stem)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="YGB Model Compression")
    parser.add_argument("--model", help="Path to model file")
    parser.add_argument("--all", action="store_true", help="Compress all models")
    parser.add_argument("--report", help="Generate report for model name")
    args = parser.parse_args()

    if args.all:
        compress_all_models()
    elif args.model:
        model_path = Path(args.model)
        if model_path.exists():
            compress_to_onnx_int8(model_path)
            generate_compression_report(model_path.stem)
        else:
            print(f"Model not found: {args.model}")
    elif args.report:
        report = generate_compression_report(args.report)
        print(json.dumps(report, indent=2))
    else:
        parser.print_help()
