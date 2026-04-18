"""Self-reflection loop for method failure analysis and invention.

Supports both the legacy Phase 5 orchestration API and the newer repository
tests that expect explicit root-based persistence, failure summaries, and
reflection event inspection.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field as dataclass_field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ygb.self_reflection")

FAILURE_THRESHOLD = 3
IDLE_THRESHOLD = 300
REFLECTION_INTERVAL = 300

FIELD_ALIASES: dict[str, str] = {
    "api_broken_auth": "auth",
    "auth_bypass": "auth",
    "web_auth_bypass": "auth",
    "web_csrf": "csrf",
    "web_idor": "idor",
    "web_sqli": "sqli",
    "web_ssrf": "ssrf",
    "web_xss": "xss",
}

FIELD_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "api_testing": (
        "graphql_abuse",
        "rest_attacks",
        "idor",
        "auth",
        "sqli",
        "ssrf",
        "csrf",
    ),
    "web_vulns": (
        "xss",
        "sqli",
        "ssrf",
        "idor",
        "auth",
        "csrf",
        "xxe",
        "rce",
        "file_upload",
        "deserialization",
    ),
}

ESCALATION_RULES: dict[str, list[tuple[str, str, str, str]]] = {
    "auth": [
        (
            "jwt validated",
            "auth_jwt_kid",
            "JWT Key ID Injection",
            "Test JWT kid parameter for path traversal or SQL injection",
        ),
        (
            "session strong",
            "auth_timing",
            "Timing Attack on Auth",
            "Use timing differences to enumerate valid usernames",
        ),
        (
            "mfa enforced",
            "auth_device_flow",
            "Device Flow Auth Abuse",
            "Target alternate OAuth and device-code paths that bypass interactive MFA",
        ),
    ],
    "csrf": [
        (
            "token required",
            "csrf_login",
            "Login CSRF",
            "Target login, OAuth linking, and state-changing endpoints that still accept ambient credentials",
        ),
        (
            "same-site enforced",
            "csrf_client_side",
            "Client-Side CSRF",
            "Use client-side request forgery via trusted JavaScript gadgets and reflected state",
        ),
        (
            "origin checked",
            "csrf_content_type",
            "Content-Type Confusion CSRF",
            "Bypass origin checks with simple requests, method override, or content-type downgrades",
        ),
    ],
    "deserialization": [
        (
            "gadget unavailable",
            "deser_alt_gadget",
            "Alternate Gadget Chain Discovery",
            "Probe alternate gadget chains, library versions, and secondary sinks for deserialization abuse",
        ),
        (
            "pickle blocked",
            "deser_yaml_polyglot",
            "YAML Polyglot Deserialization",
            "Swap pickle payloads for YAML, XMLDecoder, or polyglot object formats",
        ),
        (
            "java serialization filtered",
            "deser_jndi",
            "JNDI-Assisted Deserialization",
            "Pivot from blocked serialized blobs to JNDI lookups, gadget autoloading, or alternate marshallers",
        ),
    ],
    "file_upload": [
        (
            "extension blocked",
            "upload_polyglot",
            "Polyglot File Upload",
            "Use image/script polyglots, parser differentials, and double-extension payloads",
        ),
        (
            "mime checked",
            "upload_magic_bypass",
            "Magic-Byte Upload Bypass",
            "Match expected magic bytes while preserving a secondary executable parser path",
        ),
        (
            "storage isolated",
            "upload_processing_chain",
            "Processing-Chain Upload Abuse",
            "Target downstream image, archive, and antivirus processing for secondary execution",
        ),
    ],
    "graphql_abuse": [
        (
            "introspection disabled",
            "graphql_suggestion_oracle",
            "GraphQL Suggestion Oracle",
            "Use field suggestion leakage, error oracles, and persisted query diffs to map the schema",
        ),
        (
            "depth limited",
            "graphql_batching",
            "GraphQL Query Batching",
            "Chain aliases, batching, and fragments to bypass depth and rate controls",
        ),
        (
            "auth enforced",
            "graphql_idor",
            "GraphQL Object Authorization Bypass",
            "Probe node, edge, and nested resolver authorization inconsistencies",
        ),
    ],
    "idor": [
        (
            "sequential blocked",
            "idor_uuid",
            "UUID IDOR",
            "Test UUID/GUID predictability or enumeration",
        ),
        (
            "authz check present",
            "idor_race",
            "Race Condition IDOR",
            "Use concurrent requests to bypass authorization checks",
        ),
        (
            "object scoped",
            "idor_indirect_ref",
            "Indirect Reference IDOR",
            "Pivot through exports, shares, logs, and secondary object references that leak cross-tenant identifiers",
        ),
    ],
    "privilege_escalation": [
        (
            "role check present",
            "privesc_confused_deputy",
            "Confused Deputy Privilege Escalation",
            "Target helper services and cross-role workflows that execute with elevated authority",
        ),
        (
            "sudo blocked",
            "privesc_service_misconfig",
            "Service Misconfiguration Privilege Escalation",
            "Pivot to writable services, scheduled tasks, and install paths that grant elevated execution",
        ),
        (
            "container isolated",
            "privesc_escape_surface",
            "Container Escape Surface Mapping",
            "Probe kernel interfaces, mounted sockets, and runtime escapes instead of direct sudo paths",
        ),
    ],
    "race_condition": [
        (
            "duplicate blocked",
            "race_multi_endpoint",
            "Multi-Endpoint Race",
            "Race logically-linked endpoints that share state but enforce checks independently",
        ),
        (
            "locking enabled",
            "race_cross_region",
            "Cross-Region Race",
            "Exploit replication lag, cache delay, or asynchronous workers rather than local locks",
        ),
        (
            "idempotency present",
            "race_state_confusion",
            "State Confusion Race",
            "Target partial state transitions and asynchronous confirmation windows",
        ),
    ],
    "rce": [
        (
            "command not found",
            "rce_env",
            "RCE via Environment Variables",
            "Manipulate PATH or LD_PRELOAD for execution",
        ),
        (
            "filtered",
            "rce_template",
            "Template Injection RCE",
            "Test SSTI payloads for server-side template engines",
        ),
        (
            "shell blocked",
            "rce_deserialization",
            "Deserialization RCE",
            "Test unsafe deserialization in pickle, yaml, java",
        ),
    ],
    "rest_attacks": [
        (
            "verb blocked",
            "rest_method_override",
            "REST Method Override Abuse",
            "Use method override headers, proxy rewrites, and alternate verbs to reach blocked handlers",
        ),
        (
            "schema validated",
            "rest_mass_assignment",
            "REST Mass Assignment",
            "Probe hidden fields, sparse updates, and partial object merges for unauthorized property control",
        ),
        (
            "auth enforced",
            "rest_bola",
            "REST BOLA Pivot",
            "Target object-level authorization mismatches across list, detail, and export endpoints",
        ),
    ],
    "sqli": [
        (
            "filtered",
            "sqli_blind_time",
            "Blind Time-Based SQLi",
            "Use SLEEP() or pg_sleep() with binary search on data",
        ),
        (
            "waf detected",
            "sqli_chunked",
            "WAF Evasion SQLi",
            "Use comment splitting, case variation, hex encoding",
        ),
        (
            "error suppressed",
            "sqli_boolean",
            "Boolean-Based Blind SQLi",
            "Use conditional responses to extract data bit by bit",
        ),
    ],
    "ssrf": [
        (
            "blocked",
            "ssrf_dns_rebind",
            "DNS Rebinding SSRF",
            "Use DNS rebinding or CNAME chains to bypass IP filters",
        ),
        (
            "redirect followed",
            "ssrf_redirect_chain",
            "SSRF via Redirect Chain",
            "Use HTTP 301/302 to internal targets",
        ),
        (
            "localhost blocked",
            "ssrf_ipv6",
            "IPv6 SSRF",
            "Use IPv6 localhost variants like ::1 or IPv6-mapped IPv4",
        ),
    ],
    "subdomain_takeover": [
        (
            "cname validated",
            "subdomain_ns_drift",
            "Dangling NS Takeover",
            "Target dangling NS delegations and partially-retired zones instead of direct CNAMEs",
        ),
        (
            "dns active",
            "subdomain_service_rebind",
            "Service Rebind Takeover",
            "Probe third-party service unclaim flows, zone transfers, and stale SaaS bindings",
        ),
        (
            "cdn configured",
            "subdomain_cache_poison",
            "CDN Cache-Poison Pivot",
            "Abuse CDN host routing and cache poisoning to recover control over delegated origins",
        ),
    ],
    "xss": [
        (
            "basic payload filtered",
            "xss_encode",
            "XSS with encoding bypass",
            "Try HTML entity, URL, unicode encodings of XSS payload",
        ),
        (
            "csp present",
            "xss_csp_bypass",
            "CSP Bypass XSS",
            "Use CSP nonce prediction, DOM-based sinks, or JSONP callbacks",
        ),
        (
            "waf detected",
            "xss_polyglot",
            "Polyglot XSS",
            "Use polyglot payloads that work in multiple contexts",
        ),
    ],
    "xxe": [
        (
            "doctype blocked",
            "xxe_xinclude",
            "XInclude XXE",
            "Shift from DOCTYPE entities to XInclude, schema imports, and parser-side includes",
        ),
        (
            "external entity blocked",
            "xxe_oob",
            "Out-of-Band XXE",
            "Use external DTD retrieval and blind OOB callbacks to exfiltrate parser-controlled content",
        ),
        (
            "parser hardened",
            "xxe_svg",
            "SVG/Office XXE",
            "Target secondary XML parsers in SVG, DOCX, XLSX, or SOAP processing flows",
        ),
    ],
}


@dataclass
class VulnMethod:
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
    attack_family: str = ""
    failure_pattern: str = ""
    source_failure_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailureObservation:
    method_id: str
    attack_family: str
    field: str
    failure_pattern: str
    reason: str
    timestamp: str
    count_for_pattern: int = 0
    context: Dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionEvent:
    event_id: str
    event_type: str
    trigger: str
    field: str
    failed_method: str
    failure_patterns: List[str]
    new_method_proposed: Optional[str]
    reasoning: str
    timestamp: str
    invented_method_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MethodLibrary:
    """Persistent library of known and self-invented methods."""

    SEED_METHODS = [
        VulnMethod(
            "xss_basic",
            "Basic XSS Probe",
            "Inject <script>alert(1)</script> variations",
            "xss",
            invented_by="human",
        ),
        VulnMethod(
            "sqli_error",
            "SQLi Error-Based",
            "Inject single quote and observe error responses",
            "sqli",
            invented_by="human",
        ),
        VulnMethod(
            "ssrf_loopback",
            "SSRF Loopback Probe",
            "Test URL parameters with http://127.0.0.1 payloads",
            "ssrf",
            invented_by="human",
        ),
        VulnMethod(
            "idor_seq",
            "IDOR Sequential Probe",
            "Test ID parameters by incrementing/decrementing values",
            "idor",
            invented_by="human",
        ),
        VulnMethod(
            "auth_jwt",
            "JWT Weakness Detection",
            "Test JWT algorithm confusion and none algorithm",
            "auth",
            invented_by="human",
        ),
        VulnMethod(
            "rce_cmd",
            "Command Injection",
            "Test command injection via shell metacharacters",
            "rce",
            invented_by="human",
        ),
        VulnMethod(
            "xxe_basic",
            "XXE Basic",
            "Test XML external entity injection",
            "xxe",
            invented_by="human",
        ),
        VulnMethod(
            "csrf_basic",
            "CSRF Token Check",
            "Test for missing CSRF tokens",
            "csrf",
            invented_by="human",
        ),
    ]

    def __init__(
        self,
        library_path: Path | str | None = None,
        *,
        root: Path | str | None = None,
    ) -> None:
        if root is not None:
            self.root = Path(root)
            self._path = self.root / "method_library.json"
        elif library_path is not None:
            candidate = Path(library_path)
            if candidate.suffix:
                self.root = candidate.parent
                self._path = candidate
            else:
                self.root = candidate
                self._path = self.root / "method_library.json"
        else:
            self.root = Path("data")
            self._path = self.root / "method_library.json"
        self._methods: Dict[str, VulnMethod] = {}
        self._load()

    def _deserialize_methods(self, payload: Any) -> Dict[str, VulnMethod]:
        methods: Dict[str, VulnMethod] = {}
        if isinstance(payload, dict) and isinstance(payload.get("methods"), list):
            items = payload["methods"]
        elif isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = list(payload.values())
        else:
            items = []
        for item in items:
            if not isinstance(item, dict) or not item.get("method_id"):
                continue
            method = VulnMethod(**item)
            methods[method.method_id] = method
        return methods

    def _load(self) -> None:
        if self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                self._methods = self._deserialize_methods(payload)
            except Exception as exc:
                logger.warning("Failed to load method library: %s", exc)
                self._methods = {}

        if not self._methods:
            for method in self.SEED_METHODS:
                self._methods[method.method_id] = VulnMethod(**method.to_dict())
            self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        methods = sorted(
            self._methods.values(),
            key=lambda item: (0 if item.invented_by == "self_reflection" else 1, item.method_id),
        )
        payload = {
            "methods": [method.to_dict() for method in methods],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_all_methods(self) -> List[VulnMethod]:
        return list(self._methods.values())

    def list_methods(
        self,
        *,
        invented_by: str | None = None,
        field: str | None = None,
    ) -> List[VulnMethod]:
        methods = self.get_all_methods()
        if invented_by is not None:
            methods = [method for method in methods if method.invented_by == invented_by]
        if field is not None:
            methods = [method for method in methods if method.field == field]
        return sorted(methods, key=lambda method: method.method_id)

    def get_method(self, method_id: str) -> Optional[VulnMethod]:
        return self._methods.get(str(method_id))

    def record_outcome(self, method_id: str, success: bool) -> None:
        method = self._methods.get(str(method_id))
        if method is None:
            logger.warning("Unknown method: %s", method_id)
            return
        if success:
            method.success_count += 1
        else:
            method.failure_count += 1
        method.last_used = datetime.now(UTC).isoformat()
        total = method.success_count + method.failure_count
        method.effectiveness_score = method.success_count / total if total > 0 else 0.0
        self._save()

    def get_failing_methods(self, field: str, *, threshold: int = FAILURE_THRESHOLD) -> List[VulnMethod]:
        return [
            method
            for method in self._methods.values()
            if method.field == field
            and method.failure_count >= int(threshold)
            and method.failure_count > method.success_count * 2
        ]

    def add_invented_method(self, method: VulnMethod) -> None:
        self._methods[method.method_id] = method
        self._save()
        logger.info("New method invented: %s for field %s", method.name, method.field)

    def get_best_methods(self, field: str, n: int = 5) -> List[VulnMethod]:
        field_methods = [method for method in self._methods.values() if method.field == field]
        return sorted(field_methods, key=lambda method: method.effectiveness_score, reverse=True)[:n]


class SelfReflectionEngine:
    """Monitors failures and invents new methods when thresholds are crossed."""

    def __init__(
        self,
        library: MethodLibrary | None = None,
        reflection_log_path: Path | str | None = None,
        *,
        method_library: MethodLibrary | None = None,
        invention_threshold: int = FAILURE_THRESHOLD,
    ) -> None:
        self._library = method_library or library or MethodLibrary()
        self._log_path = Path(reflection_log_path) if reflection_log_path is not None else self._library.root / "reflection_log.jsonl"
        self._failure_patterns: Dict[str, List[str]] = defaultdict(list)
        self._failure_summary: Dict[str, Dict[str, Any]] = {}
        self._observations: List[FailureObservation] = []
        self._events: List[ReflectionEvent] = []
        self._last_reflection: float = 0.0
        self._invention_threshold = max(1, int(invention_threshold))

    def build_failure_key(self, attack_family: str, failure_pattern: str) -> str:
        return f"{str(attack_family).strip().lower()}::{str(failure_pattern).strip().lower()}"

    def _normalize_field_name(self, field_name: str) -> str:
        return str(field_name or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _expand_field_names(self, field_name: str) -> List[str]:
        root = self._normalize_field_name(field_name)
        if not root:
            return []

        expanded: List[str] = []
        seen: set[str] = set()
        pending = [root]
        while pending:
            current = self._normalize_field_name(pending.pop(0))
            if not current or current in seen:
                continue
            seen.add(current)
            expanded.append(current)

            alias = FIELD_ALIASES.get(current)
            if alias is not None:
                pending.append(alias)
            pending.extend(FIELD_EXPANSIONS.get(current, ()))
        return expanded

    def _infer_field(self, attack_family: str, explicit_field: str | None = None) -> str:
        if explicit_field:
            normalized_field = self._normalize_field_name(str(explicit_field))
            return FIELD_ALIASES.get(normalized_field, normalized_field)
        method = self._library.get_method(attack_family)
        if method is not None:
            normalized_field = self._normalize_field_name(method.field)
            return FIELD_ALIASES.get(normalized_field, normalized_field)
        normalized_field = self._normalize_field_name(str(attack_family))
        return FIELD_ALIASES.get(normalized_field, normalized_field)

    def _append_event(self, event: ReflectionEvent) -> None:
        self._events.append(event)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict()) + "\n")

    def observe_failure(
        self,
        method_id: str,
        field_or_pattern: str,
        error_pattern: str | None = None,
        *,
        reason: str = "",
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if error_pattern is None:
            attack_family = str(method_id)
            failure_pattern = str(field_or_pattern)
            field = self._infer_field(attack_family)
        else:
            attack_family = str(method_id)
            field = self._infer_field(attack_family, explicit_field=str(field_or_pattern))
            failure_pattern = str(error_pattern)

        self._library.record_outcome(attack_family, success=False)
        self._failure_patterns[field].append(failure_pattern)

        failure_key = self.build_failure_key(attack_family, failure_pattern)
        summary = self._failure_summary.setdefault(
            failure_key,
            {
                "attack_family": attack_family,
                "field": field,
                "failure_pattern": failure_pattern,
                "count": 0,
                "invented_method_id": None,
            },
        )
        summary["count"] = int(summary["count"]) + 1

        observation = FailureObservation(
            method_id=attack_family,
            attack_family=attack_family,
            field=field,
            failure_pattern=failure_pattern,
            reason=str(reason or failure_pattern),
            timestamp=datetime.now(UTC).isoformat(),
            count_for_pattern=int(summary["count"]),
            context=dict(context or {}),
        )
        self._observations.append(observation)

        failing_methods = self._library.get_failing_methods(field, threshold=self._invention_threshold)
        invented_method: VulnMethod | None = None
        if int(summary["count"]) >= self._invention_threshold and summary["invented_method_id"] is None:
            invented_method = self._reflect(
                field,
                failing_methods,
                trigger="failure_threshold",
                attack_family=attack_family,
                failure_pattern=failure_pattern,
                source_failure_count=int(summary["count"]),
            )
            if invented_method is not None:
                summary["invented_method_id"] = invented_method.method_id

        return {
            "failure_key": failure_key,
            "failure_count": int(summary["count"]),
            "invented_method": invented_method,
            "field": field,
        }

    def observe_success(self, method_id: str, field: str | None = None) -> None:
        del field
        self._library.record_outcome(method_id, success=True)

    def idle_reflection(self, fields: List[str], *, idle_seconds: float | None = None) -> Dict[str, Any]:
        requested_fields = [
            str(field).strip()
            for field in fields
            if str(field).strip()
        ]
        if not requested_fields:
            requested_fields = sorted(
                {
                    method.field
                    for method in self._library.get_all_methods()
                    if str(method.field).strip()
                }
            )

        if idle_seconds is not None and float(idle_seconds) < IDLE_THRESHOLD:
            return {
                "triggered": False,
                "rate_limited": False,
                "reason": "idle_threshold_not_met",
                "requested_fields": requested_fields,
                "checked_fields": [],
                "reflected_fields": [],
                "invented_method_ids": [],
                "idle_seconds": float(idle_seconds),
                "idle_threshold": float(IDLE_THRESHOLD),
                "seconds_until_next": 0.0,
            }

        now = time.time()
        seconds_until_next = max(0.0, float(REFLECTION_INTERVAL) - (now - self._last_reflection))
        if seconds_until_next > 0.0:
            return {
                "triggered": False,
                "rate_limited": True,
                "reason": "rate_limited",
                "requested_fields": requested_fields,
                "checked_fields": [],
                "reflected_fields": [],
                "invented_method_ids": [],
                "idle_seconds": None if idle_seconds is None else float(idle_seconds),
                "idle_threshold": float(IDLE_THRESHOLD),
                "seconds_until_next": round(seconds_until_next, 3),
            }

        self._last_reflection = now
        checked_fields: List[str] = []
        reflected_fields: List[str] = []
        invented_method_ids: List[str] = []
        seen_fields: set[str] = set()

        for field in requested_fields:
            for candidate_field in self._expand_field_names(field):
                if candidate_field in seen_fields:
                    continue
                seen_fields.add(candidate_field)
                checked_fields.append(candidate_field)

                failing_methods = self._library.get_failing_methods(
                    candidate_field,
                    threshold=self._invention_threshold,
                )
                if not failing_methods:
                    continue

                invented_method = self._reflect(candidate_field, failing_methods, trigger="idle")
                reflected_fields.append(candidate_field)
                if invented_method is not None:
                    invented_method_ids.append(invented_method.method_id)

        return {
            "triggered": bool(reflected_fields),
            "rate_limited": False,
            "reason": "reflected" if reflected_fields else "no_failing_methods",
            "requested_fields": requested_fields,
            "checked_fields": checked_fields,
            "reflected_fields": reflected_fields,
            "invented_method_ids": invented_method_ids,
            "idle_seconds": None if idle_seconds is None else float(idle_seconds),
            "idle_threshold": float(IDLE_THRESHOLD),
            "seconds_until_next": float(REFLECTION_INTERVAL),
        }

    def _reflect(
        self,
        field: str,
        failing_methods: List[VulnMethod],
        *,
        trigger: str,
        attack_family: str | None = None,
        failure_pattern: str | None = None,
        source_failure_count: int = 0,
    ) -> Optional[VulnMethod]:
        patterns = self._failure_patterns.get(field, [])
        candidate_family = attack_family or (failing_methods[0].method_id if failing_methods else field)
        candidate_pattern = failure_pattern or (patterns[-1] if patterns else "repeated_failure")
        invented_method = self._invent_method_rule_based(
            field,
            failing_methods,
            patterns,
            attack_family=candidate_family,
            failure_pattern=candidate_pattern,
            source_failure_count=source_failure_count or len(patterns),
        )
        if invented_method is not None:
            self._library.add_invented_method(invented_method)

        reasoning = self._generate_reasoning(field, failing_methods, patterns)
        reflection_event = ReflectionEvent(
            event_id=uuid.uuid4().hex[:8],
            event_type="reflection",
            trigger=trigger,
            field=field,
            failed_method=", ".join(method.method_id for method in failing_methods) or str(candidate_family),
            failure_patterns=patterns[-5:],
            new_method_proposed=invented_method.name if invented_method is not None else None,
            invented_method_id=invented_method.method_id if invented_method is not None else None,
            reasoning=reasoning,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._append_event(reflection_event)

        if invented_method is not None:
            self._append_event(
                ReflectionEvent(
                    event_id=uuid.uuid4().hex[:8],
                    event_type="method_invented",
                    trigger=trigger,
                    field=field,
                    failed_method=str(candidate_family),
                    failure_patterns=[candidate_pattern],
                    new_method_proposed=invented_method.name,
                    invented_method_id=invented_method.method_id,
                    reasoning=reasoning,
                    timestamp=datetime.now(UTC).isoformat(),
                )
            )
            logger.info("Self-reflection [%s/%s]: invented '%s'", field, trigger, invented_method.name)
        else:
            logger.info("Self-reflection [%s/%s]: no new method invented yet", field, trigger)

        return invented_method

    def _invent_method_rule_based(
        self,
        field: str,
        failing_methods: List[VulnMethod],
        patterns: List[str],
        *,
        attack_family: str,
        failure_pattern: str,
        source_failure_count: int,
    ) -> Optional[VulnMethod]:
        normalized_field = self._infer_field(str(field), explicit_field=str(field))
        pattern_text = " ".join([*patterns[-5:], str(failure_pattern)]).lower()

        candidate_fields: List[str] = []
        for candidate_field in [normalized_field, *self._expand_field_names(normalized_field)]:
            if candidate_field not in candidate_fields:
                candidate_fields.append(candidate_field)

        for candidate_field in candidate_fields:
            field_rules = ESCALATION_RULES.get(candidate_field, [])
            field_for_method = normalized_field if normalized_field in ESCALATION_RULES else candidate_field
            existing_methods = self._library.list_methods(field=field_for_method)
            for trigger_text, method_prefix, name, description in field_rules:
                if trigger_text not in pattern_text:
                    continue
                if any(
                    existing.method_id.startswith(f"{method_prefix}_") or existing.name == name
                    for existing in existing_methods
                ):
                    continue
                method_id = f"{method_prefix}_{uuid.uuid4().hex[:4]}"
                return VulnMethod(
                    method_id=method_id,
                    name=name,
                    description=description,
                    field=field_for_method,
                    invented_at=datetime.now(UTC).isoformat(),
                    invented_by="self_reflection",
                    attack_family=str(attack_family),
                    failure_pattern=str(failure_pattern),
                    source_failure_count=int(source_failure_count),
                )
        return None

    def _generate_reasoning(self, field: str, failing_methods: List[VulnMethod], patterns: List[str]) -> str:
        method_names = [method.name for method in failing_methods] or [field]
        return (
            f"Field '{field}': methods {method_names} failed "
            f"{sum(method.failure_count for method in failing_methods) if failing_methods else len(patterns)} times. "
            f"Common patterns: {set(patterns[-5:])}. "
            f"Hypothesis: defenses are blocking known signatures. "
            f"New approach: try encoding/timing/indirect variants."
        )

    def list_methods(self, *, invented_by: str | None = None, field: str | None = None) -> List[VulnMethod]:
        return self._library.list_methods(invented_by=invented_by, field=field)

    def get_failure_summary(self) -> Dict[str, Dict[str, Any]]:
        return {key: dict(value) for key, value in self._failure_summary.items()}

    def list_reflection_events(self) -> List[ReflectionEvent]:
        return list(self._events)

    def list_failure_observations(self) -> List[FailureObservation]:
        return list(self._observations)

    def get_stats(self) -> dict[str, Any]:
        all_methods = self._library.get_all_methods()
        invented = [method for method in all_methods if method.invented_by == "self_reflection"]
        return {
            "total_methods": len(all_methods),
            "invented_methods": len(invented),
            "human_methods": len(all_methods) - len(invented),
            "total_successes": sum(method.success_count for method in all_methods),
            "total_failures": sum(method.failure_count for method in all_methods),
            "avg_effectiveness": (
                sum(method.effectiveness_score for method in all_methods) / len(all_methods)
                if all_methods
                else 0.0
            ),
        }


if __name__ == "__main__":
    library = MethodLibrary(root=Path("data/test_self_reflection"))
    engine = SelfReflectionEngine(method_library=library)
    for attempt in range(4):
        engine.observe_failure("xss_basic", "xss", f"basic payload filtered attempt {attempt + 1}")
    print(json.dumps(engine.get_stats(), indent=2))


__all__ = [
    "FailureObservation",
    "IDLE_THRESHOLD",
    "MethodLibrary",
    "ReflectionEvent",
    "SelfReflectionEngine",
    "VulnMethod",
]
