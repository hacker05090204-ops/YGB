"""MODE-B verified label injection for supervised fine-tuning."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import torch
from torch import nn

from backend.ingestion._integrity import log_module_sha256
from backend.observability.metrics import metrics_registry
from impl_v1.phase49.governors.g38_self_trained_model import can_ai_verify_bug

logger = logging.getLogger("ygb.training.label_injector")
ALLOWED_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"})
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class VerifiedBugLabel:
    sample_sha256: str
    is_bug: bool
    severity: str
    confirmed_by: str
    confirmed_at: datetime
    proof_hash: str


def _is_valid_sha256(value: str) -> bool:
    return bool(SHA256_PATTERN.match(value))


def load_verified_labels(path: str = "secure_data/verified_labels.jsonl") -> list[VerifiedBugLabel]:
    labels: list[VerifiedBugLabel] = []
    label_path = Path(path)
    if not label_path.exists():
        return labels

    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            required = {"sample_sha256", "is_bug", "severity", "confirmed_by", "confirmed_at", "proof_hash"}
            if not required.issubset(payload):
                raise ValueError("missing required fields")
            if payload["severity"] not in ALLOWED_SEVERITIES:
                raise ValueError("invalid severity")
            if not str(payload["confirmed_by"]).strip():
                raise ValueError("empty confirmed_by")
            if not _is_valid_sha256(str(payload["sample_sha256"])) or not _is_valid_sha256(str(payload["proof_hash"])):
                raise ValueError("invalid sha256")
            confirmed_at = datetime.fromisoformat(str(payload["confirmed_at"]).replace("Z", "+00:00"))
            if confirmed_at.tzinfo is None:
                raise ValueError("confirmed_at must be timezone-aware")
            labels.append(
                VerifiedBugLabel(
                    sample_sha256=str(payload["sample_sha256"]),
                    is_bug=bool(payload["is_bug"]),
                    severity=str(payload["severity"]),
                    confirmed_by=str(payload["confirmed_by"]).strip(),
                    confirmed_at=confirmed_at,
                    proof_hash=str(payload["proof_hash"]),
                )
            )
        except Exception as exc:
            logger.warning("Skipping malformed MODE-B label line %s: %s", line_number, exc)
    return labels


def load_human_override(path: str = "secure_data/mode_b_override.json") -> bool:
    override_path = Path(path)
    if not override_path.exists():
        return False

    try:
        payload = json.loads(override_path.read_text(encoding="utf-8"))
        if payload.get("human_override") is not True:
            return False
        authorized_by = str(payload.get("authorized_by", "")).strip()
        if not authorized_by:
            return False
        authorized_at = datetime.fromisoformat(str(payload.get("authorized_at", "")).replace("Z", "+00:00"))
        if authorized_at.tzinfo is None:
            return False
        logger.info("MODE-B override loaded, authorized by %s", authorized_by)
        return True
    except Exception:
        return False


def _label_to_tensor(label: VerifiedBugLabel) -> torch.Tensor:
    seed = bytes.fromhex(label.sample_sha256 + label.proof_hash)
    values = list(seed)
    expanded = [values[index % len(values)] / 255.0 for index in range(508)]
    severity_value = {
        "CRITICAL": 1.0,
        "HIGH": 0.75,
        "MEDIUM": 0.5,
        "LOW": 0.25,
        "INFO": 0.1,
    }[label.severity]
    structured = [severity_value, 1.0 if label.is_bug else 0.0, 1.0, len(label.confirmed_by) / 64.0]
    return torch.tensor(expanded + structured, dtype=torch.float32)


def inject_labels_into_training(labels, model, optimizer, device) -> None:
    if can_ai_verify_bug()[0]:
        raise RuntimeError("GUARD VIOLATED")
    if not load_human_override():
        raise PermissionError("MODE-B requires human override")
    if len(labels) == 0:
        logger.warning("no labels to inject")
        return

    metrics_registry.set_gauge("mode_b_active", 1.0)
    positive_count = sum(1 for label in labels if label.is_bug)
    negative_count = len(labels) - positive_count
    logger.info("MODE-B injection: %s bugs, %s non-bugs", positive_count, negative_count)

    features = torch.stack([_label_to_tensor(label) for label in labels]).to(device)
    targets = torch.tensor([1 if label.is_bug else 0 for label in labels], dtype=torch.long, device=device)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor([1.0, 3.0], dtype=torch.float32, device=device))

    model.train()
    optimizer.zero_grad(set_to_none=True)
    outputs = model(features)
    loss = criterion(outputs, targets)
    loss.backward()
    optimizer.step()

    metrics_registry.set_gauge("mode_b_samples_trained", float(len(labels)))
    metrics_registry.set_gauge("mode_b_active", 0.0)


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
