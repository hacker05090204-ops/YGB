"""Utilities for low-overhead deterministic model hashing."""

from __future__ import annotations

import hashlib
from typing import Iterable


def _iter_named_tensors(model) -> Iterable[tuple[str, object]]:
    raw = model.module if hasattr(model, "module") else model
    if hasattr(raw, "state_dict"):
        for name, tensor in sorted(raw.state_dict().items()):
            yield name, tensor.detach()
    else:
        for name, tensor in sorted(raw.named_parameters()):
            yield name, tensor.detach()


def hash_model_weights(model, mode: str = "sampled", sample_elems: int = 1024) -> str:
    """Return a deterministic SHA-256 hash of model weights.

    Modes:
    - full: hash every tensor byte (highest overhead)
    - sampled: hash lightweight tensor samples + metadata (default)
    """
    import torch

    h = hashlib.sha256()

    for name, tensor in _iter_named_tensors(model):
        h.update(name.encode("utf-8"))
        h.update(str(tuple(tensor.shape)).encode("utf-8"))
        h.update(str(tensor.dtype).encode("utf-8"))

        if mode == "full":
            h.update(tensor.contiguous().cpu().numpy().tobytes())
            continue

        flat = tensor.reshape(-1)
        numel = int(flat.numel())
        h.update(str(numel).encode("utf-8"))
        if numel == 0:
            continue

        take = min(sample_elems, numel)
        if take >= numel:
            sample = flat
        else:
            step = max(numel // take, 1)
            sample = flat[::step][:take]
            if sample.numel() < take:
                tail = flat[-(take - sample.numel()):]
                sample = torch.cat((sample, tail), dim=0)

        h.update(sample.contiguous().cpu().numpy().tobytes())

    return h.hexdigest()
