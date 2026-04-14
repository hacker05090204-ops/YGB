from __future__ import annotations

import json

import numpy as np
import pytest

import backend.training.deep_rl_agent as deep_rl_module
from backend.training.deep_rl_agent import DeepRLAgent, SklearnFeatureAugmenter
from backend.training.rl_feedback import RewardBuffer


def test_deep_rl_agent_records_real_outcomes_and_recomputes_normalized_rewards(
    tmp_path,
):
    episodes_path = tmp_path / "deep_rl_episodes.json"
    reward_buffer_path = tmp_path / "deep_rl_reward_buffer.json"
    agent = DeepRLAgent(
        episodes_path=episodes_path,
        reward_buffer_path=reward_buffer_path,
        normalization_window=16,
    )

    correct_episode = agent.record_outcome(
        sample_id="sample-critical-ok",
        cve_id="CVE-2026-9001",
        predicted_severity="CRITICAL",
        actual_severity="CRITICAL",
        source="manual_review",
    )
    missed_episode = agent.record_outcome(
        sample_id="sample-critical-miss",
        cve_id="CVE-2026-9002",
        predicted_severity="LOW",
        actual_severity="CRITICAL",
        source="manual_review",
    )

    assert correct_episode.reward == pytest.approx(1.0)
    assert missed_episode.reward < -0.5

    snapshot = agent.snapshot()
    normalized_rewards = np.asarray(
        [episode.normalized_reward for episode in snapshot],
        dtype=np.float32,
    )
    assert np.isfinite(normalized_rewards).all()
    assert float(normalized_rewards.mean()) == pytest.approx(0.0, abs=1e-6)

    persisted_payload = json.loads(episodes_path.read_text(encoding="utf-8"))
    assert len(persisted_payload) == 2
    assert persisted_payload[-1]["actual_severity"] == "CRITICAL"

    reward_buffer = RewardBuffer.load(path=reward_buffer_path)
    reward_signals = reward_buffer.snapshot()
    assert len(reward_signals) == 2
    assert reward_signals[-1].reward == pytest.approx(missed_episode.reward)


def test_sklearn_feature_augmenter_increases_feature_width_and_persists_state(
    tmp_path,
):
    state_path = tmp_path / "deep_rl_sklearn_state.pkl"
    metadata_path = tmp_path / "deep_rl_sklearn_state.json"
    if not deep_rl_module.SKLEARN_AVAILABLE:
        with pytest.raises(RuntimeError, match="scikit-learn"):
            SklearnFeatureAugmenter(
                state_path=state_path,
                metadata_path=metadata_path,
                auto_load=False,
            )
        return

    rng = np.random.default_rng(42)
    features = rng.normal(loc=0.0, scale=1.0, size=(100, 267)).astype(np.float32)
    augmenter = SklearnFeatureAugmenter(
        state_path=state_path,
        metadata_path=metadata_path,
        n_components=24,
        auto_load=False,
    )

    augmented = augmenter.fit_transform(features)

    assert augmented.shape[0] == 100
    assert augmented.shape[1] > 267
    assert state_path.exists()
    assert metadata_path.exists()

    reloaded = SklearnFeatureAugmenter(
        state_path=state_path,
        metadata_path=metadata_path,
        auto_load=True,
    )
    transformed = reloaded.transform(features[:5])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert transformed.shape[1] == augmented.shape[1]
    assert metadata["input_dim"] == 267
    assert metadata["augmented_dim"] == augmented.shape[1]
