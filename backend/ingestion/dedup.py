"""Deduplication index for ingested samples."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.ingestion._integrity import log_module_sha256

logger = logging.getLogger("ygb.ingestion.dedup")


class DedupIndex:
    def __init__(self, index_path: str = "data/dedup_store.json") -> None:
        requested_path = Path(index_path)
        if requested_path.name == "dedup_store.json":
            self.index_path = requested_path
            self.legacy_json_path = requested_path.with_name("dedup_index.json")
        else:
            store_parent = (
                requested_path.parent.parent
                if requested_path.parent.name.lower() == "raw"
                else requested_path.parent
            )
            self.index_path = store_parent / "dedup_store.json"
            self.legacy_json_path = requested_path
        self._loaded = False
        self._entries: list[dict[str, str]] = []
        self._seen_cve_ids: set[str] = set()
        self._seen_text_hashes: set[str] = set()
        self.dupes_found = 0

    @property
    def seen_hashes(self) -> set[str]:
        return set(self._seen_text_hashes)

    @property
    def seen_cve_ids(self) -> set[str]:
        return set(self._seen_cve_ids)

    def load(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = []
        self._seen_cve_ids = set()
        self._seen_text_hashes = set()
        if self.index_path.exists():
            payload = self._read_payload(self.index_path)
            self._hydrate_from_payload(payload)
        elif self._migrate_legacy_json_if_needed():
            payload = self._read_payload(self.index_path)
            self._hydrate_from_payload(payload)
        else:
            self._loaded = True
            self.save()
            return
        self._loaded = True

    def _read_payload(self, path: Path) -> dict[str, Any]:
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Dedup store is corrupted: {path}") from exc
        except OSError as exc:
            raise OSError(f"Unable to read dedup store: {path}") from exc
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Dedup store payload must be an object: {path}")
        return raw_payload

    def _hydrate_from_payload(self, payload: dict[str, Any]) -> None:
        seen_cve_ids = {
            str(value)
            for value in payload.get("seen_cve_ids", [])
            if str(value or "")
        }
        seen_text_hashes = {
            str(value)
            for value in payload.get(
                "seen_text_hashes",
                payload.get("seen_hashes", []),
            )
            if str(value or "")
        }
        entries: list[dict[str, str]] = []
        raw_entries = payload.get("entries", [])
        if isinstance(raw_entries, list):
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict):
                    continue
                cve_id = str(raw_entry.get("cve_id", "") or "")
                text_hash = str(raw_entry.get("text_hash", "") or "")
                if not cve_id and not text_hash:
                    continue
                entry = {
                    "cve_id": cve_id,
                    "text_hash": text_hash,
                    "first_seen": str(
                        raw_entry.get("first_seen")
                        or datetime.now(timezone.utc).isoformat()
                    ),
                    "source": str(raw_entry.get("source", "") or ""),
                }
                entries.append(entry)
                if cve_id:
                    seen_cve_ids.add(cve_id)
                if text_hash:
                    seen_text_hashes.add(text_hash)
        if not entries:
            timestamp = datetime.now(timezone.utc).isoformat()
            for text_hash in sorted(seen_text_hashes):
                entries.append(
                    {
                        "cve_id": "",
                        "text_hash": text_hash,
                        "first_seen": timestamp,
                        "source": "legacy_json",
                    }
                )
            for cve_id in sorted(seen_cve_ids):
                if any(entry["cve_id"] == cve_id for entry in entries):
                    continue
                entries.append(
                    {
                        "cve_id": cve_id,
                        "text_hash": "",
                        "first_seen": timestamp,
                        "source": "legacy_json",
                    }
                )
        self._entries = entries
        self._seen_cve_ids = seen_cve_ids
        self._seen_text_hashes = seen_text_hashes

    def _migrate_legacy_json_if_needed(self) -> bool:
        if (
            self.legacy_json_path == self.index_path
            or not self.legacy_json_path.exists()
        ):
            return False
        try:
            payload = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Legacy dedup payload is corrupted: {self.legacy_json_path}"
            ) from exc
        except OSError as exc:
            raise OSError(
                f"Unable to read legacy dedup payload: {self.legacy_json_path}"
            ) from exc

        timestamp = datetime.now(timezone.utc).isoformat()
        seen_cve_ids: list[str] = []
        seen_text_hashes: list[str] = []
        entries: list[dict[str, str]] = []
        if isinstance(payload, dict):
            seen_cve_ids = [
                str(value)
                for value in payload.get("seen_cve_ids", [])
                if str(value or "")
            ]
            seen_text_hashes = [
                str(value)
                for value in payload.get("seen_text_hashes", payload.get("seen_hashes", []))
                if str(value or "")
            ]
            raw_entries = payload.get("entries", [])
            if isinstance(raw_entries, list):
                for raw_entry in raw_entries:
                    if not isinstance(raw_entry, dict):
                        continue
                    cve_id = str(raw_entry.get("cve_id", "") or "")
                    text_hash = str(raw_entry.get("text_hash", "") or "")
                    if not cve_id and not text_hash:
                        continue
                    entries.append(
                        {
                            "cve_id": cve_id,
                            "text_hash": text_hash,
                            "first_seen": str(raw_entry.get("first_seen", timestamp) or timestamp),
                            "source": str(raw_entry.get("source", "legacy_json") or "legacy_json"),
                        }
                    )
        elif isinstance(payload, list):
            seen_text_hashes = [str(value) for value in payload if str(value or "")]
        else:
            raise ValueError(
                f"Unsupported legacy dedup payload type: {self.legacy_json_path}"
            )

        if not entries:
            entries = [
                {
                    "cve_id": "",
                    "text_hash": text_hash,
                    "first_seen": timestamp,
                    "source": "legacy_json",
                }
                for text_hash in seen_text_hashes
            ]
            entries.extend(
                {
                    "cve_id": cve_id,
                    "text_hash": "",
                    "first_seen": timestamp,
                    "source": "legacy_json",
                }
                for cve_id in seen_cve_ids
            )

        self._entries = entries
        self._seen_cve_ids = set(seen_cve_ids) | {
            entry["cve_id"] for entry in entries if entry["cve_id"]
        }
        self._seen_text_hashes = set(seen_text_hashes) | {
            entry["text_hash"] for entry in entries if entry["text_hash"]
        }
        self._loaded = True
        self.save()
        try:
            self.legacy_json_path.unlink()
        except OSError:
            logger.warning(
                "dedup_legacy_json_cleanup_failed",
                extra={"path": str(self.legacy_json_path)},
            )
        return True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("DedupIndex.load() must be called before use")

    def has_cve_id(self, cve_id: str) -> bool:
        self._ensure_loaded()
        normalized_cve_id = str(cve_id or "")
        return bool(normalized_cve_id) and normalized_cve_id in self._seen_cve_ids

    def has_text_hash(self, text_hash: str) -> bool:
        self._ensure_loaded()
        normalized_text_hash = str(text_hash or "")
        return bool(normalized_text_hash) and normalized_text_hash in self._seen_text_hashes

    def is_duplicate(self, cve_id: str, text_hash: str | None = None) -> bool:
        self._ensure_loaded()
        normalized_cve_id = str(cve_id or "")
        normalized_text_hash = str(text_hash or "")
        duplicate = False
        if normalized_cve_id and normalized_cve_id in self._seen_cve_ids:
            duplicate = True
        elif normalized_text_hash and normalized_text_hash in self._seen_text_hashes:
            duplicate = True
        elif not normalized_text_hash and normalized_cve_id in self._seen_text_hashes:
            duplicate = True
        if duplicate:
            self.dupes_found += 1
        return duplicate

    def record_seen(
        self,
        cve_id: str,
        text_hash: str | None = None,
        source: str = "",
    ) -> None:
        self._ensure_loaded()
        normalized_cve_id = str(cve_id or "")
        normalized_text_hash = str(text_hash or "")
        if not normalized_cve_id and not normalized_text_hash:
            return

        changed = False
        if normalized_cve_id and normalized_cve_id not in self._seen_cve_ids:
            self._seen_cve_ids.add(normalized_cve_id)
            changed = True
        if normalized_text_hash and normalized_text_hash not in self._seen_text_hashes:
            self._seen_text_hashes.add(normalized_text_hash)
            changed = True
        if not changed:
            return

        self._entries.append(
            {
                "cve_id": normalized_cve_id,
                "text_hash": normalized_text_hash,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "source": str(source or ""),
            }
        )
        self.save()

    def mark_seen(self, sha256: str, source: str = "") -> None:
        self.record_seen("", sha256, source=source)

    def save(self) -> None:
        self._ensure_loaded()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seen_cve_ids": sorted(self._seen_cve_ids),
            "seen_text_hashes": sorted(self._seen_text_hashes),
            "entries": list(self._entries),
        }
        temp_path = self.index_path.with_suffix(f"{self.index_path.suffix}.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temp_path, self.index_path)
            self._write_compatibility_payload()
        except OSError as exc:
            raise OSError(f"Unable to persist dedup store: {self.index_path}") from exc

    def _write_compatibility_payload(self) -> None:
        if (
            self.legacy_json_path == self.index_path
            or self.legacy_json_path.name != "dedup_index.json"
        ):
            return
        self.legacy_json_path.parent.mkdir(parents=True, exist_ok=True)
        compatibility_payload = {
            "seen_hashes": sorted(self._seen_text_hashes),
            "seen_cve_ids": sorted(self._seen_cve_ids),
            "entries": list(self._entries),
        }
        temp_path = self.legacy_json_path.with_suffix(
            f"{self.legacy_json_path.suffix}.tmp"
        )
        temp_path.write_text(
            json.dumps(compatibility_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temp_path, self.legacy_json_path)

    def stats(self) -> dict[str, float]:
        total_seen = float(len(self._entries))
        total_observed = total_seen + float(self.dupes_found)
        duplicate_rate = float(self.dupes_found) / max(total_observed, 1.0)
        return {
            "total_seen": total_seen,
            "dupes_found": float(self.dupes_found),
            "duplicate_rate": duplicate_rate,
        }

    def close(self) -> None:
        if self._loaded:
            self.save()
        self._loaded = False


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
