"""
Persistent single-objective focus state for the local assistant.

This keeps the assistant anchored to one active objective at a time so it
does not drift into unrelated work until the current objective is completed.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FOCUS_STATE_PATH = PROJECT_ROOT / "data" / "assistant_focus_state.json"
MAX_STEP_HISTORY = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ObjectiveDecision:
    allowed: bool
    reason: str
    active_objective: Optional[dict]


class TaskFocusManager:
    """Single-active-objective state manager with append-only progress history."""

    def __init__(self, state_path: str | os.PathLike[str] | None = None):
        self._path = str(state_path or FOCUS_STATE_PATH)

    def _default_state(self) -> dict:
        return {
            "active_objective_id": None,
            "objectives": [],
            "last_updated": _utc_now(),
        }

    def load(self) -> dict:
        if not os.path.exists(self._path):
            return self._default_state()
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return self._default_state()
            data.setdefault("active_objective_id", None)
            data.setdefault("objectives", [])
            data.setdefault("last_updated", _utc_now())
            return data
        except Exception:
            return self._default_state()

    def save(self, state: dict) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        state["last_updated"] = _utc_now()
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self._path)

    def _find_objective(self, state: dict, objective_id: str) -> Optional[dict]:
        for objective in state.get("objectives", []):
            if objective.get("objective_id") == objective_id:
                return objective
        return None

    def get_active_objective(self) -> Optional[dict]:
        state = self.load()
        objective_id = state.get("active_objective_id")
        if not objective_id:
            return None
        return self._find_objective(state, objective_id)

    def status_snapshot(self) -> dict:
        state = self.load()
        active = self.get_active_objective()
        completed = [
            objective
            for objective in state.get("objectives", [])
            if objective.get("status") == "COMPLETED"
        ]
        return {
            "has_active_objective": active is not None,
            "active_objective": active,
            "completed_count": len(completed),
            "last_completed": completed[-1] if completed else None,
            "last_updated": state.get("last_updated"),
        }

    def start_objective(
        self,
        *,
        title: str,
        requested_by: str,
        summary: str = "",
        force_switch: bool = False,
    ) -> dict:
        clean_title = title.strip()
        if not clean_title:
            return {
                "status": "error",
                "message": "OBJECTIVE_TITLE_REQUIRED",
            }

        state = self.load()
        active = self._find_objective(state, state.get("active_objective_id"))
        if active and active.get("status") == "ACTIVE":
            if active.get("title", "").strip().lower() == clean_title.lower():
                return {
                    "status": "ok",
                    "message": "OBJECTIVE_ALREADY_ACTIVE",
                    "objective": active,
                }
            if not force_switch:
                return {
                    "status": "blocked",
                    "message": (
                        f"ACTIVE_OBJECTIVE_IN_PROGRESS: '{active.get('title')}'. "
                        "Complete it or force a switch."
                    ),
                    "objective": active,
                }
            active["status"] = "ABANDONED"
            active["completed_at"] = None
            active["completion_summary"] = "Switched to a new objective"
            active["updated_at"] = _utc_now()

        objective = {
            "objective_id": f"OBJ-{uuid.uuid4().hex[:16].upper()}",
            "title": clean_title,
            "requested_by": requested_by.strip() or "unknown",
            "summary": summary.strip() or clean_title,
            "status": "ACTIVE",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "completed_at": None,
            "completion_summary": None,
            "steps": [],
        }
        state.setdefault("objectives", []).append(objective)
        state["active_objective_id"] = objective["objective_id"]
        self.save(state)
        return {
            "status": "ok",
            "message": "OBJECTIVE_STARTED",
            "objective": objective,
        }

    def complete_active_objective(self, summary: str = "") -> dict:
        state = self.load()
        active = self._find_objective(state, state.get("active_objective_id"))
        if not active:
            return {
                "status": "blocked",
                "message": "NO_ACTIVE_OBJECTIVE",
            }
        active["status"] = "COMPLETED"
        active["updated_at"] = _utc_now()
        active["completed_at"] = _utc_now()
        active["completion_summary"] = summary.strip() or "Objective marked complete"
        state["active_objective_id"] = None
        self.save(state)
        return {
            "status": "ok",
            "message": "OBJECTIVE_COMPLETED",
            "objective": active,
        }

    def append_step(
        self,
        *,
        kind: str,
        summary: str,
        grounded: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> dict:
        state = self.load()
        active = self._find_objective(state, state.get("active_objective_id"))
        if not active:
            return {
                "status": "ignored",
                "message": "NO_ACTIVE_OBJECTIVE",
            }
        step = {
            "step_id": f"STP-{uuid.uuid4().hex[:12].upper()}",
            "timestamp": _utc_now(),
            "kind": kind,
            "summary": summary[:1000],
            "grounded": bool(grounded),
            "metadata": metadata or {},
        }
        active.setdefault("steps", []).append(step)
        active["steps"] = active["steps"][-MAX_STEP_HISTORY:]
        active["updated_at"] = _utc_now()
        self.save(state)
        return {
            "status": "ok",
            "message": "STEP_RECORDED",
            "objective": active,
            "step": step,
        }

    def evaluate_new_objective(self, title: str) -> ObjectiveDecision:
        active = self.get_active_objective()
        if not active:
            return ObjectiveDecision(True, "NO_ACTIVE_OBJECTIVE", None)
        if active.get("status") != "ACTIVE":
            return ObjectiveDecision(True, "ACTIVE_OBJECTIVE_NOT_RUNNING", active)
        if active.get("title", "").strip().lower() == title.strip().lower():
            return ObjectiveDecision(True, "SAME_OBJECTIVE", active)
        return ObjectiveDecision(
            False,
            (
                f"ACTIVE_OBJECTIVE_IN_PROGRESS: '{active.get('title')}'. "
                "Complete it before starting the next one."
            ),
            active,
        )
