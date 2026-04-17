from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from config.storage_config import SSD_ROOT


EVIDENCE_DIR = SSD_ROOT / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    capture_type: str
    source_url: str
    captured_at: str
    sha256: str
    size_bytes: int
    content_path: str


def capture_http_response(url: str, response_data: bytes) -> EvidenceRecord:
    evidence_id = hashlib.sha256(f"{url}{time.time()}".encode("utf-8")).hexdigest()[:16]
    sha256 = hashlib.sha256(response_data).hexdigest()
    path = EVIDENCE_DIR / f"{evidence_id}.bin"
    path.write_bytes(response_data)
    return EvidenceRecord(
        evidence_id=evidence_id,
        capture_type="http_response",
        source_url=url,
        captured_at=datetime.now(UTC).isoformat(),
        sha256=sha256,
        size_bytes=len(response_data),
        content_path=str(path),
    )

