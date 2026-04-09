from __future__ import annotations

from pathlib import Path

import run_leader_ddp


def test_run_leader_ddp_imports_expert_task_queue_without_error():
    assert run_leader_ddp.ExpertTaskQueue.__name__ == "ExpertTaskQueue"


def test_run_leader_ddp_reads_master_port_from_env(monkeypatch):
    monkeypatch.setenv("YGB_DDP_PORT", "29642")

    config = run_leader_ddp.build_leader_config()

    assert config.master_port == 29642


def test_launch_training_script_contains_expected_modes_and_dispatch():
    contents = Path("scripts/launch_training.sh").read_text(encoding="utf-8")

    assert 'export YGB_USE_MOE=true' in contents
    assert 'export YGB_DDP_PORT="${YGB_DDP_PORT:-29500}"' in contents
    assert 'export YGB_DDP_ADDR="${YGB_DDP_ADDR:-127.0.0.1}"' in contents
    assert 'case "$MODE" in' in contents
    assert 'leader)' in contents
    assert 'follower)' in contents
    assert 'agent)' in contents
    assert 'exec python run_leader_ddp.py "$@"' in contents
    assert 'exec python run_rtx3050_follower.py "$@"' in contents
    assert 'exec python scripts/device_agent.py "$@"' in contents
