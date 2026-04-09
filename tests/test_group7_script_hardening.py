from __future__ import annotations

import os
import subprocess
import sys
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
