from __future__ import annotations

import importlib
from pathlib import Path

import run_leader_ddp
from scripts.expert_task_queue import ExpertTaskQueue


def test_leader_reads_expert_from_queue(tmp_path):
    queue = ExpertTaskQueue(status_path=tmp_path / "experts_status.json")
    queue.initialize_status_file()

    claimed, claim_mode = run_leader_ddp._claim_leader_expert(queue, "leader-worker")

    assert claimed is not None
    assert claim_mode == "claimed"
    assert int(claimed["expert_id"]) >= 0

    state = queue.load_status()
    claimed_record = next(
        item
        for item in state["experts"]
        if int(item.get("expert_id", -1)) == int(claimed["expert_id"])
    )
    assert claimed_record["status"] == "CLAIMED"
    assert claimed_record["claimed_by"] == "leader-worker"


def test_ddp_port_comes_from_env(monkeypatch):
    monkeypatch.setenv("YGB_DDP_PORT", "29642")
    reloaded_module = importlib.reload(run_leader_ddp)
    try:
        config = reloaded_module.build_leader_config()

        assert reloaded_module.MASTER_PORT == 29642
        assert reloaded_module.get_master_port() == 29642
        assert config.master_port == 29642
    finally:
        monkeypatch.delenv("YGB_DDP_PORT", raising=False)
        importlib.reload(reloaded_module)


def test_follower_connects_to_env_address_without_claiming():
    follower_path = Path("run_rtx3050_follower.py")
    contents = follower_path.read_text(encoding="utf-8")

    assert 'os.getenv("YGB_DDP_ADDR", "127.0.0.1")' in contents
    assert 'os.getenv("YGB_DDP_PORT", "29500")' in contents
    assert 'master_addr = get_master_addr()' in contents
    assert 'master_port = get_master_port()' in contents
    assert 'master_addr=master_addr' in contents
    assert 'master_port=master_port' in contents
    assert 'queue.claim_next_expert' not in contents


def test_launch_script_supports_leader_follower_and_agent_modes():
    script_path = Path("scripts/launch_training.sh")
    contents = script_path.read_text(encoding="utf-8")

    assert script_path.exists()
    assert contents.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in contents
    assert 'Usage: $0 {leader|follower|agent} [args...]' in contents
    assert 'export YGB_DDP_PORT="${YGB_DDP_PORT:-29500}"' in contents
    assert 'export YGB_DDP_ADDR="${YGB_DDP_ADDR:-127.0.0.1}"' in contents
    assert 'case "$MODE" in' in contents
    assert 'leader)' in contents
    assert 'follower)' in contents
    assert 'agent)' in contents
    assert 'exec "${PYTHON_BIN}" run_leader_ddp.py "$@"' in contents
    assert 'exec "${PYTHON_BIN}" run_rtx3050_follower.py "$@"' in contents
    assert 'exec "${PYTHON_BIN}" scripts/device_agent.py "$@"' in contents


def test_colab_quickstart_includes_ngrok_and_vllm_validation_guidance():
    doc_path = Path("docs/colab_ddp_quickstart.md")
    doc_text = doc_path.read_text(encoding="utf-8")

    assert doc_path.exists()
    assert "ngrok" in doc_text.lower()
    assert "YBG_VLLM_HOST" in doc_text
    assert "YGB_VLLM_HOST" in doc_text
    assert "YGB_DDP_ADDR" in doc_text
    assert "YGB_DDP_PORT" in doc_text
    assert "--dry-run" in doc_text
    assert '"status": "ok"' in doc_text
    assert "model list" in doc_text.lower()
    assert "run_rtx3050_follower.py" in doc_text
