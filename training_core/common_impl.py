from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import datetime
from typing import Any, Optional, Tuple

import numpy as np

from training_core.types_impl import CheckpointBundle


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def atomic_write_json(path: str, payload: dict) -> None:
    ensure_dir(os.path.dirname(path))
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_bundle(base_dir: str, name: str) -> CheckpointBundle:
    dir_path = os.path.join(base_dir, name)
    return CheckpointBundle(
        name=name,
        dir_path=dir_path,
        model_path=os.path.join(dir_path, "model.safetensors"),
        state_path=os.path.join(dir_path, "training_state.pt"),
        meta_path=os.path.join(dir_path, "meta.json"),
    )


def checkpoint_manifest_path(base_dir: str) -> str:
    return os.path.join(base_dir, "manifest.json")


def load_json_if_exists(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def extract_verification_code(message: str) -> str:
    prefix, sep, _ = str(message or "").partition(":")
    prefix = prefix.strip()
    if sep and prefix and prefix == prefix.upper():
        return prefix
    return "VERIFICATION_FAILED"


def get_rng_state(torch_module) -> dict:
    state = {
        "python_random": random.getstate(),
        "numpy_random": np.random.get_state(),
        "torch_random": torch_module.get_rng_state(),
    }
    if torch_module.cuda.is_available():
        state["torch_cuda_random_all"] = torch_module.cuda.get_rng_state_all()
    return state


def set_rng_state(torch_module, state: dict) -> None:
    try:
        if state.get("python_random") is not None:
            random.setstate(state["python_random"])
        if state.get("numpy_random") is not None:
            np.random.set_state(state["numpy_random"])
        if state.get("torch_random") is not None:
            torch_module.set_rng_state(state["torch_random"])
        if (
            torch_module.cuda.is_available()
            and state.get("torch_cuda_random_all") is not None
        ):
            torch_module.cuda.set_rng_state_all(state["torch_cuda_random_all"])
    except Exception:
        pass


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def safe_grad_norm(torch_module, parameters, norm_type: float = 2.0) -> float:
    grads = []
    for parameter in parameters:
        grad = getattr(parameter, "grad", None)
        if grad is not None:
            grads.append(grad.detach())
    if not grads:
        return 0.0
    norms = [grad.norm(norm_type) for grad in grads]
    return float(torch_module.norm(torch_module.stack(norms), norm_type).item())


def build_optimizer(optim_module, parameters, lr: float, device) -> Any:
    kwargs = {"lr": lr, "betas": (0.9, 0.95), "weight_decay": 0.01}
    if getattr(device, "type", "") == "cuda":
        try:
            return optim_module.AdamW(parameters, fused=True, **kwargs)
        except TypeError:
            pass
    return optim_module.AdamW(parameters, **kwargs)


def cuda_memory_utilization(torch_module, device) -> float:
    if not torch_module.cuda.is_available():
        return 0.0
    try:
        total = float(torch_module.cuda.get_device_properties(device).total_memory)
        used = float(torch_module.cuda.max_memory_allocated(device))
        return round((used / total) * 100.0, 4) if total > 0 else 0.0
    except Exception:
        return 0.0


def autotune_local_batch(
    *,
    current_batch: int,
    gradient_accumulation: int,
    optimizer,
    performance_tuner,
    latest_sps: float,
    elapsed: float,
    world_size: int,
    zero_stage: int,
    gpu_utilization: float,
    memory_utilization: float,
    min_batch: int,
    max_batch: int,
    min_lr: float,
    max_lr: float,
) -> Tuple[int, int, dict]:
    from impl_v1.unified.performance import ComputeSnapshot

    snapshot = ComputeSnapshot(
        batch_size=current_batch,
        learning_rate=float(optimizer.param_groups[0].get("lr", 0.0)),
        gpu_utilization=gpu_utilization,
        memory_utilization=memory_utilization,
        latency_ms=max(elapsed, 1e-6) * 1000.0 / max(1, current_batch),
        cluster_sps=latest_sps * max(world_size, 1),
        scaling_efficiency=min(1.0, max(0.25, gpu_utilization / 100.0)),
        gradient_accumulation=gradient_accumulation,
        zero_stage=zero_stage,
    )
    decision = performance_tuner.analyze(snapshot)
    next_batch = clamp_int(decision.batch_size, min_batch, max_batch)
    next_accumulation = max(1, int(decision.gradient_accumulation))
    next_lr = max(min_lr, min(max_lr, float(decision.learning_rate)))
    for group in optimizer.param_groups:
        group["lr"] = next_lr
    return next_batch, next_accumulation, decision.__dict__


def update_checkpoint_manifest(base_dir: str, meta: dict) -> None:
    manifest_path = checkpoint_manifest_path(base_dir)
    manifest = load_json_if_exists(manifest_path)
    history = manifest.get("history", [])
    history.append(
        {
            "name": meta.get("checkpoint_name"),
            "epoch": meta.get("epoch"),
            "accuracy": meta.get("accuracy"),
            "loss": meta.get("loss"),
            "saved_at": meta.get("saved_at"),
            "model_sha256": meta.get("model_sha256"),
        }
    )
    manifest["history"] = history[-100:]
    manifest["latest"] = meta if meta.get("is_latest") else manifest.get("latest")
    if meta.get("is_best"):
        manifest["best"] = meta
    manifest["updated_at"] = datetime.now().isoformat()
    atomic_write_json(manifest_path, manifest)


def prune_epoch_checkpoints(base_dir: str, keep: int) -> None:
    if keep <= 0:
        return
    try:
        candidates = []
        for entry in os.listdir(base_dir):
            if entry.startswith("epoch_") and os.path.isdir(
                os.path.join(base_dir, entry)
            ):
                candidates.append(entry)
        candidates.sort()
        for old in candidates[:-keep]:
            old_dir = os.path.join(base_dir, old)
            for root, dirs, files in os.walk(old_dir, topdown=False):
                for file_name in files:
                    os.remove(os.path.join(root, file_name))
                for dir_name in dirs:
                    os.rmdir(os.path.join(root, dir_name))
            os.rmdir(old_dir)
    except Exception:
        pass
