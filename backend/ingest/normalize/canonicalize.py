from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_json(item) for item in value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return repr(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _normalized_text(payload: Mapping[str, Any]) -> str:
    parts = []
    for key in ("title", "summary", "description", "content", "text", "body"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    tags = payload.get("tags", [])
    if isinstance(tags, (list, tuple, set)):
        parts.extend(str(tag) for tag in tags if tag)
    return " ".join(parts).strip()


@dataclass
class CanonicalRecord:
    record_id: str
    source_name: str
    source_type: str
    source_url: str
    source_id: str
    immutable_source_ref: str
    content_sha256: str
    normalized_text: str
    provenance: Dict[str, Any]
    received_at: str
    raw_payload: Dict[str, Any]
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def canonicalize_record(
    raw_payload: Mapping[str, Any],
    *,
    source_name: str,
    source_type: str,
) -> CanonicalRecord:
    payload = _normalize_json(dict(raw_payload))
    source_url = str(payload.get("source_url", payload.get("url", "")) or "")
    source_id = str(payload.get("source_id", payload.get("id", "")) or "")
    normalized_text = _normalized_text(payload)
    content_sha256 = str(payload.get("content_sha256", "") or "")
    if not content_sha256 and normalized_text:
        content_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    immutable_source_ref = source_id or source_url
    record_id = hashlib.sha256(
        json.dumps(
            {
                "source_name": source_name,
                "source_type": source_type,
                "immutable_source_ref": immutable_source_ref,
                "content_sha256": content_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    provenance = payload.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {"value": provenance}
    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        tags = list(tags) if isinstance(tags, (tuple, set)) else [str(tags)]
    return CanonicalRecord(
        record_id=record_id,
        source_name=str(source_name),
        source_type=str(source_type),
        source_url=source_url,
        source_id=source_id,
        immutable_source_ref=immutable_source_ref,
        content_sha256=content_sha256,
        normalized_text=normalized_text,
        provenance=_normalize_json(provenance),
        received_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        raw_payload=payload,
        tags=[str(item) for item in tags if item],
    )
