"""
Self-reflection loop for vulnerability-method evolution.

This module now supports both the older runtime-oriented API and the newer
Phase-19 test-facing persistence/reporting API.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ygb.self_reflection")

FAILURE_THRESHOLD = 3
REFLECTION_INTERVAL = 300
DEFAULT_LIBRARY_ROOT = Path("data")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MethodRecord:
    """A persisted vulnerability-detection method record."""

    method_id: str
    name: str
    description: str
    field: str
    success_count: int = 0
    failure_count: int = 0
    invented_at: str = ""
    invented_by: str = "human"
    last_used: str = ""
    effectiveness_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    attack_family: str = ""
    failure_pattern: str = ""
    source_failure_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MethodRecord":
        return cls(
            method_id=str(payload.get("method_id", "")),
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            field=str(payload.get("field", "")),
            success_count=int(payload.get("success_count", 0) or 0),
            failure_count=int(payload.get("failure_count", 0) or 0),
            invented_at=str(payload.get("invented_at", "")),
            invented_by=str(payload.get("invented_by", "human")),
            last_used=str(payload.get("last_used", "")),
            effectiveness_score=float(payload.get("effectiveness_score", 0.0) or 0.0),
            metadata=dict(payload.get("metadata", {}) or {}),
            attack_family=str(payload.get("attack_family", "") or ""),
            failure_pattern=str(payload.get("failure_pattern", "") or ""),
            source_failure_count=int(payload.get("source_failure_count", 0) or 0),
        )


VulnMethod = MethodRecord


@dataclass(frozen=True)
class FailureObservation:
    method_id: str
    attack_family: str
    failure_pattern: str
    reason: str
    context: dict[str, Any]
    timestamp: str
    count_for_pattern: int


@dataclass(frozen=True)
class ReflectionEvent:
    event_id: str
    event_type: str
    trigger: str
    field: str
    failed_method: str
    failure_patterns: tuple[str, ...]
    new_method_proposed: Optional[str]
    invented_method_id: str = ""
    reasoning: str = ""
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class MethodLibrary:
    """Persistent library of seed and self-invented methods."""

    SEED_METHODS = (
        MethodRecord(
            "xss_basic",
            "Basic XSS Probe",
            "Inject basic reflected/stored XSS payload variations.",
            "xss",
            attack_family="xss_basic",
        ),
        MethodRecord(
            "sqli_error",
            "SQLi Error-Based",
            "Inject quote-based payloads and inspect database errors.",
            "sqli",
            attack_family="sqli_error",
        ),
        MethodRecord(
            "ssrf_loopback",
            "SSRF Loopback Probe",
            "Test URL parameters with localhost and RFC1918 targets.",
            "ssrf",
            attack_family="ssrf_loopback",
        ),
        MethodRecord(
            "idor_seq",
            "IDOR Sequential Probe",
            "Test predictable identifier increments/decrements.",
            "idor",
            attack_family="idor_seq",
        ),
        MethodRecord(
            "auth_jwt",
            "JWT Weakness Detection",
            "Test algorithm confusion and unsafe token handling.",
            "auth",
            attack_family="auth_jwt",
        ),
        MethodRecord(
            "rce_cmd",
            "Command Injection Probe",
            "Test shell metacharacter execution paths.",
            "rce",
            attack_family="rce_cmd",
        ),
        MethodRecord(
            "path_traversal",
            "Path Traversal Probe",
            "Test traversal payloads and path normalization gaps.",
            "path_traversal",
            attack_family="path_traversal",
        ),
        MethodRecord(
            "xxe_basic",
            "XXE Basic Probe",
            "Test XML entity expansion and external entity handling.",
            "xxe",
            attack_family="xxe_basic",
        ),
    )

    def __init__(
        self,
        root: Path | str | None = None,
        library_path: Path | str | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else DEFAULT_LIBRARY_ROOT
        self._path = Path(library_path) if library_path is not None else self.root / "method_library.json"
        self._methods: dict[str, MethodRecord] = {
            record.method_id: MethodRecord.from_dict(record.to_dict())
            for record in self.SEED_METHODS
        }
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to load method library: %s", exc)
            return

        if isinstance(payload, dict) and "methods" in payload:
            entries = payload.get("methods", [])
        elif isinstance(payload, dict):
            entries = list(payload.values())
        elif isinstance(payload, list):
            entries = payload
        else:
            entries = []

        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            record = MethodRecord.from_dict(raw_entry)
            self._methods[record.method_id] = record

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        invented = [
            method.to_dict()
            for method in self.list_methods(invented_by="self_reflection")
        ]
        self._path.write_text(
            json.dumps({"methods": invented}, indent=2),
            encoding="utf-8",
        )

    def record_outcome(self, method_id: str, success: bool) -> None:
        method = self._methods.get(method_id)
        if method is None:
            logger.warning("Unknown method: %s", method_id)
            return
        if success:
            method.success_count += 1
        else:
            method.failure_count += 1
        method.last_used = _utcnow_iso()
        total = method.success_count + method.failure_count
        method.effectiveness_score = method.success_count / total if total else 0.0
        if method.invented_by == "self_reflection":
            self._save()

    def add_invented_method(self, method: MethodRecord) -> None:
        self._methods[method.method_id] = method
        self._save()
        logger.info("New method invented: %s for field %s", method.name, method.field)

    def get_method(self, method_id: str) -> Optional[MethodRecord]:
        return self._methods.get(method_id)

    def get_all_methods(self) -> list[MethodRecord]:
        return self.list_methods()

    def list_methods(self, invented_by: str | None = None) -> list[MethodRecord]:
        methods = list(self._methods.values())
        if invented_by is not None:
            methods = [method for method in methods if method.invented_by == invented_by]
        return sorted(
            methods,
            key=lambda method: (
                method.invented_at or "",
                method.method_id,
            ),
        )

    def get_best_methods(self, field: str, n: int = 5) -> list[MethodRecord]:
        field_methods = [method for method in self._methods.values() if method.field == field]
        return sorted(
            field_methods,
            key=lambda method: (method.effectiveness_score, method.success_count, -method.failure_count),
            reverse=True,
        )[:n]

    def get_failing_methods(
        self,
        field: str,
        *,
        threshold: int = FAILURE_THRESHOLD,
    ) -> list[MethodRecord]:
        return [
            method
            for method in self._methods.values()
            if (method.field == field or method.method_id == field or method.attack_family == field)
            and method.failure_count >= threshold
            and method.failure_count >= max(1, method.success_count + 1)
        ]


class SelfReflectionEngine:
    """Monitor repeated failures and invent alternative methods."""

    def __init__(
        self,
        library: MethodLibrary | None = None,
        reflection_log_path: Path | str | None = None,
        *,
        method_library: MethodLibrary | None = None,
        invention_threshold: int = FAILURE_THRESHOLD,
    ) -> None:
        self._library = method_library or library or MethodLibrary()
        self.invention_threshold = max(1, int(invention_threshold))
        self._log_path = Path(reflection_log_path) if reflection_log_path is not None else self._library.root / "reflection_log.jsonl"
        self._failure_summary: dict[str, dict[str, Any]] = {}
        self._failure_observations: list[FailureObservation] = []
        self._reflection_events: list[ReflectionEvent] = []
        self._last_reflection = 0.0

    def build_failure_key(self, attack_family: str, failure_pattern: str) -> str:
        return f"{str(attack_family).strip()}::{str(failure_pattern).strip()}"

    def get_failure_summary(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._failure_summary.items()}

    def list_failure_observations(self) -> list[FailureObservation]:
        return list(self._failure_observations)

    def list_reflection_events(self) -> list[ReflectionEvent]:
        return list(self._reflection_events)

    def observe_failure(
        self,
        method_id: str,
        field_or_pattern: str,
        error_pattern: str | None = None,
        *,
        reason: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        method = self._library.get_method(method_id)
        if error_pattern is None:
            field = method.field if method is not None else str(method_id)
            failure_pattern = str(field_or_pattern)
        else:
            field = str(field_or_pattern)
            failure_pattern = str(error_pattern)

        self._library.record_outcome(method_id, success=False)
        failure_key = self.build_failure_key(method_id, failure_pattern)
        summary = self._failure_summary.setdefault(
            failure_key,
            {
                "count": 0,
                "attack_family": method_id,
                "field": field,
                "failure_pattern": failure_pattern,
                "invented_method_id": "",
            },
        )
        summary["count"] += 1
        summary["last_reason"] = str(reason or "")
        summary["last_context"] = dict(context or {})
        summary["last_observed_at"] = _utcnow_iso()

        observation = FailureObservation(
            method_id=method_id,
            attack_family=method_id,
            failure_pattern=failure_pattern,
            reason=str(reason or ""),
            context=dict(context or {}),
            timestamp=summary["last_observed_at"],
            count_for_pattern=int(summary["count"]),
        )
        self._failure_observations.append(observation)

        invented_method: MethodRecord | None = None
        if summary["count"] >= self.invention_threshold:
            invented_method_id = str(summary.get("invented_method_id", "") or "")
            invented_method = self._library.get_method(invented_method_id) if invented_method_id else None
            if invented_method is None:
                invented_method = self._invent_method_rule_based(
                    attack_family=method_id,
                    field=field,
                    failure_pattern=failure_pattern,
                    failure_count=int(summary["count"]),
                )
                if invented_method is not None:
                    self._library.add_invented_method(invented_method)
                    summary["invented_method_id"] = invented_method.method_id
                    self._append_reflection_event(
                        ReflectionEvent(
                            event_id=uuid.uuid4().hex[:8],
                            event_type="method_invented",
                            trigger="failure_threshold",
                            field=field,
                            failed_method=method_id,
                            failure_patterns=(failure_pattern,),
                            new_method_proposed=invented_method.name,
                            invented_method_id=invented_method.method_id,
                            reasoning=self._generate_reasoning(field, method_id, failure_pattern, int(summary["count"])),
                            timestamp=_utcnow_iso(),
                            metadata={"failure_key": failure_key},
                        )
                    )

            self._append_reflection_event(
                ReflectionEvent(
                    event_id=uuid.uuid4().hex[:8],
                    event_type="reflection",
                    trigger="failure_threshold",
                    field=field,
                    failed_method=method_id,
                    failure_patterns=(failure_pattern,),
                    new_method_proposed=invented_method.name if invented_method else None,
                    invented_method_id=invented_method.method_id if invented_method else str(summary.get("invented_method_id", "") or ""),
                    reasoning=self._generate_reasoning(field, method_id, failure_pattern, int(summary["count"])),
                    timestamp=_utcnow_iso(),
                    metadata={"failure_key": failure_key},
                )
            )

        return {
            "failure_key": failure_key,
            "failure_count": int(summary["count"]),
            "invented_method": invented_method,
        }

    def observe_success(self, method_id: str, field: str | None = None) -> None:
        self._library.record_outcome(method_id, success=True)
        logger.debug("Success recorded: method=%s field=%s", method_id, field or "")

    def idle_reflection(self, fields: list[str]) -> None:
        now = time.time()
        if now - self._last_reflection < REFLECTION_INTERVAL:
            return
        self._last_reflection = now
        for field in fields:
            failing_methods = self._library.get_failing_methods(
                field,
                threshold=self.invention_threshold,
            )
            if not failing_methods:
                continue
            self._append_reflection_event(
                ReflectionEvent(
                    event_id=uuid.uuid4().hex[:8],
                    event_type="reflection",
                    trigger="idle",
                    field=field,
                    failed_method=",".join(method.method_id for method in failing_methods),
                    failure_patterns=tuple(method.method_id for method in failing_methods),
                    new_method_proposed=None,
                    reasoning=f"Idle reflection noticed repeated failures in field '{field}'.",
                    timestamp=_utcnow_iso(),
                )
            )

    def get_reflection_stats(self) -> dict[str, Any]:
        by_field = Counter(event.field for event in self._reflection_events)
        by_trigger = Counter(event.trigger for event in self._reflection_events)
        invented = sum(1 for event in self._reflection_events if event.event_type == "method_invented")
        return {
            "total_events": len(self._reflection_events),
            "methods_invented": invented,
            "by_field": dict(by_field),
            "by_trigger": dict(by_trigger),
        }

    def _append_reflection_event(self, event: ReflectionEvent) -> None:
        self._reflection_events.append(event)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._event_to_dict(event), sort_keys=True))
            handle.write("\n")

    def _invent_method_rule_based(
        self,
        *,
        attack_family: str,
        field: str,
        failure_pattern: str,
        failure_count: int,
    ) -> MethodRecord:
        pattern_text = failure_pattern.lower()
        escalation_map = {
            "xss": [
                ("filtered", "xss_encode", "XSS with Encoding Bypass", "Try HTML entity, URL, and unicode encoding bypasses."),
                ("csp", "xss_csp_bypass", "CSP Bypass XSS", "Use DOM sinks, JSONP callbacks, or CSP bypass vectors."),
                ("sanitized", "xss_dom_clobbering", "DOM Clobbering XSS", "Abuse DOM clobbering to bypass sanitization logic."),
            ],
            "sqli": [
                ("filtered", "sqli_blind_time", "Blind Time-Based SQLi", "Use timing side channels and binary-search extraction."),
                ("waf", "sqli_chunked", "WAF Evasion SQLi", "Use comments, casing, and encoding evasions."),
                ("error", "sqli_union", "Union-Based SQLi", "Use UNION-based extraction paths."),
            ],
            "ssrf": [
                ("blocked", "ssrf_dns_rebind", "DNS Rebinding SSRF", "Use DNS rebinding or chained resolution."),
                ("redirect", "ssrf_redirect_chain", "SSRF via Redirect Chain", "Chain 30x responses into internal targets."),
            ],
            "rce": [
                ("not found", "rce_env", "RCE via Environment Variables", "Manipulate environment-dependent execution paths."),
                ("filtered", "rce_template", "Template Injection RCE", "Probe SSTI-style execution gadgets."),
            ],
            "auth": [
                ("token", "auth_session_fixation", "Session Fixation", "Probe sticky or attacker-controlled session reuse."),
                ("bypass", "auth_logic_flaw", "Authentication Logic Flaw", "Probe branch-order and state-transition flaws."),
            ],
        }

        base_method_id = f"{field}_adaptive"
        name = f"Adaptive {field.upper()} Variant"
        description = "Apply a generalized adaptive variant derived from repeated failure analysis."
        for trigger_text, candidate_id, candidate_name, candidate_description in escalation_map.get(field, []):
            if trigger_text in pattern_text:
                base_method_id = candidate_id
                name = candidate_name
                description = candidate_description
                break

        return MethodRecord(
            method_id=f"{base_method_id}_{uuid.uuid4().hex[:4]}",
            name=name,
            description=description,
            field=field,
            invented_at=_utcnow_iso(),
            invented_by="self_reflection",
            attack_family=attack_family,
            failure_pattern=failure_pattern,
            source_failure_count=int(failure_count),
            metadata={
                "attack_family": attack_family,
                "failure_pattern": failure_pattern,
                "source_failure_count": int(failure_count),
            },
        )

    def _generate_reasoning(
        self,
        field: str,
        method_id: str,
        failure_pattern: str,
        failure_count: int,
    ) -> str:
        return (
            f"Field '{field}' observed repeated failures for '{method_id}' with pattern "
            f"'{failure_pattern}' across {failure_count} attempts. "
            "Hypothesis: current signatures are blocked or normalized. "
            "Invent a higher-variance method that changes payload structure rather than retrying unchanged probes."
        )

    def _event_to_dict(self, event: ReflectionEvent) -> dict[str, Any]:
        payload = asdict(event)
        payload["failure_patterns"] = list(event.failure_patterns)
        return payload


if __name__ == "__main__":
    print("Self-Reflection Engine")
    print("=" * 50)
    print("\nUsage:")
    print("  from backend.agent.self_reflection import MethodLibrary, SelfReflectionEngine")
    print("  library = MethodLibrary()")
    print("  engine = SelfReflectionEngine(library)")
    print("  engine.observe_failure('xss_basic', 'payload filtered')")
