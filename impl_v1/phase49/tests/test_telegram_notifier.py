from types import SimpleNamespace

from impl_v1.phase49.runtime.telegram_notifier import (
    TrainingTelegramNotifier,
    build_training_telegram_notifier_from_env,
)


def test_build_training_telegram_notifier_from_env_disabled(monkeypatch):
    monkeypatch.delenv("YGB_TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("YGB_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("YGB_TELEGRAM_CHAT_ID", raising=False)

    notifier = build_training_telegram_notifier_from_env()

    assert notifier is None


def test_build_training_telegram_notifier_from_env_reads_defaults(monkeypatch):
    monkeypatch.setenv("YGB_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("YGB_TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("YGB_TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000/control")
    monkeypatch.delenv("YGB_TELEGRAM_NOTIFY_EVENTS", raising=False)

    notifier = build_training_telegram_notifier_from_env()

    assert notifier is not None
    assert notifier.bot_token == "token"
    assert notifier.chat_id == "12345"
    assert notifier.status_url == "http://localhost:3000/control"
    assert "CHECKPOINT_SAVED" in notifier.enabled_events


def test_training_telegram_notifier_formats_training_snapshot():
    notifier = TrainingTelegramNotifier(
        bot_token="token",
        chat_id="12345",
        enabled_events=frozenset({"CHECKPOINT_SAVED"}),
        status_url="http://localhost:3000/control",
    )
    event = SimpleNamespace(
        event_type="CHECKPOINT_SAVED",
        details="Saved MODE-A checkpoint",
        epoch=8,
        timestamp="2026-03-10T12:00:00+00:00",
    )

    message = notifier._format_message(
        event,
        {
            "state": "TRAINING",
            "progress": 80,
            "last_accuracy": 0.93,
            "last_holdout_accuracy": 0.91,
            "last_loss": 0.12,
            "samples_per_sec": 40560.4,
        },
    )

    assert "YGB training update" in message
    assert "Event: CHECKPOINT_SAVED" in message
    assert "Epoch: 8" in message
    assert "Accuracy: 93.00%" in message
    assert "Dashboard: http://localhost:3000/control" in message
