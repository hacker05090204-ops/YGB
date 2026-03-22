from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import torch

from backend.observability.metrics import metrics_registry
from backend.training.label_injector import (
    VerifiedBugLabel,
    _is_valid_sha256,
    _label_to_tensor,
    inject_labels_into_training,
    load_human_override,
    load_verified_labels,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield


def _valid_label_payload() -> dict[str, object]:
    return {
        "sample_sha256": "a" * 64,
        "is_bug": True,
        "severity": "HIGH",
        "confirmed_by": "analyst",
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "proof_hash": "b" * 64,
    }


def test_load_verified_labels_filters_invalid_entries(tmp_path):
    label_path = tmp_path / "verified_labels.jsonl"
    payload = _valid_label_payload()
    invalid = {"severity": "NOPE"}
    label_path.write_text(
        "\n".join([json.dumps(payload), json.dumps(invalid), "", json.dumps({**payload, "proof_hash": "x"})]),
        encoding="utf-8",
    )

    labels = load_verified_labels(str(label_path))

    assert len(labels) == 1
    assert isinstance(labels[0], VerifiedBugLabel)
    assert labels[0].severity == "HIGH"


def test_load_verified_labels_handles_missing_and_validation_edges(tmp_path):
    assert load_verified_labels(str(tmp_path / "missing.jsonl")) == []

    label_path = tmp_path / "verified_labels.jsonl"
    payload = _valid_label_payload()
    label_path.write_text(
        "\n".join(
            [
                json.dumps({**payload, "severity": "BROKEN"}),
                json.dumps({**payload, "confirmed_by": ""}),
                json.dumps({**payload, "confirmed_at": datetime.now().isoformat()}),
            ]
        ),
        encoding="utf-8",
    )

    assert load_verified_labels(str(label_path)) == []


def test_load_human_override_requires_valid_payload(tmp_path):
    override_path = tmp_path / "mode_b_override.json"
    override_path.write_text(json.dumps({"human_override": False}), encoding="utf-8")
    assert load_human_override(str(override_path)) is False

    override_path.write_text(
        json.dumps(
            {
                "human_override": True,
                "authorized_by": "human",
                "authorized_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    assert load_human_override(str(override_path)) is True


def test_load_human_override_handles_missing_and_invalid_payloads(tmp_path):
    assert load_human_override(str(tmp_path / "missing.json")) is False

    override_path = tmp_path / "mode_b_override.json"
    override_path.write_text(
        json.dumps({"human_override": True, "authorized_by": "", "authorized_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    assert load_human_override(str(override_path)) is False

    override_path.write_text(
        json.dumps({"human_override": True, "authorized_by": "human", "authorized_at": datetime.now().isoformat()}),
        encoding="utf-8",
    )
    assert load_human_override(str(override_path)) is False

    override_path.write_text("{not-json", encoding="utf-8")
    assert load_human_override(str(override_path)) is False


def test_label_helpers_and_guard_paths(monkeypatch):
    payload = _valid_label_payload()
    label = VerifiedBugLabel(
        sample_sha256=payload["sample_sha256"],
        is_bug=payload["is_bug"],
        severity=payload["severity"],
        confirmed_by=payload["confirmed_by"],
        confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"])),
        proof_hash=payload["proof_hash"],
    )

    assert _is_valid_sha256("a" * 64) is True
    assert _is_valid_sha256("short") is False
    assert _label_to_tensor(label).shape[0] == 512

    model = torch.nn.Linear(512, 2)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)

    monkeypatch.setattr("backend.training.label_injector.can_ai_verify_bug", lambda: (True, "blocked"))
    with pytest.raises(RuntimeError, match="GUARD VIOLATED"):
        inject_labels_into_training([label], model, optimizer, "cpu")

    monkeypatch.setattr("backend.training.label_injector.can_ai_verify_bug", lambda: (False, "allowed"))
    monkeypatch.setattr("backend.training.label_injector.load_human_override", lambda: False)
    with pytest.raises(PermissionError):
        inject_labels_into_training([label], model, optimizer, "cpu")


def test_label_injection_no_labels_and_training(monkeypatch):
    payload = _valid_label_payload()
    positive = VerifiedBugLabel(
        sample_sha256=payload["sample_sha256"],
        is_bug=True,
        severity="HIGH",
        confirmed_by="analyst",
        confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"])),
        proof_hash=payload["proof_hash"],
    )
    negative = VerifiedBugLabel(
        sample_sha256="c" * 64,
        is_bug=False,
        severity="LOW",
        confirmed_by="reviewer",
        confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"])),
        proof_hash="d" * 64,
    )
    model = torch.nn.Linear(512, 2)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    before = model.weight.detach().clone()

    monkeypatch.setattr("backend.training.label_injector.can_ai_verify_bug", lambda: (False, "allowed"))
    monkeypatch.setattr("backend.training.label_injector.load_human_override", lambda: True)

    inject_labels_into_training([], model, optimizer, "cpu")
    inject_labels_into_training([positive, negative], model, optimizer, "cpu")

    assert metrics_registry.get_gauge("mode_b_samples_trained") == 2.0
    assert metrics_registry.get_gauge("mode_b_active") == 0.0
    assert not torch.equal(before, model.weight.detach())
