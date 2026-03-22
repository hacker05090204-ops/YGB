"""Deduplication index for ingested samples."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.ingestion._integrity import log_module_sha256

logger = logging.getLogger("ygb.ingestion.dedup")


class DedupIndex:
    def __init__(self, index_path: str = "data/raw/dedup.db") -> None:
        requested_path = Path(index_path)
        if requested_path.suffix.lower() == ".json":
            self.index_path = requested_path.with_suffix(".db")
            self.legacy_json_path = requested_path
        else:
            self.index_path = requested_path
            self.legacy_json_path = requested_path.with_name("dedup_index.json")
        self.conn: sqlite3.Connection | None = None
        self.dupes_found = 0

    def load(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.index_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_hashes (
                sha256 TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_hashes_sha256 ON seen_hashes(sha256)"
        )
        self.conn.commit()
        self._migrate_legacy_json_if_needed()

    @property
    def seen_hashes(self) -> set[str]:
        if self.conn is None:
            return set()
        rows = self.conn.execute("SELECT sha256 FROM seen_hashes").fetchall()
        return {str(row[0]) for row in rows}

    def _migrate_legacy_json_if_needed(self) -> None:
        if self.conn is None or not self.legacy_json_path.exists():
            return

        payload = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries = payload.get("seen_hashes", [])
        else:
            entries = payload

        timestamp = datetime.now(timezone.utc).isoformat()
        self.conn.executemany(
            "INSERT OR IGNORE INTO seen_hashes (sha256, first_seen, source) VALUES (?, ?, ?)",
            [(str(entry), timestamp, "legacy_json") for entry in entries],
        )
        self.conn.commit()
        try:
            self.legacy_json_path.unlink()
        except OSError:
            logger.warning("dedup_legacy_json_cleanup_failed", extra={"path": str(self.legacy_json_path)})

    def is_duplicate(self, sha256: str) -> bool:
        if self.conn is None:
            raise RuntimeError("DedupIndex.load() must be called before is_duplicate()")
        row = self.conn.execute(
            "SELECT 1 FROM seen_hashes WHERE sha256 = ? LIMIT 1",
            (sha256,),
        ).fetchone()
        duplicate = row is not None
        if duplicate:
            self.dupes_found += 1
        return duplicate

    def mark_seen(self, sha256: str, source: str = "") -> None:
        if self.conn is None:
            raise RuntimeError("DedupIndex.load() must be called before mark_seen()")
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_hashes (sha256, first_seen, source) VALUES (?, ?, ?)",
            (sha256, datetime.now(timezone.utc).isoformat(), source),
        )

    def save(self) -> None:
        if self.conn is not None:
            self.conn.commit()

    def stats(self) -> dict[str, float]:
        if self.conn is None:
            total_seen = 0
        else:
            total_seen = int(
                self.conn.execute("SELECT COUNT(*) FROM seen_hashes").fetchone()[0]
            )
        total_observed = total_seen + self.dupes_found
        duplicate_rate = self.dupes_found / max(total_observed, 1)
        return {
            "total_seen": float(total_seen),
            "dupes_found": float(self.dupes_found),
            "duplicate_rate": duplicate_rate,
        }

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
