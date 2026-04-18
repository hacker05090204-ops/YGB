from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import backend.training.rl_feedback as rl_feedback_module
from backend.training.rl_feedback import (
    OutcomeSignal,
    RLFeedbackCollector,
    RewardBuffer,
    normalize_rewards,
)


def test_exploit_confirmed_rewards_exact_critical_prediction(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    collector = RLFeedbackCollector(reward_buffer=reward_buffer)
    collector.record_prediction(
        sample_id="sample-critical",
        cve_id="CVE-2026-1111",
        predicted_severity="CRITICAL",
    )

    added_signals = collector.process_new_cisa_kev_batch(["CVE-2026-1111"])

    assert added_signals == 1
    assert reward_buffer.snapshot()[0].reward == pytest.approx(1.0)
    assert reward_buffer.snapshot()[0].metadata["reward_kind"] == "kev_exact_critical_hit"


def test_exploit_confirmed_penalizes_missed_critical_prediction(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    collector = RLFeedbackCollector(reward_buffer=reward_buffer)
    collector.record_prediction(
        sample_id="sample-high",
        cve_id="CVE-2026-2222",
        predicted_severity="HIGH",
    )

    added_signals = collector.process_new_cisa_kev_batch(["CVE-2026-2222"])

    assert added_signals == 1
    assert reward_buffer.snapshot()[0].reward < 0.0
    assert reward_buffer.snapshot()[0].metadata["reward_kind"] == "kev_missed_critical"


def test_severity_update_rewards_correct_prediction(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    collector = RLFeedbackCollector(reward_buffer=reward_buffer)
    collector.record_prediction(
        sample_id="sample-update",
        cve_id="CVE-2026-3333",
        predicted_severity="HIGH",
    )

    added_signals = collector.process_severity_update(
        "CVE-2026-3333",
        "LOW",
        "HIGH",
        "nvd",
    )

    assert added_signals == 1
    assert reward_buffer.snapshot()[0].reward > 0.0
    assert reward_buffer.snapshot()[0].source == "nvd"
    assert reward_buffer.snapshot()[0].metadata["signal_source"] == "nvd"
    assert reward_buffer.snapshot()[0].metadata["severity_delta"] == "2"


def test_normalize_rewards_uses_grpo_style_group_normalization() -> None:
    normalized = normalize_rewards(
        {"sample-a": 2.0, "sample-b": 0.0},
        group_size=2,
    )

    assert normalized["sample-a"] == pytest.approx(1.0, abs=1e-5)
    assert normalized["sample-b"] == pytest.approx(-1.0, abs=1e-5)


def test_weighted_signals_respects_recency_cutoff(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    now = datetime(2026, 4, 8, tzinfo=timezone.utc)
    reward_buffer.add(
        OutcomeSignal(
            sample_id="sample-recent",
            cve_id="CVE-2026-4444",
            predicted_severity="HIGH",
            outcome="kev_exploit_confirmed",
            reward=1.0,
            source="cisa_kev",
            observed_at=(now - timedelta(days=3)).isoformat(),
        )
    )
    reward_buffer.add(
        OutcomeSignal(
            sample_id="sample-old",
            cve_id="CVE-2026-5555",
            predicted_severity="HIGH",
            outcome="kev_exploit_confirmed",
            reward=1.0,
            source="cisa_kev",
            observed_at=(now - timedelta(days=45)).isoformat(),
        )
    )

    weighted_signals = reward_buffer.get_weighted_signals(now=now, max_age_days=30)

    assert "sample-recent" in weighted_signals
    assert weighted_signals["sample-recent"] > 0.0
    assert "sample-old" not in weighted_signals


def test_collector_get_weighted_signals_returns_real_recency_weighted_feedback(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    collector = RLFeedbackCollector(reward_buffer=reward_buffer)
    now = datetime(2026, 4, 8, tzinfo=timezone.utc)
    reward_buffer.add(
        OutcomeSignal(
            sample_id="sample-weighted",
            cve_id="CVE-2026-7777",
            predicted_severity="HIGH",
            outcome="kev_exploit_confirmed",
            reward=1.0,
            source="cisa_kev",
            observed_at=(now - timedelta(days=7)).isoformat(),
        )
    )

    weighted_signals = collector.get_weighted_signals(
        now=now,
        max_age_days=30,
        half_life_days=7,
    )

    assert weighted_signals["sample-weighted"] == pytest.approx(0.5)


def test_export_rewards_for_al_uses_real_stored_feedback(tmp_path, monkeypatch):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    reward_buffer.add(
        OutcomeSignal(
            sample_id="sample-export",
            cve_id="CVE-2026-6666",
            predicted_severity="HIGH",
            outcome="kev_exploit_confirmed",
            reward=1.0,
            source="cisa_kev",
        )
    )
    monkeypatch.setattr(rl_feedback_module, "get_reward_buffer", lambda: reward_buffer)

    exported = rl_feedback_module.export_rewards_for_al()

    assert exported == [
        {
            "task_id": "CVE-2026-6666",
            "reward": pytest.approx(1.0),
            "outcome_type": "kev_exploit_confirmed",
            "source": "cisa_kev",
        }
    ]
