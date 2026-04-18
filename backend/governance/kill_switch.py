"""Persisted emergency kill switch for training governance."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.training.runtime_status_validator import TrainingGovernanceError

try:
    from config.storage_config import REPORTS_DIR
except Exception:
    REPORTS_DIR = Path("data")


logger = logging.getLogger("ygb.governance.kill_switch")
DEFAULT_KILL_SWITCH_PATH = Path(REPORTS_DIR) / "training_kill_switch.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    now = _utc_now()
    return {
        "killed": False,
        "reason": None,
        "actor": None,
        "engaged_at": None,
        "disengaged_at": now,
        "updated_at": now,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _load_state(path: str | Path = DEFAULT_KILL_SWITCH_PATH) -> dict[str, Any]:
    resolved_path = Path(path)
    if not resolved_path.exists():
        return _default_state()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("kill switch state must be a JSON object")
    state = _default_state()
    state.update(payload)
    state["killed"] = bool(state.get("killed", False))
    return state


def engage(
    reason: str = "manual_emergency_stop",
    *,
    actor: str | None = None,
    path: str | Path = DEFAULT_KILL_SWITCH_PATH,
) -> dict[str, Any]:
    """Persist the emergency-stop state and fail all future checks closed."""
    state = _load_state(path)
    timestamp = _utc_now()
    state.update(
        {
            "killed": True,
            "reason": str(reason or "manual_emergency_stop"),
            "actor": None if actor is None else str(actor),
            "engaged_at": timestamp,
            "updated_at": timestamp,
        }
    )
    _atomic_write_json(Path(path), state)
    logger.critical(
        "training kill switch engaged actor=%s reason=%s",
        state.get("actor") or "unknown",
        state["reason"],
    )
    return dict(state)


def disengage(
    reason: str = "manual_reset",
    *,
    actor: str | None = None,
    path: str | Path = DEFAULT_KILL_SWITCH_PATH,
) -> dict[str, Any]:
    """Persistently clear the emergency-stop state."""
    state = _load_state(path)
    timestamp = _utc_now()
    state.update(
        {
            "killed": False,
            "reason": str(reason or "manual_reset"),
            "actor": None if actor is None else str(actor),
            "disengaged_at": timestamp,
            "updated_at": timestamp,
        }
    )
    _atomic_write_json(Path(path), state)
    logger.warning(
        "training kill switch disengaged actor=%s reason=%s",
        state.get("actor") or "unknown",
        state["reason"],
    )
    return dict(state)


def is_killed(path: str | Path = DEFAULT_KILL_SWITCH_PATH) -> bool:
    """Return the persisted kill state. Corrupt state fails closed."""
    try:
        return bool(_load_state(path).get("killed", False))
    except Exception as exc:
        logger.critical("kill switch state unreadable; failing closed: %s", exc)
        return True


def check_or_raise(path: str | Path = DEFAULT_KILL_SWITCH_PATH) -> None:
    """Raise a governance error when the persisted kill switch is active."""
    try:
        state = _load_state(path)
    except Exception as exc:
        raise TrainingGovernanceError(
            "training kill switch state unreadable",
            status="KILL_SWITCH_ERROR",
            reasons=[f"kill_switch_state_unreadable:{type(exc).__name__}"],
        ) from exc

    if bool(state.get("killed", False)):
        reason = str(state.get("reason") or "manual_emergency_stop")
        raise TrainingGovernanceError(
            f"training kill switch engaged: {reason}",
            status="KILLED",
            reasons=[reason],
        )
