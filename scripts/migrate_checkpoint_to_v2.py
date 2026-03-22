"""Migrate legacy G38 checkpoints into the residual v2 architecture."""

from __future__ import annotations

import argparse
import hashlib
import logging
from pathlib import Path

import torch

from impl_v1.phase49.governors.g37_pytorch_backend import BugClassifier, create_model_config
from training.safetensors_io import load_safetensors, save_safetensors

logger = logging.getLogger("ygb.scripts.migrate_checkpoint_to_v2")

LEGACY_SEQUENTIAL_KEY_MAP = {
    "3.weight": "down_512_256.0.weight",
    "3.bias": "down_512_256.0.bias",
    "6.weight": "down_256_128.0.weight",
    "6.bias": "down_256_128.0.bias",
    "9.weight": "head.weight",
    "9.bias": "head.bias",
}
LEGACY_PARTIAL_KEY_MAP = {
    "0.weight": "input_proj.weight",
    "0.bias": "input_proj.bias",
}


def _log_module_sha256(module_file: str) -> str:
    digest = hashlib.sha256(Path(module_file).read_bytes()).hexdigest()
    logger.info(
        "module_sha256",
        extra={"event": "module_sha256", "module_name": __name__, "module_file": module_file, "sha256": digest},
    )
    return digest


def find_legacy_checkpoint(search_root: str = "checkpoints") -> Path | None:
    candidates = sorted(Path(search_root).glob("*.pt"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_checkpoint_state(input_path: str) -> tuple[dict[str, torch.Tensor], dict[str, str]]:
    source_path = Path(input_path)
    metadata = {"source_path": str(source_path)}
    if source_path.suffix.lower() == ".safetensors":
        return load_safetensors(input_path, device="cpu"), metadata

    payload = torch.load(input_path, map_location="cpu")
    if isinstance(payload, dict):
        for key in ("model_state_dict", "model_state", "state_dict"):
            state_dict = payload.get(key)
            if isinstance(state_dict, dict):
                metadata["source_format"] = key
                metadata["epoch"] = str(payload.get("epoch", ""))
                return state_dict, metadata
        if all(hasattr(value, "shape") for value in payload.values()):
            metadata["source_format"] = "raw_state_dict"
            return payload, metadata

    raise RuntimeError(f"Unsupported checkpoint payload: {input_path}")


def _copy_overlapping_tensor(target: torch.Tensor, source: torch.Tensor) -> None:
    slices = tuple(slice(0, min(t_dim, s_dim)) for t_dim, s_dim in zip(target.shape, source.shape))
    if not slices:
        return
    target[slices].copy_(source[slices].to(dtype=target.dtype))


def migrate_checkpoint(
    input_path: str = "checkpoints/g38_model_checkpoint.safetensors",
    output_path: str = "checkpoints/g38_model_checkpoint_v2.safetensors",
) -> dict[str, list[str]]:
    if BugClassifier is None:
        raise RuntimeError("BugClassifier runtime unavailable")

    source_path = Path(input_path)
    if not source_path.exists():
        legacy_candidate = find_legacy_checkpoint(source_path.parent.as_posix())
        if legacy_candidate is None:
            raise FileNotFoundError(f"No checkpoint found at {input_path}")
        source_path = legacy_candidate

    old_state, source_metadata = _load_checkpoint_state(str(source_path))
    model = BugClassifier(create_model_config())
    new_state = model.state_dict()
    mapped_keys: list[str] = []
    unmapped_keys: list[str] = []

    for key, tensor in new_state.items():
        source_tensor = old_state.get(key)
        if source_tensor is not None and tuple(source_tensor.shape) == tuple(tensor.shape):
            tensor.copy_(source_tensor)
            mapped_keys.append(key)
            continue

        legacy_key = next(
            (src_key for src_key, dst_key in LEGACY_SEQUENTIAL_KEY_MAP.items() if dst_key == key),
            None,
        )
        if legacy_key is not None and legacy_key in old_state:
            tensor.copy_(old_state[legacy_key].to(dtype=tensor.dtype))
            mapped_keys.append(f"{legacy_key}->{key}")
            continue

        legacy_partial_key = next(
            (src_key for src_key, dst_key in LEGACY_PARTIAL_KEY_MAP.items() if dst_key == key),
            None,
        )
        if legacy_partial_key is not None and legacy_partial_key in old_state:
            _copy_overlapping_tensor(tensor, old_state[legacy_partial_key])
            mapped_keys.append(f"{legacy_partial_key}->{key}[partial]")
            continue

        if tensor.dtype.is_floating_point:
            if tensor.dim() >= 2:
                torch.nn.init.xavier_uniform_(tensor)
            elif key.endswith(".weight"):
                torch.nn.init.ones_(tensor)
            else:
                torch.nn.init.zeros_(tensor)
        else:
            tensor.zero_()
        unmapped_keys.append(key)

    save_safetensors(
        new_state,
        output_path,
        metadata={
            "mapped_keys": str(len(mapped_keys)),
            "unmapped_keys": str(len(unmapped_keys)),
            "source_path": source_metadata.get("source_path", str(source_path)),
            "source_format": source_metadata.get("source_format", source_path.suffix.lower().lstrip(".")),
            "epoch": source_metadata.get("epoch", ""),
        },
    )
    logger.info("checkpoint_migration_complete mapped=%s unmapped=%s", len(mapped_keys), len(unmapped_keys))
    return {"mapped_keys": mapped_keys, "unmapped_keys": unmapped_keys}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a G38 checkpoint to the residual v2 architecture.")
    parser.add_argument("--input", default="checkpoints/g38_model_checkpoint.safetensors")
    parser.add_argument("--output", default="checkpoints/g38_model_checkpoint_v2.safetensors")
    args = parser.parse_args()
    result = migrate_checkpoint(args.input, args.output)
    print(f"mapped={len(result['mapped_keys'])} unmapped={len(result['unmapped_keys'])}")
    return 0


MODULE_SHA256 = _log_module_sha256(__file__)


if __name__ == "__main__":
    raise SystemExit(main())
