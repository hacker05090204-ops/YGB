from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping, Sequence

from impl_v1.phase49.moe import EXPERT_FIELDS

DEFAULT_VRAM_RESERVE_GB = 0.75
SATURATION_UTILIZATION_THRESHOLD = 95.0
_LOW_VRAM_TARGET_GB = 8.0


@dataclass(frozen=True)
class FieldScheduleProfile:
    field_name: str
    required_vram_gb: float
    priority: int
    complexity: str


FIELD_PROFILES: dict[str, FieldScheduleProfile] = {
    "web_vulns": FieldScheduleProfile("web_vulns", 1.50, 92, "low"),
    "api_testing": FieldScheduleProfile("api_testing", 1.75, 90, "low"),
    "mobile_apk": FieldScheduleProfile("mobile_apk", 4.25, 76, "high"),
    "cloud_misconfig": FieldScheduleProfile("cloud_misconfig", 3.75, 84, "medium"),
    "blockchain": FieldScheduleProfile("blockchain", 4.50, 74, "high"),
    "iot": FieldScheduleProfile("iot", 3.75, 72, "high"),
    "hardware": FieldScheduleProfile("hardware", 5.00, 70, "high"),
    "firmware": FieldScheduleProfile("firmware", 4.75, 71, "high"),
    "ssrf": FieldScheduleProfile("ssrf", 2.50, 94, "medium"),
    "rce": FieldScheduleProfile("rce", 3.75, 98, "high"),
    "xss": FieldScheduleProfile("xss", 1.40, 96, "low"),
    "sqli": FieldScheduleProfile("sqli", 2.25, 97, "medium"),
    "auth_bypass": FieldScheduleProfile("auth_bypass", 2.00, 95, "medium"),
    "idor": FieldScheduleProfile("idor", 1.60, 96, "low"),
    "graphql_abuse": FieldScheduleProfile("graphql_abuse", 2.40, 88, "medium"),
    "rest_attacks": FieldScheduleProfile("rest_attacks", 2.00, 89, "medium"),
    "csrf": FieldScheduleProfile("csrf", 1.25, 82, "low"),
    "file_upload": FieldScheduleProfile("file_upload", 2.50, 91, "medium"),
    "deserialization": FieldScheduleProfile("deserialization", 3.00, 90, "medium"),
    "privilege_escalation": FieldScheduleProfile("privilege_escalation", 3.25, 93, "high"),
    "cryptography": FieldScheduleProfile("cryptography", 3.50, 78, "high"),
    "subdomain_takeover": FieldScheduleProfile("subdomain_takeover", 1.50, 83, "low"),
    "race_condition": FieldScheduleProfile("race_condition", 2.75, 87, "medium"),
}


def _normalize_utilization(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric <= 1.0:
        numeric *= 100.0
    return max(0.0, min(numeric, 100.0))


def _resource_attr(resource_or_vram: Any, name: str, default: Any) -> Any:
    if isinstance(resource_or_vram, Mapping):
        return resource_or_vram.get(name, default)
    if hasattr(resource_or_vram, name):
        return getattr(resource_or_vram, name)
    return default


def _available_vram_gb(resource_or_vram: Any) -> float:
    if isinstance(resource_or_vram, Real) and not isinstance(resource_or_vram, bool):
        return max(0.0, float(resource_or_vram))
    return max(0.0, float(_resource_attr(resource_or_vram, "available_vram_gb", 0.0) or 0.0))


def _healthy(resource_or_vram: Any) -> bool:
    value = _resource_attr(resource_or_vram, "healthy", True)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "healthy"}
    return bool(value)


def _effective_available_vram_gb(
    resource_or_vram: Any,
    *,
    reserve_vram_gb: float = DEFAULT_VRAM_RESERVE_GB,
) -> float:
    if not _healthy(resource_or_vram):
        return 0.0

    utilization = _normalize_utilization(_resource_attr(resource_or_vram, "gpu_utilization", 0.0))
    if utilization >= SATURATION_UTILIZATION_THRESHOLD:
        return 0.0

    available = max(0.0, _available_vram_gb(resource_or_vram) - max(0.0, float(reserve_vram_gb)))
    if utilization >= 90.0:
        return available * 0.85
    if utilization >= 80.0:
        return available * 0.95
    return available


def get_field_profile(field_name: str) -> FieldScheduleProfile:
    normalized = str(field_name or "").strip()
    if not normalized:
        raise ValueError("field_name is required")
    return FIELD_PROFILES.get(
        normalized,
        FieldScheduleProfile(
            field_name=normalized,
            required_vram_gb=2.50,
            priority=50,
            complexity="adaptive",
        ),
    )


def can_handle(
    field_name: str,
    resource_or_vram: Any,
    *,
    reserve_vram_gb: float = DEFAULT_VRAM_RESERVE_GB,
) -> bool:
    profile = get_field_profile(field_name)
    effective_available = _effective_available_vram_gb(
        resource_or_vram,
        reserve_vram_gb=reserve_vram_gb,
    )
    return effective_available >= profile.required_vram_gb


def _priority_score(
    profile: FieldScheduleProfile,
    *,
    effective_available_vram_gb: float,
) -> float:
    fits = effective_available_vram_gb >= profile.required_vram_gb
    scarcity = max(0.0, _LOW_VRAM_TARGET_GB - effective_available_vram_gb)
    abundance = max(0.0, effective_available_vram_gb - _LOW_VRAM_TARGET_GB)
    deficit = max(0.0, profile.required_vram_gb - effective_available_vram_gb)

    score = float(profile.priority * 100)
    score += 10_000.0 if fits else -(deficit * 2_000.0)
    score += scarcity * max(0.0, 10.0 - profile.required_vram_gb) * 15.0
    score += abundance * profile.required_vram_gb * 20.0
    if fits and effective_available_vram_gb >= _LOW_VRAM_TARGET_GB:
        score += profile.required_vram_gb * 1_500.0
    return score


def get_priority_order(
    resource_or_vram: Any,
    *,
    fields: Sequence[str] | None = None,
    reserve_vram_gb: float = DEFAULT_VRAM_RESERVE_GB,
) -> list[str]:
    selected_fields: list[str] = []
    seen: set[str] = set()
    for field_name in fields or EXPERT_FIELDS:
        normalized = str(field_name or "").strip()
        if not normalized or normalized in seen:
            continue
        selected_fields.append(normalized)
        seen.add(normalized)

    effective_available = _effective_available_vram_gb(
        resource_or_vram,
        reserve_vram_gb=reserve_vram_gb,
    )

    def _sort_key(field_name: str) -> tuple[float, int, float, str]:
        profile = get_field_profile(field_name)
        return (
            -_priority_score(
                profile,
                effective_available_vram_gb=effective_available,
            ),
            -profile.priority,
            profile.required_vram_gb,
            profile.field_name,
        )

    return sorted(selected_fields, key=_sort_key)


__all__ = [
    "DEFAULT_VRAM_RESERVE_GB",
    "FIELD_PROFILES",
    "FieldScheduleProfile",
    "SATURATION_UTILIZATION_THRESHOLD",
    "can_handle",
    "get_field_profile",
    "get_priority_order",
]
