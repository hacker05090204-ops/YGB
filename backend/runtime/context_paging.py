from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from config.storage_config import SSD_ROOT


LOW_VRAM_CONTEXT_THRESHOLD_GB = 4.0
_DEFAULT_STORAGE_ROOT = SSD_ROOT / "context_paging"
_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class ContextPagingError(RuntimeError):
    """Raised when paged context persistence cannot be completed safely."""


@dataclass(frozen=True)
class ContextPagingDecision:
    mode: str
    reason: str


def _sanitize_segment(value: str) -> str:
    normalized = _SEGMENT_RE.sub("_", str(value or "").strip())
    return normalized.strip("._") or "context"


def _normalize_item(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": True, "size": len(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize_item(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_item(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_item(item) for item in value]
    return value


def resolve_context_paging_decision(
    device_configuration: Any | None,
    *,
    requested_mode: str = "auto",
) -> ContextPagingDecision:
    normalized_mode = str(requested_mode or "auto").strip().lower()
    if normalized_mode not in {"auto", "memory", "disk"}:
        raise ValueError(f"Unsupported context paging mode: {requested_mode!r}")

    if normalized_mode == "memory":
        return ContextPagingDecision(mode="memory", reason="manual_memory")
    if normalized_mode == "disk":
        return ContextPagingDecision(mode="disk", reason="manual_disk")

    selected_device = str(getattr(device_configuration, "selected_device", "") or "").strip().lower()
    total_memory_gb = float(getattr(device_configuration, "total_memory_gb", 0.0) or 0.0)

    if selected_device == "cuda":
        if total_memory_gb <= 0.0:
            return ContextPagingDecision(mode="memory", reason="cuda_vram_unknown_fallback_memory")
        if total_memory_gb < LOW_VRAM_CONTEXT_THRESHOLD_GB:
            return ContextPagingDecision(
                mode="disk",
                reason=(
                    f"cuda_low_vram:{total_memory_gb:.2f}GB"
                    f"<{LOW_VRAM_CONTEXT_THRESHOLD_GB:.2f}GB"
                ),
            )
        return ContextPagingDecision(mode="memory", reason=f"cuda_vram_sufficient:{total_memory_gb:.2f}GB")

    if selected_device == "cpu":
        return ContextPagingDecision(mode="memory", reason="cpu_only_fallback_memory")
    if selected_device == "mps":
        return ContextPagingDecision(mode="memory", reason="mps_fallback_memory")
    if not selected_device:
        return ContextPagingDecision(mode="memory", reason="missing_device_configuration_fallback_memory")
    return ContextPagingDecision(mode="memory", reason=f"{selected_device}_fallback_memory")


class PagedContextBuffer:
    """Reusable runtime context buffer with optional SSD paging for low-VRAM nodes."""

    def __init__(
        self,
        *,
        max_items: int = 20,
        page_size: int = 6,
        mode: str = "auto",
        device_configuration: Any | None = None,
        storage_root: str | Path | None = None,
        namespace: str = "runtime_context",
        context_id: str | None = None,
    ) -> None:
        self.max_items = max(1, int(max_items))
        self.page_size = max(1, int(page_size))
        self.namespace = _sanitize_segment(namespace)
        self.context_id = _sanitize_segment(context_id or f"CTX-{uuid.uuid4().hex[:12].upper()}")
        self.storage_root = Path(storage_root) if storage_root is not None else _DEFAULT_STORAGE_ROOT

        self._decision = resolve_context_paging_decision(
            device_configuration,
            requested_mode=mode,
        )
        self.mode = self._decision.mode
        self.mode_reason = self._decision.reason

        self.storage_path = (
            self.storage_root / self.namespace / self.context_id
            if self.mode == "disk"
            else None
        )
        self._memory_items: list[dict[str, Any]] = []
        self._page_files: list[Path] = []
        self._page_counts: list[int] = []
        self._disk_item_count = 0

        if self.mode == "disk":
            self._initialize_disk_storage()

    @property
    def item_count(self) -> int:
        if self.mode == "disk":
            return self._disk_item_count
        return len(self._memory_items)

    @property
    def page_count(self) -> int:
        if self.item_count <= 0:
            return 1
        return ((self.item_count - 1) // self.page_size) + 1

    @property
    def current_page(self) -> int:
        return self.page_count

    def append(self, item: Mapping[str, Any]) -> None:
        normalized = _normalize_item(dict(item))
        try:
            json.dumps(normalized, sort_keys=True)
        except TypeError as exc:
            raise ContextPagingError(f"Context item is not JSON-serializable: {exc}") from exc

        if self.mode == "disk":
            self._append_disk_item(normalized)
            return

        self._memory_items.append(normalized)
        self._memory_items = self._memory_items[-self.max_items :]

    def items(self) -> list[dict[str, Any]]:
        if self.mode == "disk":
            records: list[dict[str, Any]] = []
            for page_path in self._page_files:
                records.extend(self._read_page(page_path))
            return records
        return [dict(item) for item in self._memory_items]

    def tail(self, limit: int | None = None) -> list[dict[str, Any]]:
        effective_limit = max(1, int(limit or self.page_size))
        if self.mode != "disk":
            return [dict(item) for item in self._memory_items[-effective_limit:]]

        remaining = effective_limit
        records: list[dict[str, Any]] = []
        for page_path in reversed(self._page_files):
            page_items = self._read_page(page_path)
            if not page_items:
                continue
            records = page_items[-remaining:] + records
            remaining = effective_limit - len(records)
            if remaining <= 0:
                break
        return records[-effective_limit:]

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "reason": self.mode_reason,
            "item_count": self.item_count,
            "page_count": self.page_count,
            "storage_path": str(self.storage_path) if self.storage_path is not None else None,
        }

    def _initialize_disk_storage(self) -> None:
        if self.storage_path is None:
            raise ContextPagingError("Disk paging requested without a storage path")
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ContextPagingError(f"Unable to create context paging directory: {exc}") from exc

        self._page_files = []
        self._page_counts = []
        self._disk_item_count = 0
        for page_path in sorted(self.storage_path.glob("page_*.jsonl")):
            count = self._count_page_items(page_path)
            if count <= 0:
                page_path.unlink(missing_ok=True)
                continue
            self._page_files.append(page_path)
            self._page_counts.append(count)
            self._disk_item_count += count
        if self._disk_item_count > self.max_items:
            self._trim_disk_items(self._disk_item_count - self.max_items)

    def _count_page_items(self, page_path: Path) -> int:
        try:
            with page_path.open("r", encoding="utf-8") as handle:
                return sum(1 for line in handle if line.strip())
        except OSError as exc:
            raise ContextPagingError(f"Unable to inspect context page {page_path}: {exc}") from exc

    def _next_page_path(self) -> Path:
        if self.storage_path is None:
            raise ContextPagingError("Disk paging requested without a storage path")
        next_index = 1
        if self._page_files:
            stem = self._page_files[-1].stem.rsplit("_", 1)[-1]
            next_index = int(stem) + 1
        return self.storage_path / f"page_{next_index:06d}.jsonl"

    def _ensure_writable_page(self) -> Path:
        if not self._page_files or self._page_counts[-1] >= self.page_size:
            page_path = self._next_page_path()
            self._page_files.append(page_path)
            self._page_counts.append(0)
        return self._page_files[-1]

    def _append_disk_item(self, item: dict[str, Any]) -> None:
        page_path = self._ensure_writable_page()
        try:
            with page_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, sort_keys=True))
                handle.write("\n")
        except OSError as exc:
            raise ContextPagingError(f"Unable to persist context page {page_path}: {exc}") from exc

        self._page_counts[-1] += 1
        self._disk_item_count += 1
        if self._disk_item_count > self.max_items:
            self._trim_disk_items(self._disk_item_count - self.max_items)

    def _trim_disk_items(self, overflow: int) -> None:
        remaining_overflow = max(0, int(overflow))
        while remaining_overflow > 0 and self._page_files:
            oldest_path = self._page_files[0]
            oldest_count = self._page_counts[0]
            if oldest_count <= remaining_overflow:
                oldest_path.unlink(missing_ok=True)
                self._page_files.pop(0)
                self._page_counts.pop(0)
                self._disk_item_count -= oldest_count
                remaining_overflow -= oldest_count
                continue

            page_items = self._read_page(oldest_path)
            retained_items = page_items[remaining_overflow:]
            tmp_path = oldest_path.with_suffix(f"{oldest_path.suffix}.tmp")
            try:
                with tmp_path.open("w", encoding="utf-8") as handle:
                    for entry in retained_items:
                        handle.write(json.dumps(entry, sort_keys=True))
                        handle.write("\n")
                os.replace(tmp_path, oldest_path)
            except OSError as exc:
                raise ContextPagingError(f"Unable to trim context page {oldest_path}: {exc}") from exc
            finally:
                tmp_path.unlink(missing_ok=True)

            self._page_counts[0] = len(retained_items)
            self._disk_item_count -= remaining_overflow
            remaining_overflow = 0

    def _read_page(self, page_path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        try:
            with page_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    records.append(json.loads(stripped))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContextPagingError(f"Unable to read context page {page_path}: {exc}") from exc
        return records
