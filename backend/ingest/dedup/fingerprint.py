from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def compute_sha256(value: bytes | str) -> str:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return compute_sha256(canonical)


def _tokenize(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        text = json.dumps(value, sort_keys=True)
    elif isinstance(value, (list, tuple, set)):
        text = json.dumps(list(value), sort_keys=True)
    else:
        text = str(value or "")
    return set(_TOKEN_RE.findall(text.lower()))


def near_duplicate_score(left: Any, right: Any) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    union = len(left_tokens | right_tokens)
    if union <= 0:
        return 0.0
    return round(len(left_tokens & right_tokens) / union, 4)
