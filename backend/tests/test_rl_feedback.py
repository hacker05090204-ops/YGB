from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.training.rl_feedback import OutcomeSignal, RLFeedbackCollector, RewardBuffer


def test_exploit_confirmed_rewards_high_prediction(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    collector = RLFeedbackCollector(reward_buffer=reward_buffer)
    collector.record_prediction(
        sample_id="sample-high",
        cve_id="CVE-2026-1111",
        predicted_severity="HIGH",
    )

    added_signals = collector.process_new_cisa_kev_batch(["CVE-2026-1111"])

    assert added_signals == 1
    assert reward_buffer.snapshot()[0].reward == pytest.approx(1.0)


def test_exploit_confirmed_penalizes_low_prediction(tmp_path):
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    collector = RLFeedbackCollector(reward_buffer=reward_buffer)
    collector.record_prediction(
        sample_id="sample-low",
        cve_id="CVE-2026-2222",
        predicted_severity="LOW",
    )

    added_signals = collector.process_new_cisa_kev_batch(["CVE-2026-2222"])

    assert added_signals == 1
    assert reward_buffer.snapshot()[0].reward == pytest.approx(-0.5)


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
    )

    assert added_signals == 1
    assert reward_buffer.snapshot()[0].reward == pytest.approx(0.5)


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
