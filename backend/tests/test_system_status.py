from __future__ import annotations

import json
from pathlib import Path

from backend.api.system_status_store import SYSTEM_STATUS_PATH, refresh_system_status_file


def test_system_status_file_exists():
    refresh_system_status_file()
    assert SYSTEM_STATUS_PATH.exists()


def test_system_status_schema_valid():
    refresh_system_status_file()
    with open(SYSTEM_STATUS_PATH, encoding="utf-8") as handle:
        status = json.load(handle)

    assert status["schema_version"] == 2
    assert "last_updated" in status
    assert set(status) == {"schema_version", "last_updated", "training", "ingestion", "sync", "gpu"}
    assert isinstance(status["training"]["last_accuracy"], float)
    assert isinstance(status["training"]["precision_breach"], bool)
    assert isinstance(status["training"]["checkpoint_sha256"], str)
    assert isinstance(status["ingestion"]["sources_active"], list)
    assert isinstance(status["sync"]["peers_connected"], int)
    assert isinstance(status["gpu"]["available"], bool)


def test_precision_breach_matches_runtime_status():
    refresh_system_status_file()
    canonical = json.loads(SYSTEM_STATUS_PATH.read_text(encoding="utf-8"))
    runtime_status = json.loads(Path("data/runtime_status.json").read_text(encoding="utf-8"))
    assert canonical["training"]["precision_breach"] == runtime_status["precision_breach"]
