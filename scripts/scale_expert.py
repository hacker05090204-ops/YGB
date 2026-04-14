"""Scale a repository MoE expert checkpoint forward for Phase 16.

Phase 16 scaling plan:

- Day 1-30  -> 130M per expert
- Day 31-90 -> 512M per expert
- Day 91-180 -> 1B per expert
- Day 181+ -> 3B per expert

The repository's classifier-path expert checkpoints do not expose a literal
`n_layers`. Instead, [`SingleExpert`](impl_v1/phase49/moe/expert.py:31) is the
faithful expert unit. Phase 16 therefore maps expert depth to the number of
classifier expert MLP transforms:

- depth `1` = the legacy `fc1 -> GELU -> Dropout -> fc2` expert block
- depth `N > 1` = the legacy block plus `N - 1` residual `depth_layers`

This script performs one forward-scaling step by doubling `expert_depth`
(`1 -> 2`, `2 -> 4`, `4 -> 8`, ...). Existing weights are preserved and newly
appended residual layers are zero-initialized so the scaled checkpoint remains
function-preserving while adding compatible capacity.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from safetensors import safe_open

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.training.safetensors_store import (
    CHECKPOINT_METADATA_JSON_KEY,
    LEGACY_CHECKPOINT_METADATA_JSON_KEY,
)
from impl_v1.phase49.moe import MoEClassifier, MoEConfig
from impl_v1.training.checkpoints.checkpoint_hardening import HardenedCheckpointManager
from training.safetensors_io import load_safetensors, save_safetensors


logger = logging.getLogger("ygb.scripts.scale_expert")


@dataclass(frozen=True)
class Phase16ScalingStage:
    label: str
    day_start: int
    day_end: int | None
    target_per_expert_params: int
    target_label: str


@dataclass(frozen=True)
class ExpertCheckpointShape:
    input_dim: int
    output_dim: int
    d_model: int
    n_experts: int
    top_k: int
    expert_hidden_dim: int
    expert_depth: int
    dropout: float
    gate_noise: float


@dataclass(frozen=True)
class ExpertScalingResult:
    input_path: str
    output_path: str
    source_depth: int
    scaled_depth: int
    source_sha256: str
    output_sha256: str
    tensor_hash: str
    stage_label: str


PHASE16_SCALING_PLAN: tuple[Phase16ScalingStage, ...] = (
    Phase16ScalingStage(
        label="Day 1-30",
        day_start=1,
        day_end=30,
        target_per_expert_params=130_000_000,
        target_label="130M per expert",
    ),
    Phase16ScalingStage(
        label="Day 31-90",
        day_start=31,
        day_end=90,
        target_per_expert_params=512_000_000,
        target_label="512M per expert",
    ),
    Phase16ScalingStage(
        label="Day 91-180",
        day_start=91,
        day_end=180,
        target_per_expert_params=1_000_000_000,
        target_label="1B per expert",
    ),
    Phase16ScalingStage(
        label="Day 181+",
        day_start=181,
        day_end=None,
        target_per_expert_params=3_000_000_000,
        target_label="3B per expert",
    ),
)


def resolve_phase16_scaling_stage(training_day: int) -> Phase16ScalingStage:
    day_value = int(training_day)
    if day_value <= 0:
        raise ValueError(f"training_day must be positive, got {training_day}")

    for stage in PHASE16_SCALING_PLAN:
        if stage.day_end is None and day_value >= stage.day_start:
            return stage
        if stage.day_end is not None and stage.day_start <= day_value <= stage.day_end:
            return stage
    raise RuntimeError(f"No Phase 16 scaling stage found for day={training_day}")


def load_checkpoint_metadata(checkpoint_path: str | Path) -> dict[str, Any]:
    path = Path(checkpoint_path)
    with safe_open(str(path), framework="pt") as handle:
        metadata = handle.metadata() or {}
    raw_metadata = metadata.get(CHECKPOINT_METADATA_JSON_KEY)
    if raw_metadata in (None, ""):
        raw_metadata = metadata.get(LEGACY_CHECKPOINT_METADATA_JSON_KEY, "{}")
    parsed = json.loads(raw_metadata or "{}")
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: checkpoint metadata must decode to an object")
    return parsed


def _write_sha256_sidecar(path: Path, sha256: str) -> Path:
    sidecar_path = Path(f"{path}.sha256")
    temp_path = Path(f"{sidecar_path}.tmp")
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{sha256.strip().lower()}\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temp_path), str(sidecar_path))
    return sidecar_path


def _infer_expert_depth(state_dict: dict[str, torch.Tensor]) -> int:
    depth_prefix = "moe.experts.0.depth_layers."
    depth_suffix = ".fc1.weight"
    depth_indices: list[int] = []
    for key in state_dict:
        if not key.startswith(depth_prefix) or not key.endswith(depth_suffix):
            continue
        index_text = key[len(depth_prefix) : -len(depth_suffix)]
        if index_text.isdigit():
            depth_indices.append(int(index_text))
    return 1 + (max(depth_indices) + 1 if depth_indices else 0)


def _coerce_positive_int(value: Any, *, fallback: int, field_name: str) -> int:
    candidate = fallback if value in (None, "") else value
    try:
        parsed = int(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer, got {candidate!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer, got {parsed}")
    return parsed


def _coerce_float(value: Any, *, fallback: float, field_name: str) -> float:
    candidate = fallback if value in (None, "") else value
    try:
        return float(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a float, got {candidate!r}") from exc


def _resolve_checkpoint_shape(
    state_dict: dict[str, torch.Tensor],
    metadata: dict[str, Any],
) -> ExpertCheckpointShape:
    input_proj = state_dict.get("input_proj.weight")
    classifier_weight = state_dict.get("classifier.weight")
    router_weight = state_dict.get("moe.router.w_gate.weight")
    expert_fc1_weight = state_dict.get("moe.experts.0.fc1.weight")
    required = {
        "input_proj.weight": input_proj,
        "classifier.weight": classifier_weight,
        "moe.router.w_gate.weight": router_weight,
        "moe.experts.0.fc1.weight": expert_fc1_weight,
    }
    missing = [key for key, value in required.items() if not isinstance(value, torch.Tensor)]
    if missing:
        raise RuntimeError(
            "Unsupported checkpoint: expected a MoEClassifier expert checkpoint with keys "
            f"{', '.join(missing)}"
        )

    return ExpertCheckpointShape(
        input_dim=_coerce_positive_int(
            metadata.get("input_dim"),
            fallback=int(input_proj.shape[1]),
            field_name="input_dim",
        ),
        output_dim=_coerce_positive_int(
            metadata.get("output_dim"),
            fallback=int(classifier_weight.shape[0]),
            field_name="output_dim",
        ),
        d_model=_coerce_positive_int(
            metadata.get("d_model"),
            fallback=int(input_proj.shape[0]),
            field_name="d_model",
        ),
        n_experts=_coerce_positive_int(
            metadata.get("n_experts"),
            fallback=int(router_weight.shape[0]),
            field_name="n_experts",
        ),
        top_k=_coerce_positive_int(
            metadata.get("top_k"),
            fallback=2,
            field_name="top_k",
        ),
        expert_hidden_dim=_coerce_positive_int(
            metadata.get("expert_hidden_dim"),
            fallback=int(expert_fc1_weight.shape[0]),
            field_name="expert_hidden_dim",
        ),
        expert_depth=_coerce_positive_int(
            metadata.get("expert_depth"),
            fallback=_infer_expert_depth(state_dict),
            field_name="expert_depth",
        ),
        dropout=_coerce_float(
            metadata.get("dropout"),
            fallback=0.3,
            field_name="dropout",
        ),
        gate_noise=_coerce_float(
            metadata.get("gate_noise"),
            fallback=1.0,
            field_name="gate_noise",
        ),
    )


def _build_classifier(shape: ExpertCheckpointShape) -> MoEClassifier:
    config = MoEConfig(
        d_model=int(shape.d_model),
        n_experts=int(shape.n_experts),
        top_k=int(shape.top_k),
        expert_hidden_mult=max(1, int(math.ceil(shape.expert_hidden_dim / max(1, shape.d_model)))),
        dropout=float(shape.dropout),
        gate_noise=float(shape.gate_noise),
    )
    setattr(config, "expert_hidden_dim", int(shape.expert_hidden_dim))
    setattr(config, "expert_depth", int(shape.expert_depth))
    return MoEClassifier(
        config,
        input_dim=int(shape.input_dim),
        output_dim=int(shape.output_dim),
    )


def _default_output_path(input_path: Path, scaled_depth: int) -> Path:
    return input_path.with_name(f"{input_path.stem}_scaled_d{scaled_depth}{input_path.suffix}")


def scale_expert_checkpoint(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    training_day: int | None = None,
    overwrite: bool = False,
) -> ExpertScalingResult:
    source_path = Path(input_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {source_path}")

    resolved_output_path = Path(output_path) if output_path is not None else _default_output_path(source_path, 2)
    if resolved_output_path.exists() and not overwrite:
        raise FileExistsError(f"Output checkpoint already exists: {resolved_output_path}")

    source_sha256 = HardenedCheckpointManager._require_verified_file_hash(source_path)
    metadata = load_checkpoint_metadata(source_path)
    state_dict = load_safetensors(str(source_path), device="cpu")
    source_shape = _resolve_checkpoint_shape(state_dict, metadata)

    source_model = _build_classifier(source_shape)
    source_model.load_state_dict(state_dict, strict=True)

    scaled_shape = replace(source_shape, expert_depth=source_shape.expert_depth * 2)
    scaled_model = _build_classifier(scaled_shape)
    scaled_state = scaled_model.state_dict()

    source_keys = set(state_dict.keys())
    scaled_keys = set(scaled_state.keys())
    allowed_new_keys = {
        key for key in scaled_keys - source_keys if ".depth_layers." in key
    }
    disallowed_new_keys = sorted((scaled_keys - source_keys) - allowed_new_keys)
    unexpected_source_keys = sorted(source_keys - scaled_keys)
    if disallowed_new_keys or unexpected_source_keys:
        raise RuntimeError(
            "Checkpoint shape mismatch during expert scaling: "
            f"unexpected_new={disallowed_new_keys} unexpected_source={unexpected_source_keys}"
        )

    for key, value in state_dict.items():
        scaled_state[key] = value.detach().cpu().clone()
    for key in allowed_new_keys:
        scaled_state[key] = torch.zeros_like(scaled_state[key])

    scaled_model.load_state_dict(scaled_state, strict=True)

    stage = resolve_phase16_scaling_stage(training_day) if training_day is not None else None
    scaled_metadata = {
        **metadata,
        "architecture": metadata.get("architecture") or "MoEClassifier",
        "architecture_format": metadata.get("architecture_format") or "moe_classifier_expert_v2",
        "input_dim": int(scaled_shape.input_dim),
        "output_dim": int(scaled_shape.output_dim),
        "d_model": int(scaled_shape.d_model),
        "n_experts": int(scaled_shape.n_experts),
        "top_k": int(scaled_shape.top_k),
        "expert_hidden_dim": int(scaled_shape.expert_hidden_dim),
        "expert_depth": int(scaled_shape.expert_depth),
        "scaled_from_depth": int(source_shape.expert_depth),
        "scaled_from_checkpoint_path": source_path.as_posix(),
        "scaled_from_checkpoint_sha256": source_sha256,
        "scaling_strategy": "phase16_expert_depth_doubling",
        "scaling_mapping": "expert_depth=1 legacy block; expert_depth>1 adds residual depth_layers",
        "scaled_at": datetime.now(timezone.utc).isoformat(),
    }
    if stage is not None:
        scaled_metadata.update(
            {
                "phase16_stage_label": stage.label,
                "phase16_training_day": int(training_day),
                "phase16_target_per_expert_params": int(stage.target_per_expert_params),
                "phase16_target_label": stage.target_label,
            }
        )

    metadata_json = json.dumps(scaled_metadata, sort_keys=True)
    output_sha256, tensor_hash = save_safetensors(
        scaled_state,
        str(resolved_output_path),
        metadata={
            CHECKPOINT_METADATA_JSON_KEY: metadata_json,
            LEGACY_CHECKPOINT_METADATA_JSON_KEY: metadata_json,
        },
    )
    _write_sha256_sidecar(resolved_output_path, output_sha256)
    HardenedCheckpointManager._require_verified_file_hash(
        resolved_output_path,
        expected_sha256=output_sha256,
    )
    load_safetensors(str(resolved_output_path), device="cpu")

    return ExpertScalingResult(
        input_path=source_path.as_posix(),
        output_path=resolved_output_path.as_posix(),
        source_depth=int(source_shape.expert_depth),
        scaled_depth=int(scaled_shape.expert_depth),
        source_sha256=source_sha256,
        output_sha256=output_sha256,
        tensor_hash=tensor_hash,
        stage_label=stage.label if stage is not None else "UNSPECIFIED",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scale a repository expert checkpoint forward by doubling expert depth.",
    )
    parser.add_argument("--input", required=True, help="Path to the source expert checkpoint")
    parser.add_argument("--output", default="", help="Path for the scaled checkpoint")
    parser.add_argument(
        "--day",
        type=int,
        default=None,
        help="Optional training day used to annotate the Phase 16 scaling tier",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output checkpoint if it already exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args(argv)
    result = scale_expert_checkpoint(
        args.input,
        output_path=args.output or None,
        training_day=args.day,
        overwrite=bool(args.overwrite),
    )
    print(f"Original expert depth/layers: {result.source_depth}")
    print(f"Scaled expert depth/layers: {result.scaled_depth}")
    print(f"Phase 16 scaling stage: {result.stage_label}")
    print(f"Verified scaled checkpoint: {result.output_path}")
    print(f"Scaled checkpoint SHA256: {result.output_sha256}")
    print(f"Scaled checkpoint tensor_hash: {result.tensor_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
