from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, Iterable, List, Optional, Tuple

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, sort_keys=True)
        else:
            text = str(value)
        tokens.update(_TOKEN_RE.findall(text.lower()))
    return tokens


def _normalize(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": True, "size": len(value)}
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    return value


@dataclass
class MemoryEntry:
    record_id: str
    namespace: str
    key: str
    prompt: str
    response: Dict[str, Any]
    tags: Tuple[str, ...] = ()
    references: Tuple[str, ...] = ()
    metrics: Dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_accessed_at: str = ""
    access_count: int = 0
    feedback_score: float = 0.0


class UnifiedMemoryStore:
    """Persistent retrieval layer for cross-subsystem decisions."""

    def __init__(self, path: str):
        self.path = path
        self._entries: Dict[str, MemoryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for item in payload.get("entries", []):
                entry = MemoryEntry(**item)
                self._entries[entry.record_id] = entry
        except Exception:
            self._entries = {}

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "entries": [_normalize(asdict(entry)) for entry in self._entries.values()],
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                handle,
                indent=2,
            )
            handle.write("\n")
        os.replace(tmp, self.path)

    def remember(
        self,
        namespace: str,
        key: str,
        *,
        prompt: str,
        response: Dict[str, Any],
        tags: Iterable[str] = (),
        references: Iterable[str] = (),
        metrics: Optional[Dict[str, float]] = None,
    ) -> MemoryEntry:
        existing = self.find(namespace, key)
        entry = MemoryEntry(
            record_id=existing.record_id if existing else f"MEM-{uuid.uuid4().hex[:12].upper()}",
            namespace=namespace,
            key=key,
            prompt=prompt,
            response=response,
            tags=tuple(sorted({str(tag) for tag in tags})),
            references=tuple(sorted({str(ref) for ref in references})),
            metrics=dict(metrics or {}),
            created_at=existing.created_at if existing else datetime.now(UTC).isoformat(),
            last_accessed_at=existing.last_accessed_at if existing else "",
            access_count=existing.access_count if existing else 0,
            feedback_score=existing.feedback_score if existing else 0.0,
        )
        self._entries[entry.record_id] = entry
        self._persist()
        return entry

    def find(self, namespace: str, key: str) -> Optional[MemoryEntry]:
        for entry in self._entries.values():
            if entry.namespace == namespace and entry.key == key:
                return entry
        return None

    def retrieve(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        top_k: int = 5,
        required_tags: Iterable[str] = (),
    ) -> List[MemoryEntry]:
        query_tokens = _tokenize(query)
        required = {str(tag) for tag in required_tags}
        scored: List[tuple[float, MemoryEntry]] = []

        for entry in self._entries.values():
            if namespace and entry.namespace != namespace:
                continue
            if required and not required.issubset(set(entry.tags)):
                continue
            if query_tokens:
                overlap = len(
                    query_tokens
                    & _tokenize(entry.prompt, entry.response, entry.tags, entry.references)
                )
            else:
                overlap = 1
            if overlap <= 0:
                continue
            score = overlap + max(entry.feedback_score, 0.0) + min(entry.access_count, 20) * 0.05
            scored.append((score, entry))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        selected = [entry for _, entry in scored[: max(1, top_k)]]
        if selected:
            now = datetime.now(UTC).isoformat()
            for entry in selected:
                entry.access_count += 1
                entry.last_accessed_at = now
            self._persist()
        return selected

    def reinforce(self, record_id: str, delta: float) -> Optional[MemoryEntry]:
        entry = self._entries.get(record_id)
        if entry is None:
            return None
        entry.feedback_score = round(entry.feedback_score + float(delta), 4)
        self._persist()
        return entry

    def latest(self, namespace: Optional[str] = None, limit: int = 10) -> List[MemoryEntry]:
        entries = [
            entry for entry in self._entries.values()
            if namespace is None or entry.namespace == namespace
        ]
        entries.sort(key=lambda item: item.created_at, reverse=True)
        return entries[: max(1, limit)]

    def stats(self) -> Dict[str, Any]:
        by_namespace: Dict[str, int] = {}
        for entry in self._entries.values():
            by_namespace[entry.namespace] = by_namespace.get(entry.namespace, 0) + 1
        return {
            "entries": len(self._entries),
            "namespaces": by_namespace,
            "path": self.path,
        }
