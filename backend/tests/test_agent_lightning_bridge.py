from __future__ import annotations

import numpy as np
import pytest

import backend.training.agent_lightning_bridge as bridge_module
from backend.training.agent_lightning_bridge import (
    CVESeverityAgent,
    CVETrainingTask,
    YBGDatasetProvider,
)
from backend.training.safetensors_store import SafetensorsFeatureStore


def test_agent_lightning_bridge_imports_cleanly_with_guarded_availability_flag():
    assert isinstance(bridge_module.AL_AVAILABLE, bool)
    assert callable(bridge_module.build_ybg_trainer)


def test_dataset_provider_loads_real_tasks_from_description_sidecars(tmp_path):
    feature_store = SafetensorsFeatureStore(tmp_path / "feature_store")
    feature_store.write(
        "cve_task",
        np.linspace(0.01, 1.01, 256, dtype=np.float32).reshape(1, 256),
        np.asarray([1], dtype=np.int64),
        metadata={
            "sample_cve_id": "CVE-2026-7001",
            "sample_severity": "HIGH",
            "sample_source": "nvd",
        },
    )
    feature_store.write_descriptions(
        "cve_task",
        [
            {
                "row_id": "sha256-1",
                "sample_sha256": "sha256-1",
                "cve_id": "CVE-2026-7001",
                "source": "nvd",
                "severity": "HIGH",
                "raw_text": "A real CVE description from the sidecar store.",
            }
        ],
    )
    provider = YBGDatasetProvider(
        feature_store_root=tmp_path / "feature_store",
        raw_data_root=tmp_path / "raw_data",
    )

    tasks = provider.load_tasks()

    assert len(tasks) == 1
    assert tasks[0].task_id == "CVE-2026-7001"
    assert tasks[0].sample_id == "sha256-1"
    assert "A real CVE description" in tasks[0].prompt


def test_cve_severity_agent_prefers_rl_feedback_reward_over_ground_truth():
    agent = CVESeverityAgent(
        reward_records=[
            {
                "task_id": "CVE-2026-7002",
                "reward": -0.25,
                "outcome_type": "severity_update:LOW",
                "source": "nvd_severity_update",
            }
        ]
    )
    task = CVETrainingTask(
        task_id="CVE-2026-7002",
        sample_id="sample-7002",
        cve_id="CVE-2026-7002",
        source="nvd",
        raw_text="Real CVE text.",
        expected_severity="CRITICAL",
        prompt="Prompt text.",
    )

    result = agent.run(task, predicted_severity="CRITICAL")

    assert result["reward"] == pytest.approx(-0.25)
    assert result["reward_source"] == "rl_feedback"


def test_cve_severity_agent_uses_ground_truth_reward_when_rl_feedback_missing():
    agent = CVESeverityAgent(reward_records=[])
    task = CVETrainingTask(
        task_id="CVE-2026-7003",
        sample_id="sample-7003",
        cve_id="CVE-2026-7003",
        source="nvd",
        raw_text="Real CVE text.",
        expected_severity="HIGH",
        prompt="Prompt text.",
    )

    result = agent.run(task, predicted_severity="HIGH")

    assert result["reward"] == pytest.approx(1.0)
    assert result["reward_source"] == "ground_truth"


def test_cve_severity_agent_penalizes_critical_miss_when_prediction_is_too_low():
    agent = CVESeverityAgent(reward_records=[])
    task = CVETrainingTask(
        task_id="CVE-2026-7004",
        sample_id="sample-7004",
        cve_id="CVE-2026-7004",
        source="nvd",
        raw_text="Real CVE text.",
        expected_severity="CRITICAL",
        prompt="Prompt text.",
    )

    result = agent.run(task, predicted_severity="LOW")

    assert result["reward"] == pytest.approx(-0.5)
    assert result["reward_source"] == "ground_truth"


def test_cve_severity_agent_penalizes_false_critical_prediction_against_low_truth():
    agent = CVESeverityAgent(reward_records=[])
    task = CVETrainingTask(
        task_id="CVE-2026-7005",
        sample_id="sample-7005",
        cve_id="CVE-2026-7005",
        source="nvd",
        raw_text="Real CVE text.",
        expected_severity="LOW",
        prompt="Prompt text.",
    )

    result = agent.run(task, predicted_severity="CRITICAL")

    assert result["reward"] == pytest.approx(-0.5)
    assert result["reward_source"] == "ground_truth"


def test_build_ybg_trainer_fails_honestly_when_agent_lightning_missing(tmp_path, monkeypatch):
    provider = YBGDatasetProvider(
        feature_store_root=tmp_path / "feature_store",
        raw_data_root=tmp_path / "raw_data",
    )
    monkeypatch.setattr(bridge_module, "AL_AVAILABLE", False)
    monkeypatch.setattr(bridge_module, "_agent_lightning_module", None)

    with pytest.raises(RuntimeError, match="Agent Lightning is not installed"):
        bridge_module.build_ybg_trainer(
            dataset_provider=provider,
            agent=CVESeverityAgent(reward_records=[]),
        )
