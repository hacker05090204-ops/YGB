from __future__ import annotations

import os
from typing import Optional

from training_core.common_impl import (
    atomic_write_json,
    checkpoint_bundle,
    checkpoint_manifest_path,
    ensure_dir,
    load_json_if_exists,
    sha256_file,
    update_checkpoint_manifest,
)


def save_training_checkpoint(
    *,
    base_dir: str,
    name: str,
    model_state: dict,
    training_state: dict,
    meta: dict,
) -> str:
    from safetensors.torch import save_file as st_save

    bundle = checkpoint_bundle(base_dir, name)
    ensure_dir(bundle.dir_path)

    model_tmp = f"{bundle.model_path}.tmp"
    state_tmp = f"{bundle.state_path}.tmp"

    st_save(model_state, model_tmp)
    os.replace(model_tmp, bundle.model_path)

    torch = __import__("torch")
    torch.save(training_state, state_tmp)
    os.replace(state_tmp, bundle.state_path)

    meta = dict(meta)
    meta.update(
        {
            "checkpoint_name": name,
            "model_path": bundle.model_path,
            "state_path": bundle.state_path,
            "meta_path": bundle.meta_path,
            "model_sha256": sha256_file(bundle.model_path),
            "state_sha256": sha256_file(bundle.state_path),
        }
    )
    atomic_write_json(bundle.meta_path, meta)
    update_checkpoint_manifest(base_dir, meta)
    return bundle.meta_path


def load_latest_training_checkpoint(base_dir: str) -> Optional[dict]:
    try:
        from impl_v1.training.distributed.advanced_checkpointing import (
            AsyncDistributedCheckpointManager,
        )

        manager = AsyncDistributedCheckpointManager(base_dir)
        loaded = manager.load_latest_valid(rank=0)
        manager.close()
        if loaded is not None:
            return {
                **loaded.meta,
                "model_path": loaded.bundle.model_shards[0].model_path
                if loaded.bundle.model_shards
                else "",
                "state_path": loaded.bundle.model_shards[0].optimizer_path
                if loaded.bundle.model_shards
                else "",
                "meta_path": loaded.bundle.meta_path,
                "model_sha256": loaded.bundle.model_shards[0].model_sha256
                if loaded.bundle.model_shards
                else "",
            }
    except Exception:
        pass

    manifest = load_json_if_exists(checkpoint_manifest_path(base_dir))
    latest = manifest.get("latest") or {}
    meta_path = latest.get("meta_path")
    if not meta_path or not os.path.exists(meta_path):
        return None
    meta = load_json_if_exists(meta_path)
    if not meta:
        return None
    if not os.path.exists(meta.get("model_path", "")):
        return None
    if not os.path.exists(meta.get("state_path", "")):
        return None
    return meta
