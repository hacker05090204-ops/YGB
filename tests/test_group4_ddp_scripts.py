from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest

import run_leader_ddp
from scripts.expert_task_queue import ExpertTaskQueue


def test_run_leader_ddp_imports_expert_task_queue_without_error():
    assert run_leader_ddp.ExpertTaskQueue.__name__ == "ExpertTaskQueue"


def test_run_leader_ddp_reads_master_port_from_env(monkeypatch):
    monkeypatch.setenv("YGB_DDP_PORT", "29642")
    reloaded_module = importlib.reload(run_leader_ddp)
    try:
        config = reloaded_module.build_leader_config()

        assert reloaded_module.MASTER_PORT == 29642
        assert config.master_port == 29642
    finally:
        monkeypatch.delenv("YGB_DDP_PORT", raising=False)
        importlib.reload(reloaded_module)


def test_run_leader_ddp_reads_master_addr_from_env(monkeypatch):
    monkeypatch.setenv("YGB_DDP_ADDR", "10.10.10.5")
    reloaded_module = importlib.reload(run_leader_ddp)
    try:
        config = reloaded_module.build_leader_config()

        assert reloaded_module.MASTER_ADDR == "10.10.10.5"
        assert config.master_addr == "10.10.10.5"
    finally:
        monkeypatch.delenv("YGB_DDP_ADDR", raising=False)
        importlib.reload(reloaded_module)


def test_run_leader_ddp_reuses_existing_leader_claim(tmp_path):
    queue = ExpertTaskQueue(status_path=tmp_path / "experts_status.json")
    queue.initialize_status_file()
    first_claim = queue.claim_next_expert("leader-worker", claim_timeout_seconds=60.0)

    claimed, claim_mode = run_leader_ddp._claim_leader_expert(queue, "leader-worker")

    assert first_claim is not None
    assert claimed is not None
    assert claim_mode == "resumed"
    assert int(claimed["expert_id"]) == int(first_claim["expert_id"])
    state = queue.load_status()
    claimed_records = [item for item in state["experts"] if item["status"] == "CLAIMED"]
    assert len(claimed_records) == 1


def test_run_leader_ddp_rejects_foreign_claimants(tmp_path):
    queue = ExpertTaskQueue(status_path=tmp_path / "experts_status.json")
    queue.initialize_status_file()
    queue.claim_next_expert("other-worker", claim_timeout_seconds=60.0)

    with pytest.raises(RuntimeError, match="only claimant"):
        run_leader_ddp._claim_leader_expert(queue, "leader-worker")


def test_run_rtx3050_follower_uses_env_target_without_claiming():
    follower_path = Path("run_rtx3050_follower.py")
    contents = follower_path.read_text(encoding="utf-8")

    assert 'os.getenv("YGB_DDP_ADDR", "127.0.0.1")' in contents
    assert 'os.getenv("YGB_DDP_PORT", "29500")' in contents
    assert 'queue.claim_next_expert' not in contents
    assert 'YGB_EXPERT_FIELD_NAME' in contents
    assert 'claimed_by' in contents


def test_launch_training_script_contains_expected_modes_and_dispatch():
    script_path = Path("scripts/launch_training.sh")
    script_arg = script_path.as_posix()
    contents = script_path.read_text(encoding="utf-8")

    assert script_path.exists()
    assert contents.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in contents
    assert 'PYTHON_BIN="${PYTHON_BIN:-python}"' in contents
    assert 'export YGB_USE_MOE=true' in contents
    assert 'export YGB_DDP_PORT="${YGB_DDP_PORT:-29500}"' in contents
    assert 'export YGB_DDP_ADDR="${YGB_DDP_ADDR:-127.0.0.1}"' in contents
    assert 'case "$MODE" in' in contents
    assert 'leader)' in contents
    assert 'follower)' in contents
    assert 'agent)' in contents
    assert 'export YGB_DDP_ROLE=leader' in contents
    assert 'export YGB_DDP_ROLE=follower' in contents
    assert 'export YGB_DDP_ROLE=agent' in contents
    assert 'exec "${PYTHON_BIN}" run_leader_ddp.py "$@"' in contents
    assert 'exec "${PYTHON_BIN}" run_rtx3050_follower.py "$@"' in contents
    assert 'exec "${PYTHON_BIN}" scripts/device_agent.py "$@"' in contents

    if os.name != "nt":
        assert script_path.stat().st_mode & 0o111

    bash_path = shutil.which("bash")
    if bash_path:
        completed = subprocess.run(
            [bash_path, "-n", script_arg],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
