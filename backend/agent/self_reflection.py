from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name}_required")
    return normalized


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_jsonl(path: Path, loader: Callable[[dict[str, Any]], Any]) -> list[Any]:
    if not path.exists():
        return []
    records: list[Any] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid_jsonl:{path}:{line_number}:{exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(f"jsonl_record_must_be_mapping:{path}:{line_number}")
            records.append(loader(payload))
    return records


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "adaptive_method"


@dataclass(frozen=True)
class MethodRecord:
    method_id: str
    name: str
    attack_family: str
    failure_pattern: str
    reasoning: str
    steps: tuple[str, ...]
    invented_by: str
    created_at: str
    source_failure_count: int = 0
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "name": self.name,
            "attack_family": self.attack_family,
            "failure_pattern": self.failure_pattern,
            "reasoning": self.reasoning,
            "steps": list(self.steps),
            "invented_by": self.invented_by,
            "created_at": self.created_at,
            "source_failure_count": int(self.source_failure_count),
            "tags": list(self.tags),
            "metadata": _json_safe(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MethodRecord":
        return cls(
            method_id=_normalize_text(payload.get("method_id"), field_name="method_id"),
            name=_normalize_text(payload.get("name"), field_name="name"),
            attack_family=_normalize_text(
                payload.get("attack_family"),
                field_name="attack_family",
            ),
            failure_pattern=_normalize_text(
                payload.get("failure_pattern"),
                field_name="failure_pattern",
            ),
            reasoning=_normalize_text(payload.get("reasoning"), field_name="reasoning"),
            steps=tuple(str(item) for item in payload.get("steps", ()) if str(item).strip()),
            invented_by=_normalize_text(payload.get("invented_by"), field_name="invented_by"),
            created_at=_normalize_text(payload.get("created_at"), field_name="created_at"),
            source_failure_count=int(payload.get("source_failure_count", 0) or 0),
            tags=tuple(str(item) for item in payload.get("tags", ()) if str(item).strip()),
            metadata=dict(_json_safe(payload.get("metadata", {})) or {}),
        )


@dataclass(frozen=True)
class FailureObservation:
    observation_id: str
    attack_family: str
    failure_pattern: str
    reason: str
    count_for_pattern: int
    observed_at: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "attack_family": self.attack_family,
            "failure_pattern": self.failure_pattern,
            "reason": self.reason,
            "count_for_pattern": int(self.count_for_pattern),
            "observed_at": self.observed_at,
            "context": _json_safe(self.context),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FailureObservation":
        return cls(
            observation_id=_normalize_text(
                payload.get("observation_id"),
                field_name="observation_id",
            ),
            attack_family=_normalize_text(
                payload.get("attack_family"),
                field_name="attack_family",
            ),
            failure_pattern=_normalize_text(
                payload.get("failure_pattern"),
                field_name="failure_pattern",
            ),
            reason=str(payload.get("reason", "") or "").strip(),
            count_for_pattern=int(payload.get("count_for_pattern", 0) or 0),
            observed_at=_normalize_text(
                payload.get("observed_at"),
                field_name="observed_at",
            ),
            context=dict(_json_safe(payload.get("context", {})) or {}),
        )


@dataclass(frozen=True)
class ReflectionEvent:
    event_id: str
    event_type: str
    attack_family: str
    failure_pattern: str
    reasoning: str
    failure_count: int
    occurred_at: str
    invented_method_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "attack_family": self.attack_family,
            "failure_pattern": self.failure_pattern,
            "reasoning": self.reasoning,
            "failure_count": int(self.failure_count),
            "occurred_at": self.occurred_at,
            "invented_method_id": self.invented_method_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReflectionEvent":
        invented_method_id = str(payload.get("invented_method_id", "") or "").strip() or None
        return cls(
            event_id=_normalize_text(payload.get("event_id"), field_name="event_id"),
            event_type=_normalize_text(payload.get("event_type"), field_name="event_type"),
            attack_family=_normalize_text(
                payload.get("attack_family"),
                field_name="attack_family",
            ),
            failure_pattern=_normalize_text(
                payload.get("failure_pattern"),
                field_name="failure_pattern",
            ),
            reasoning=_normalize_text(payload.get("reasoning"), field_name="reasoning"),
            failure_count=int(payload.get("failure_count", 0) or 0),
            occurred_at=_normalize_text(payload.get("occurred_at"), field_name="occurred_at"),
            invented_method_id=invented_method_id,
        )


class MethodLibrary:
    DEFAULT_ROOT = Path("secure_data") / "self_reflection"

    def __init__(
        self,
        root: str | os.PathLike[str] = DEFAULT_ROOT,
        *,
        library_filename: str = "method_library.json",
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.library_path = self.root / library_filename
        self._methods = self._load_methods()

    def _load_methods(self) -> list[MethodRecord]:
        if not self.library_path.exists():
            return []
        try:
            payload = json.loads(self.library_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_method_library_json:{self.library_path}:{exc.msg}") from exc
        if isinstance(payload, list):
            methods_payload = payload
        elif isinstance(payload, dict):
            methods_payload = payload.get("methods", [])
        else:
            raise ValueError(f"invalid_method_library_payload:{self.library_path}")
        if not isinstance(methods_payload, list):
            raise ValueError(f"invalid_method_library_methods:{self.library_path}")
        return [MethodRecord.from_payload(item) for item in methods_payload]

    def _persist(self) -> None:
        payload = {
            "version": 1,
            "updated_at": _utc_now(),
            "methods": [method.to_payload() for method in self._methods],
        }
        _atomic_write_json(self.library_path, payload)

    @property
    def methods(self) -> tuple[MethodRecord, ...]:
        return tuple(self._methods)

    def __iter__(self):
        return iter(self._methods)

    def __len__(self) -> int:
        return len(self._methods)

    def add_method(self, method: MethodRecord) -> MethodRecord:
        if not isinstance(method, MethodRecord):
            raise TypeError("method_must_be_method_record")
        replaced = False
        updated_methods: list[MethodRecord] = []
        for existing in self._methods:
            if existing.method_id == method.method_id:
                updated_methods.append(method)
                replaced = True
            else:
                updated_methods.append(existing)
        if not replaced:
            updated_methods.append(method)
        self._methods = updated_methods
        self._persist()
        return method

    def get_method(self, method_id: str) -> MethodRecord | None:
        normalized_method_id = _normalize_text(method_id, field_name="method_id")
        for method in self._methods:
            if method.method_id == normalized_method_id:
                return method
        return None

    def list_methods(
        self,
        *,
        attack_family: str | None = None,
        invented_by: str | None = None,
    ) -> list[MethodRecord]:
        methods = list(self._methods)
        if attack_family is not None:
            normalized_attack_family = _normalize_text(
                attack_family,
                field_name="attack_family",
            ).lower()
            methods = [
                method
                for method in methods
                if method.attack_family.lower() == normalized_attack_family
            ]
        if invented_by is not None:
            normalized_invented_by = _normalize_text(
                invented_by,
                field_name="invented_by",
            ).lower()
            methods = [
                method
                for method in methods
                if method.invented_by.lower() == normalized_invented_by
            ]
        return methods

    def find_for_pattern(self, attack_family: str, failure_pattern: str) -> list[MethodRecord]:
        normalized_attack_family = _normalize_text(
            attack_family,
            field_name="attack_family",
        ).lower()
        normalized_failure_pattern = _normalize_text(
            failure_pattern,
            field_name="failure_pattern",
        ).lower()
        return [
            method
            for method in self._methods
            if method.attack_family.lower() == normalized_attack_family
            and method.failure_pattern.lower() == normalized_failure_pattern
        ]


class SelfReflectionEngine:
    DEFAULT_INVENTION_THRESHOLD = 4

    def __init__(
        self,
        method_library: MethodLibrary,
        *,
        root: str | os.PathLike[str] | None = None,
        invention_threshold: int = DEFAULT_INVENTION_THRESHOLD,
    ) -> None:
        if not isinstance(method_library, MethodLibrary):
            raise TypeError("method_library_must_be_method_library")
        self.method_library = method_library
        self.root = Path(root) if root is not None else method_library.root
        self.root.mkdir(parents=True, exist_ok=True)
        self.failure_log_path = self.root / "failure_observations.jsonl"
        self.failure_state_path = self.root / "failure_state.json"
        self.reflection_log_path = self.root / "reflection_events.jsonl"
        self.invention_threshold = int(invention_threshold)
        if self.invention_threshold < 1:
            raise ValueError("invention_threshold_must_be_positive")
        self._failure_state = self._load_failure_state()

    @staticmethod
    def build_failure_key(attack_family: str, failure_pattern: str) -> str:
        normalized_attack_family = _normalize_text(
            attack_family,
            field_name="attack_family",
        ).lower()
        normalized_failure_pattern = _normalize_text(
            failure_pattern,
            field_name="failure_pattern",
        ).lower()
        return f"{normalized_attack_family}::{normalized_failure_pattern}"

    def _load_failure_state(self) -> dict[str, dict[str, Any]]:
        if not self.failure_state_path.exists():
            return {}
        try:
            payload = json.loads(self.failure_state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_failure_state_json:{self.failure_state_path}:{exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"invalid_failure_state_payload:{self.failure_state_path}")
        raw_patterns = payload.get("patterns", {})
        if not isinstance(raw_patterns, dict):
            raise ValueError(f"invalid_failure_state_patterns:{self.failure_state_path}")
        normalized_state: dict[str, dict[str, Any]] = {}
        for key, value in raw_patterns.items():
            if not isinstance(value, dict):
                raise ValueError(f"invalid_failure_state_entry:{self.failure_state_path}:{key}")
            normalized_state[str(key)] = {
                "attack_family": _normalize_text(
                    value.get("attack_family"),
                    field_name="attack_family",
                ),
                "failure_pattern": _normalize_text(
                    value.get("failure_pattern"),
                    field_name="failure_pattern",
                ),
                "count": int(value.get("count", 0) or 0),
                "last_reason": str(value.get("last_reason", "") or "").strip(),
                "last_observed_at": str(value.get("last_observed_at", "") or "").strip(),
                "invented_method_id": str(value.get("invented_method_id", "") or "").strip() or None,
            }
        return normalized_state

    def _persist_failure_state(self) -> None:
        payload = {
            "version": 1,
            "updated_at": _utc_now(),
            "patterns": _json_safe(self._failure_state),
        }
        _atomic_write_json(self.failure_state_path, payload)

    def _build_reflection_reasoning(
        self,
        *,
        attack_family: str,
        failure_pattern: str,
        failure_count: int,
        reason: str,
    ) -> str:
        normalized_reason = str(reason or "").strip() or "no explicit failure reason provided"
        if failure_count >= self.invention_threshold:
            return (
                f"Repeated failure pattern detected for {attack_family}: '{failure_pattern}'. "
                f"Observed {failure_count} failure(s), which meets the invention threshold of "
                f"{self.invention_threshold}. Latest reason: {normalized_reason}. The loop should "
                f"invent a new method that changes structure instead of repeating the blocked path."
            )
        if failure_count > 1:
            return (
                f"Repeated failure pattern detected for {attack_family}: '{failure_pattern}'. "
                f"Observed {failure_count} failure(s) so far. Latest reason: {normalized_reason}. "
                f"Continue tracking evidence until the invention threshold of {self.invention_threshold} "
                f"is reached."
            )
        return (
            f"Initial failure observed for {attack_family}: '{failure_pattern}'. Latest reason: "
            f"{normalized_reason}. Reflection will accumulate evidence before inventing a new method."
        )

    def _build_invention_reasoning(
        self,
        *,
        attack_family: str,
        failure_pattern: str,
        failure_count: int,
        method_name: str,
    ) -> str:
        return (
            f"Invented {method_name} after {failure_count} repeated '{failure_pattern}' failures in "
            f"{attack_family}. The invented method was synthesized entirely from the observed local "
            f"failure history and does not require external tools for its core reasoning loop."
        )

    def _derive_method_steps(self, *, attack_family: str, failure_pattern: str) -> tuple[str, ...]:
        family_lower = attack_family.lower()
        pattern_lower = failure_pattern.lower()
        steps: list[str] = [
            "Capture the exact rejection signal and isolate which token, delimiter, or structure triggered the filter.",
            "Apply a minimal structural mutation instead of replaying the same blocked attempt.",
            "Record the outcome so the next reflection cycle can compare what changed and what still fails.",
        ]
        if "xss" in family_lower or "xss" in pattern_lower:
            steps.insert(
                1,
                "Prefer alternate client-side execution shapes such as attribute, event, or container variations rather than raw script-tag repetition.",
            )
            steps.insert(
                2,
                "Rotate harmless transformations such as casing, entity encoding, delimiter splitting, or context-preserving wrappers to probe naive blacklist filters.",
            )
        return tuple(steps)

    def _invent_method(
        self,
        *,
        attack_family: str,
        failure_pattern: str,
        failure_count: int,
        context: dict[str, Any],
    ) -> MethodRecord:
        stable_key = self.build_failure_key(attack_family, failure_pattern)
        stable_hash = sha1(stable_key.encode("utf-8")).hexdigest()[:12].upper()
        method_name = (
            f"{_slugify(attack_family)}_adaptive_bypass_for_{_slugify(failure_pattern)}"
        )
        return MethodRecord(
            method_id=f"SRM-{stable_hash}",
            name=method_name,
            attack_family=attack_family,
            failure_pattern=failure_pattern,
            reasoning=self._build_invention_reasoning(
                attack_family=attack_family,
                failure_pattern=failure_pattern,
                failure_count=failure_count,
                method_name=method_name,
            ),
            steps=self._derive_method_steps(
                attack_family=attack_family,
                failure_pattern=failure_pattern,
            ),
            invented_by="self_reflection",
            created_at=_utc_now(),
            source_failure_count=failure_count,
            tags=(attack_family, "self_reflection", "invented_method"),
            metadata={
                "failure_signature": stable_key,
                "invention_threshold": self.invention_threshold,
                "context": _json_safe(context),
            },
        )

    def _record_reflection_event(
        self,
        *,
        event_type: str,
        attack_family: str,
        failure_pattern: str,
        reasoning: str,
        failure_count: int,
        invented_method_id: str | None = None,
    ) -> ReflectionEvent:
        event = ReflectionEvent(
            event_id=f"RFE-{uuid4().hex[:12].upper()}",
            event_type=_normalize_text(event_type, field_name="event_type"),
            attack_family=attack_family,
            failure_pattern=failure_pattern,
            reasoning=_normalize_text(reasoning, field_name="reasoning"),
            failure_count=int(failure_count),
            occurred_at=_utc_now(),
            invented_method_id=invented_method_id,
        )
        _append_jsonl(self.reflection_log_path, event.to_payload())
        return event

    def observe_failure(
        self,
        attack_family: str,
        failure_pattern: str,
        *,
        reason: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_attack_family = _normalize_text(
            attack_family,
            field_name="attack_family",
        )
        normalized_failure_pattern = _normalize_text(
            failure_pattern,
            field_name="failure_pattern",
        )
        context_payload = dict(_json_safe(context or {}) or {})
        failure_key = self.build_failure_key(
            normalized_attack_family,
            normalized_failure_pattern,
        )
        state_entry = dict(
            self._failure_state.get(
                failure_key,
                {
                    "attack_family": normalized_attack_family,
                    "failure_pattern": normalized_failure_pattern,
                    "count": 0,
                    "last_reason": "",
                    "last_observed_at": "",
                    "invented_method_id": None,
                },
            )
        )
        failure_count = int(state_entry.get("count", 0) or 0) + 1
        observed_at = _utc_now()
        observation = FailureObservation(
            observation_id=f"OBS-{uuid4().hex[:12].upper()}",
            attack_family=normalized_attack_family,
            failure_pattern=normalized_failure_pattern,
            reason=str(reason or "").strip(),
            count_for_pattern=failure_count,
            observed_at=observed_at,
            context=context_payload,
        )
        _append_jsonl(self.failure_log_path, observation.to_payload())

        state_entry.update(
            {
                "attack_family": normalized_attack_family,
                "failure_pattern": normalized_failure_pattern,
                "count": failure_count,
                "last_reason": observation.reason,
                "last_observed_at": observed_at,
                "invented_method_id": state_entry.get("invented_method_id"),
            }
        )

        reflection_event = self._record_reflection_event(
            event_type="reflection",
            attack_family=normalized_attack_family,
            failure_pattern=normalized_failure_pattern,
            reasoning=self._build_reflection_reasoning(
                attack_family=normalized_attack_family,
                failure_pattern=normalized_failure_pattern,
                failure_count=failure_count,
                reason=observation.reason,
            ),
            failure_count=failure_count,
        )

        invented_method: MethodRecord | None = None
        invention_event: ReflectionEvent | None = None
        if failure_count >= self.invention_threshold and not state_entry.get("invented_method_id"):
            invented_method = self._invent_method(
                attack_family=normalized_attack_family,
                failure_pattern=normalized_failure_pattern,
                failure_count=failure_count,
                context=context_payload,
            )
            self.method_library.add_method(invented_method)
            state_entry["invented_method_id"] = invented_method.method_id
            invention_event = self._record_reflection_event(
                event_type="method_invented",
                attack_family=normalized_attack_family,
                failure_pattern=normalized_failure_pattern,
                reasoning=invented_method.reasoning,
                failure_count=failure_count,
                invented_method_id=invented_method.method_id,
            )

        self._failure_state[failure_key] = state_entry
        self._persist_failure_state()
        return {
            "observation": observation,
            "reflection_event": reflection_event,
            "invention_event": invention_event,
            "invented_method": invented_method,
            "failure_count": failure_count,
        }

    record_failure = observe_failure
    process_failure = observe_failure
    reflect_on_failure = observe_failure

    def get_failure_summary(self) -> dict[str, dict[str, Any]]:
        return dict(_json_safe(self._failure_state))

    def list_reflection_events(self) -> list[ReflectionEvent]:
        return _read_jsonl(self.reflection_log_path, ReflectionEvent.from_payload)

    def list_failure_observations(self) -> list[FailureObservation]:
        return _read_jsonl(self.failure_log_path, FailureObservation.from_payload)


__all__ = [
    "FailureObservation",
    "MethodLibrary",
    "MethodRecord",
    "ReflectionEvent",
    "SelfReflectionEngine",
]
