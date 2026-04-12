from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_python_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=run_env,
        check=False,
    )


def test_clean_repo_help_succeeds():
    result = _run_python_script("scripts/clean_repo.py", "--help")

    assert result.returncode == 0, result.stderr
    assert "Safely clean repo-generated artifacts." in result.stdout


def test_clean_repo_dry_run_runs_without_crash():
    result = _run_python_script("scripts/clean_repo.py", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Dry-run mode active." in result.stdout


def test_clean_repo_execute_mode_runs_without_crash_in_temp_repo(tmp_path):
    from scripts.clean_repo import RepoClean

    (tmp_path / "__pycache__").mkdir()
    stale_log = tmp_path / "stale.log"
    stale_log.write_text("stale", encoding="utf-8")
    stale_mtime = time.time() - (8 * 86400)
    os.utime(stale_log, (stale_mtime, stale_mtime))
    stale_safetensors_tmp = tmp_path / "feature_store" / "sample.safetensors.tmp"
    stale_safetensors_tmp.parent.mkdir(parents=True, exist_ok=True)
    stale_safetensors_tmp.write_text("tmp", encoding="utf-8")
    stale_tmp_mtime = time.time() - ((RepoClean.TEMP_RETENTION_DAYS + 1) * 86400)
    os.utime(stale_safetensors_tmp, (stale_tmp_mtime, stale_tmp_mtime))
    stale_description_tmp = tmp_path / "feature_store" / "sample.descriptions.jsonl.tmp"
    stale_description_tmp.write_text("tmp", encoding="utf-8")
    os.utime(stale_description_tmp, (stale_tmp_mtime, stale_tmp_mtime))

    result = RepoClean(repo_root=tmp_path, dry_run=False).run()

    assert result == 0
    assert not (tmp_path / "__pycache__").exists()
    assert not stale_log.exists()
    assert not stale_safetensors_tmp.exists()
    assert not stale_description_tmp.exists()
    clean_log = tmp_path / "scripts" / "clean_log.txt"
    assert clean_log.exists()
    clean_log_text = clean_log.read_text(encoding="utf-8")
    assert "stale.log" in clean_log_text
    assert "sample.safetensors.tmp" in clean_log_text
    assert "sample.descriptions.jsonl.tmp" in clean_log_text


def test_expert_task_queue_direct_execution_prints_status(tmp_path):
    status_path = tmp_path / "experts_status.json"
    result = _run_python_script(
        "scripts/expert_task_queue.py",
        env={"YGB_EXPERT_STATUS_PATH": str(status_path)},
    )

    assert result.returncode == 0, result.stderr
    assert "updated_at=" in result.stdout
    assert "summary: available=" in result.stdout
    assert status_path.exists()


def test_device_agent_help_supports_direct_execution():
    result = _run_python_script("scripts/device_agent.py", "--help")

    assert result.returncode == 0, result.stderr
    assert "--worker-id" in result.stdout
    assert "--print-queue-status" in result.stdout


def test_migrate_json_features_help_succeeds():
    result = _run_python_script("scripts/migrate_json_features_to_safetensors.py", "--help")

    assert result.returncode == 0, result.stderr
    assert "Migrate learned-feature JSON reports into .safetensors feature shards." in result.stdout


def test_migrate_json_features_cli_skips_missing_file_gracefully(tmp_path):
    missing_path = tmp_path / "missing_features.json"
    output_root = tmp_path / "features_safetensors"
    result = _run_python_script(
        "scripts/migrate_json_features_to_safetensors.py",
        str(missing_path),
        "--output-root",
        str(output_root),
    )

    assert result.returncode == 0, result.stderr
    assert "Migrated 0 JSON learned-feature file(s) into" in result.stdout
    assert "skipped 1 unsupported file(s)" in result.stdout
    assert not output_root.exists()


def test_run_ybg_training_colab_help_succeeds():
    result = _run_python_script("scripts/run_ybg_training_colab.py", "--help")

    assert result.returncode == 0, result.stderr
    assert "Run real CVE severity training in Colab with GRPO or Agent Lightning fallback." in result.stdout


def test_start_vllm_local_script_documents_ngrok_guidance():
    script_path = PROJECT_ROOT / "scripts" / "start_vllm_local.sh"
    script_text = script_path.read_text(encoding="utf-8")

    assert script_path.exists()
    assert "YBG_VLLM_MODEL" in script_text
    assert "YBG_VLLM_PORT" in script_text
    assert "ngrok" in script_text.lower()


def test_colab_ddp_quickstart_documents_ngrok_and_preflight():
    doc_path = PROJECT_ROOT / "docs" / "colab_ddp_quickstart.md"
    doc_text = doc_path.read_text(encoding="utf-8")

    assert doc_path.exists()
    assert "ngrok" in doc_text.lower()
    assert "YGB_VLLM_HOST" in doc_text
    assert "--dry-run" in doc_text
    assert "YGB_DDP_ADDR" in doc_text
    assert "YGB_DDP_PORT" in doc_text
    assert "run_rtx3050_follower.py" in doc_text
