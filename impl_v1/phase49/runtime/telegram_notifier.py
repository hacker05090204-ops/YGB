import logging
import os
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Optional

logger = logging.getLogger("g38.telegram")

_DEFAULT_TRAINING_EVENTS = frozenset({
    "CHECKPOINT_SAVED",
    "CONTINUOUS_START",
    "CONTINUOUS_STOP",
    "EARLY_STOP",
    "ERROR",
    "REPORT_GENERATED",
    "TRAINING_ABORTED",
    "TRAINING_STARTED",
    "TRAINING_STOPPED",
})


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_enabled_events(raw_value: str) -> FrozenSet[str]:
    if not raw_value.strip():
        return _DEFAULT_TRAINING_EVENTS
    return frozenset(
        part.strip().upper()
        for part in raw_value.split(",")
        if part.strip()
    )


@dataclass(frozen=True)
class TrainingTelegramNotifier:
    bot_token: str
    chat_id: str
    enabled_events: FrozenSet[str]
    status_url: str = ""

    def notify(self, event: Any, status: Optional[Dict[str, Any]] = None) -> None:
        event_type = str(getattr(event, "event_type", "") or "").upper()
        if not event_type or event_type not in self.enabled_events:
            return
        message = self._format_message(event, status or {})
        threading.Thread(
            target=self._send_message,
            args=(message,),
            name="ygb-telegram-notify",
            daemon=True,
        ).start()

    def _format_message(self, event: Any, status: Dict[str, Any]) -> str:
        lines = [
            "YGB training update",
            f"Event: {getattr(event, 'event_type', 'UNKNOWN')}",
            f"Details: {getattr(event, 'details', '')}",
        ]

        epoch = getattr(event, "epoch", None)
        if epoch is not None:
            lines.append(f"Epoch: {epoch}")

        state = status.get("state")
        if state:
            lines.append(f"State: {state}")

        progress = status.get("progress")
        if progress not in (None, ""):
            lines.append(f"Progress: {progress}%")

        accuracy = status.get("last_accuracy")
        if isinstance(accuracy, (int, float)) and accuracy > 0:
            lines.append(f"Accuracy: {accuracy:.2%}")

        holdout_accuracy = status.get("last_holdout_accuracy")
        if isinstance(holdout_accuracy, (int, float)) and holdout_accuracy > 0:
            lines.append(f"Holdout: {holdout_accuracy:.2%}")

        loss = status.get("last_loss")
        if isinstance(loss, (int, float)) and loss > 0:
            lines.append(f"Loss: {loss:.4f}")

        samples_per_sec = status.get("samples_per_sec")
        if isinstance(samples_per_sec, (int, float)) and samples_per_sec > 0:
            lines.append(f"Throughput: {samples_per_sec:.1f} samples/s")

        if self.status_url:
            lines.append(f"Dashboard: {self.status_url}")

        timestamp = getattr(event, "timestamp", "")
        if timestamp:
            lines.append(f"Time: {timestamp}")

        return "\n".join(lines)

    def _send_message(self, message: str) -> None:
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if getattr(response, "status", 200) >= 400:
                    raise RuntimeError(f"telegram_http_{response.status}")
        except Exception as exc:
            logger.warning("Telegram training notification failed: %s", exc)


def build_training_telegram_notifier_from_env() -> Optional[TrainingTelegramNotifier]:
    if not _env_flag("YGB_TELEGRAM_ENABLED", default=False):
        return None

    bot_token = os.environ.get("YGB_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("YGB_TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        logger.warning(
            "Telegram training notifications requested but bot token/chat id is missing"
        )
        return None

    status_url = (
        os.environ.get("YGB_TELEGRAM_STATUS_URL", "").strip()
        or os.environ.get("FRONTEND_URL", "").strip()
    )
    enabled_events = _parse_enabled_events(
        os.environ.get("YGB_TELEGRAM_NOTIFY_EVENTS", "")
    )
    return TrainingTelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        enabled_events=enabled_events,
        status_url=status_url,
    )
