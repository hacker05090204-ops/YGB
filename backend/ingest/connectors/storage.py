from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


class FileStorageConnector:
    """Loads immutable local files into the shared ingest schema."""

    source_name = "storage"
    source_type = "storage"

    def load_record(self, path: str) -> Dict[str, Any]:
        file_path = Path(path).resolve()
        raw_bytes = file_path.read_bytes()
        content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        text = raw_bytes.decode("utf-8", errors="replace")
        payload: Dict[str, Any]
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"content": text}
        payload.setdefault("source_id", file_path.name)
        payload.setdefault("source_url", file_path.as_uri())
        payload.setdefault("source_name", self.source_name)
        payload.setdefault("source_type", self.source_type)
        payload.setdefault("content", text)
        payload.setdefault("content_sha256", content_sha256)
        payload.setdefault(
            "provenance",
            {
                "connector": self.source_name,
                "path": str(file_path),
            },
        )
        return payload
