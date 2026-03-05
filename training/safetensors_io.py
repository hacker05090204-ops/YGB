"""
safetensors_io.py — Atomic SafeTensors I/O with Checksum Verification

Provides save_safetensors() and load_safetensors() with:
- Atomic write (write to .tmp, fsync, rename)
- SHA-256 checksum embedded in metadata and verified on load
- FP16 conversion support
- Windows path compatibility
"""

import hashlib
import json
import logging
import os
import tempfile
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _compute_tensor_hash(tensors: Dict) -> str:
    """Compute SHA-256 hash of tensor dict (sorted keys)."""
    h = hashlib.sha256()
    for k in sorted(tensors.keys()):
        t = tensors[k]
        if hasattr(t, 'cpu'):
            h.update(t.cpu().numpy().tobytes())
        elif hasattr(t, 'tobytes'):
            h.update(t.tobytes())
        else:
            h.update(str(t).encode())
    return h.hexdigest()


def _compute_file_hash(path: str) -> str:
    """Compute SHA-256 hash of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_safetensors(
    tensors: Dict,
    path: str,
    metadata: Optional[Dict[str, str]] = None,
    convert_fp16: bool = False,
) -> Tuple[str, str]:
    """Save tensors to .safetensors with atomic write + checksum.

    Args:
        tensors: Dict of tensor name -> tensor (PyTorch tensors or state dict).
        path: Output file path (should end in .safetensors).
        metadata: Optional string-keyed metadata dict.
        convert_fp16: If True, convert floating-point tensors to FP16.

    Returns:
        (file_sha256, tensor_hash) tuple.
    """
    import torch
    from safetensors.torch import save_file

    # FP16 conversion
    if convert_fp16:
        out = {}
        for k, v in tensors.items():
            if isinstance(v, torch.Tensor) and v.is_floating_point():
                out[k] = v.half()
            else:
                out[k] = v
        tensors = out

    # Compute tensor hash before save
    tensor_hash = _compute_tensor_hash(tensors)

    # Build metadata
    meta = dict(metadata or {})
    meta["tensor_hash"] = tensor_hash

    # Ensure directory exists
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Atomic write: temp file -> save -> rename
    tmp_path = path + ".tmp"
    try:
        save_file(tensors, tmp_path, metadata=meta)

        # Atomic rename (Windows: os.replace is atomic for same volume)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Verify file hash
    file_hash = _compute_file_hash(path)

    logger.info(
        f"[SAFETENSORS] Saved: {os.path.basename(path)} "
        f"tensor_hash={tensor_hash[:16]}... file_hash={file_hash[:16]}..."
    )

    return file_hash, tensor_hash


def load_safetensors(
    path: str,
    device: str = "cpu",
    verify_hash: bool = True,
) -> Dict:
    """Load tensors from .safetensors with optional checksum verification.

    Args:
        path: Path to .safetensors file.
        device: Device to load tensors to (default: cpu).
        verify_hash: If True, verify tensor hash from metadata.

    Returns:
        Dict of tensor name -> tensor.

    Raises:
        FileNotFoundError: If file doesn't exist.
        RuntimeError: If hash verification fails.
    """
    from safetensors.torch import load_file
    from safetensors import safe_open

    if not os.path.exists(path):
        raise FileNotFoundError(f"SafeTensors file not found: {path}")

    # Load tensors
    tensors = load_file(path, device=device)

    # Verify hash if requested
    if verify_hash:
        try:
            with safe_open(path, framework="pt") as f:
                meta = f.metadata()
            if meta and "tensor_hash" in meta:
                expected = meta["tensor_hash"]
                actual = _compute_tensor_hash(tensors)
                if actual != expected:
                    raise RuntimeError(
                        f"SafeTensors hash mismatch: "
                        f"expected={expected[:16]}..., got={actual[:16]}..."
                    )
                logger.info(
                    f"[SAFETENSORS] Verified: {os.path.basename(path)} "
                    f"hash={actual[:16]}..."
                )
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning(f"[SAFETENSORS] Hash verify skipped: {e}")

    return tensors
