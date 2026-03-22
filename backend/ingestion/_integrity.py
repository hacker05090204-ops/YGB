"""Helpers for module integrity logging."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("ygb.ingestion.integrity")


def log_module_sha256(module_file: str, module_logger: logging.Logger, module_name: str) -> str:
    """Compute and log a module SHA-256 digest."""
    digest = hashlib.sha256(Path(module_file).read_bytes()).hexdigest()
    module_logger.info(
        "module_sha256",
        extra={
            "event": "module_sha256",
            "module_name": module_name,
            "module_file": module_file,
            "sha256": digest,
        },
    )
    return digest


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
