"""Zero-loss checkpoint compression utilities for Phase 3 artifacts."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

COMPRESSION_SCHEMA_VERSION = 1
DEFAULT_ARTIFACT_SUFFIX = ".ygbcmp"
DEFAULT_ZSTD_LEVEL = 3
DEFAULT_GZIP_LEVEL = 6
KIND_FILE = "file"
KIND_DIRECTORY = "directory"
PAYLOAD_FORMAT_RAW = "raw"
PAYLOAD_FORMAT_TAR = "tar"
SUPPORTED_ALGORITHMS = {"auto", "zstd", "gzip"}


class CompressionError(RuntimeError):
    """Base error for compression engine failures."""


class CompressionDependencyError(CompressionError):
    """Raised when a required optional dependency is unavailable."""


class CompressionVerificationError(CompressionError):
    """Raised when compressed or decompressed bytes fail verification."""


@dataclass(frozen=True)
class CompressionManifestEntry:
    """Verification metadata for a single file within an artifact."""

    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CompressionResult:
    """Result returned after a successful compression operation."""

    source_path: Path
    artifact_path: Path
    metadata_path: Path
    kind: str
    algorithm: str
    compression_level: int
    original_size: int
    compressed_size: int
    compression_ratio: float
    fallback_reason: str | None
    entries: tuple[CompressionManifestEntry, ...]
    directories: tuple[str, ...]


@dataclass(frozen=True)
class DecompressionResult:
    """Result returned after a successful decompression operation."""

    artifact_path: Path
    metadata_path: Path
    output_path: Path
    kind: str
    algorithm: str
    restored_size: int
    entries: tuple[CompressionManifestEntry, ...]
    directories: tuple[str, ...]


def compress_checkpoint(
    source_path: str | Path,
    output_path: str | Path | None = None,
    *,
    algorithm: str = "auto",
    compression_level: int | None = None,
) -> CompressionResult:
    """Compress a checkpoint file or checkpoint directory without loss."""

    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Compression source not found: {source}")

    if source.is_dir():
        kind = KIND_DIRECTORY
        entries, directories = _collect_directory_manifest(source)
        payload = _build_directory_payload(source)
        original_size = sum(entry.size_bytes for entry in entries)
        payload_format = PAYLOAD_FORMAT_TAR
    else:
        kind = KIND_FILE
        payload = source.read_bytes()
        entries = [
            CompressionManifestEntry(
                relative_path=source.name,
                size_bytes=len(payload),
                sha256=_hash_bytes(payload),
            )
        ]
        directories = []
        original_size = len(payload)
        payload_format = PAYLOAD_FORMAT_RAW

    compressed_payload, resolved_algorithm, resolved_level, fallback_reason = _compress_payload(
        payload,
        algorithm=algorithm,
        compression_level=compression_level,
    )
    artifact_path = _resolve_artifact_path(source, output_path)
    metadata_path = _metadata_path_for_artifact(artifact_path)
    compressed_size = len(compressed_payload)
    compression_ratio = (
        float(original_size) / float(compressed_size)
        if compressed_size > 0
        else float("inf")
    )

    metadata = {
        "schema_version": COMPRESSION_SCHEMA_VERSION,
        "kind": kind,
        "algorithm": resolved_algorithm,
        "compression_level": resolved_level,
        "created_at": _timestamp_now(),
        "source_name": source.name,
        "payload_format": payload_format,
        "original_size": original_size,
        "compressed_size": compressed_size,
        "compression_ratio": compression_ratio,
        "artifact_sha256": _hash_bytes(compressed_payload),
        "fallback_reason": fallback_reason,
        "directories": directories,
        "entries": [asdict(entry) for entry in entries],
    }

    _atomic_write_bytes(artifact_path, compressed_payload)
    _atomic_write_json(metadata_path, metadata)

    return CompressionResult(
        source_path=source,
        artifact_path=artifact_path,
        metadata_path=metadata_path,
        kind=kind,
        algorithm=resolved_algorithm,
        compression_level=resolved_level,
        original_size=original_size,
        compressed_size=compressed_size,
        compression_ratio=compression_ratio,
        fallback_reason=fallback_reason,
        entries=tuple(entries),
        directories=tuple(directories),
    )


def compress_directory(
    source_path: str | Path,
    output_path: str | Path | None = None,
    *,
    algorithm: str = "auto",
    compression_level: int | None = None,
) -> CompressionResult:
    """Explicit directory wrapper around [`compress_checkpoint()`](backend/training/compression_engine.py:73)."""

    source = Path(source_path)
    if not source.is_dir():
        raise NotADirectoryError(f"Expected directory source, got: {source}")
    return compress_checkpoint(
        source,
        output_path,
        algorithm=algorithm,
        compression_level=compression_level,
    )


def decompress_checkpoint(
    artifact_path: str | Path,
    output_path: str | Path | None = None,
    *,
    metadata_path: str | Path | None = None,
    verify: bool = True,
) -> DecompressionResult:
    """Decompress a Phase 3 artifact and verify exact byte restoration."""

    artifact = Path(artifact_path)
    if not artifact.exists():
        raise FileNotFoundError(f"Compressed artifact not found: {artifact}")

    resolved_metadata_path = (
        Path(metadata_path)
        if metadata_path is not None
        else _metadata_path_for_artifact(artifact)
    )
    metadata = load_compression_metadata(resolved_metadata_path)
    kind = str(metadata.get("kind", "")).strip().lower()
    algorithm = str(metadata.get("algorithm", "")).strip().lower()
    source_name = str(metadata.get("source_name", "")).strip()
    payload_format = str(metadata.get("payload_format", "")).strip().lower()
    directories = tuple(str(item) for item in metadata.get("directories", []))
    entries = tuple(_coerce_manifest_entry(item) for item in metadata.get("entries", []))

    if kind not in {KIND_FILE, KIND_DIRECTORY}:
        raise CompressionError(f"Unsupported artifact kind in metadata: {kind!r}")
    if not source_name:
        raise CompressionError("Compression metadata is missing source_name")
    if kind == KIND_FILE and len(entries) != 1:
        raise CompressionError("File artifacts must contain exactly one manifest entry")

    compressed_payload = artifact.read_bytes()
    if verify:
        expected_artifact_sha = str(metadata.get("artifact_sha256", "")).strip()
        if expected_artifact_sha and _hash_bytes(compressed_payload) != expected_artifact_sha:
            raise CompressionVerificationError(
                f"Compressed artifact hash mismatch for {artifact}"
            )

    payload = _decompress_payload(compressed_payload, algorithm=algorithm)

    if kind == KIND_FILE:
        destination = _resolve_file_output_path(
            artifact=artifact,
            source_name=source_name,
            output_path=output_path,
        )
        _atomic_write_bytes(destination, payload)
        if verify:
            _verify_file_payload(payload, entries[0], destination)
        restored_size = len(payload)
        return DecompressionResult(
            artifact_path=artifact,
            metadata_path=resolved_metadata_path,
            output_path=destination,
            kind=kind,
            algorithm=algorithm,
            restored_size=restored_size,
            entries=entries,
            directories=directories,
        )

    if payload_format != PAYLOAD_FORMAT_TAR:
        raise CompressionError(
            f"Unsupported directory payload format in metadata: {payload_format!r}"
        )

    destination_dir = _resolve_directory_output_path(
        artifact=artifact,
        source_name=source_name,
        output_path=output_path,
    )
    _extract_directory_payload(payload, destination_dir)
    if verify:
        _verify_directory_contents(destination_dir, entries)
    restored_size = sum(entry.size_bytes for entry in entries)
    return DecompressionResult(
        artifact_path=artifact,
        metadata_path=resolved_metadata_path,
        output_path=destination_dir,
        kind=kind,
        algorithm=algorithm,
        restored_size=restored_size,
        entries=entries,
        directories=directories,
    )


def load_compression_metadata(metadata_path: str | Path) -> dict[str, Any]:
    """Load and validate persisted compression metadata."""

    path = Path(metadata_path)
    if not path.exists():
        raise FileNotFoundError(f"Compression metadata not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CompressionError(
            f"Compression metadata must decode to an object, got {type(payload).__name__}"
        )
    schema_version = int(payload.get("schema_version", 0))
    if schema_version != COMPRESSION_SCHEMA_VERSION:
        raise CompressionError(
            f"Unsupported compression schema version: {schema_version}"
        )
    return payload


def _get_zstd_module() -> Any | None:
    try:
        import zstandard as zstd

        return zstd
    except ImportError:
        return None


def _compress_payload(
    payload: bytes,
    *,
    algorithm: str,
    compression_level: int | None,
) -> tuple[bytes, str, int, str | None]:
    normalized_algorithm = str(algorithm or "auto").strip().lower()
    if normalized_algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(
            f"algorithm must be one of {sorted(SUPPORTED_ALGORITHMS)}, got {algorithm!r}"
        )

    zstd = _get_zstd_module() if normalized_algorithm in {"auto", "zstd"} else None
    if zstd is not None:
        level = _coerce_level(compression_level, default=DEFAULT_ZSTD_LEVEL)
        compressor = zstd.ZstdCompressor(level=level)
        return compressor.compress(payload), "zstd", level, None

    fallback_reason: str | None = None
    if normalized_algorithm == "zstd":
        fallback_reason = "zstandard is unavailable; falling back to gzip"
        logger.warning(fallback_reason)

    level = _coerce_level(compression_level, default=DEFAULT_GZIP_LEVEL)
    return _gzip_compress(payload, level=level), "gzip", level, fallback_reason


def _decompress_payload(payload: bytes, *, algorithm: str) -> bytes:
    if algorithm == "zstd":
        zstd = _get_zstd_module()
        if zstd is None:
            raise CompressionDependencyError(
                "Artifact requires zstandard for decompression, but the dependency is unavailable"
            )
        return zstd.ZstdDecompressor().decompress(payload)
    if algorithm == "gzip":
        return gzip.decompress(payload)
    raise CompressionError(f"Unsupported compression algorithm in metadata: {algorithm!r}")


def _build_directory_payload(source_dir: Path) -> bytes:
    temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".tar")
    temp_handle.close()
    temp_path = Path(temp_handle.name)
    try:
        with tarfile.open(temp_path, mode="w") as archive:
            for path in sorted(source_dir.rglob("*"), key=lambda item: item.relative_to(source_dir).as_posix()):
                archive.add(
                    path,
                    arcname=path.relative_to(source_dir).as_posix(),
                    recursive=False,
                )
        return temp_path.read_bytes()
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _extract_directory_payload(payload: bytes, destination_dir: Path) -> None:
    if destination_dir.exists() and not destination_dir.is_dir():
        raise NotADirectoryError(f"Directory restore target is a file: {destination_dir}")
    if destination_dir.exists() and any(destination_dir.iterdir()):
        raise FileExistsError(
            f"Refusing to restore directory into non-empty path: {destination_dir}"
        )
    destination_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            member_path = _safe_member_destination(destination_dir, member.name)
            if member.isdir():
                member_path.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isreg():
                raise CompressionError(
                    f"Unsupported tar member type during restore: {member.name}"
                )
            extracted = archive.extractfile(member)
            if extracted is None:
                raise CompressionError(f"Failed to extract tar member: {member.name}")
            member_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(member_path, extracted.read())


def _collect_directory_manifest(
    source_dir: Path,
) -> tuple[list[CompressionManifestEntry], list[str]]:
    entries: list[CompressionManifestEntry] = []
    directories: list[str] = []
    for path in sorted(source_dir.rglob("*"), key=lambda item: item.relative_to(source_dir).as_posix()):
        relative_path = path.relative_to(source_dir).as_posix()
        if path.is_dir():
            directories.append(relative_path)
            continue
        payload = path.read_bytes()
        entries.append(
            CompressionManifestEntry(
                relative_path=relative_path,
                size_bytes=len(payload),
                sha256=_hash_bytes(payload),
            )
        )
    return entries, directories


def _coerce_manifest_entry(value: Any) -> CompressionManifestEntry:
    if not isinstance(value, dict):
        raise CompressionError(
            f"Compression manifest entry must be an object, got {type(value).__name__}"
        )
    relative_path = str(value.get("relative_path", "")).strip()
    if not relative_path:
        raise CompressionError("Compression manifest entry is missing relative_path")
    try:
        size_bytes = int(value.get("size_bytes", -1))
    except (TypeError, ValueError) as exc:
        raise CompressionError(
            f"Invalid size_bytes for manifest entry {relative_path!r}"
        ) from exc
    sha256 = str(value.get("sha256", "")).strip().lower()
    if size_bytes < 0 or len(sha256) != 64:
        raise CompressionError(
            f"Invalid verification metadata for manifest entry {relative_path!r}"
        )
    return CompressionManifestEntry(
        relative_path=relative_path,
        size_bytes=size_bytes,
        sha256=sha256,
    )


def _verify_file_payload(
    payload: bytes,
    entry: CompressionManifestEntry,
    destination: Path,
) -> None:
    if len(payload) != entry.size_bytes:
        raise CompressionVerificationError(
            f"Size mismatch after restore for {destination}: expected {entry.size_bytes}, got {len(payload)}"
        )
    payload_hash = _hash_bytes(payload)
    if payload_hash != entry.sha256:
        raise CompressionVerificationError(
            f"Hash mismatch after restore for {destination}: expected {entry.sha256}, got {payload_hash}"
        )


def _verify_directory_contents(
    destination_dir: Path,
    entries: tuple[CompressionManifestEntry, ...],
) -> None:
    for entry in entries:
        file_path = destination_dir / Path(entry.relative_path)
        if not file_path.exists():
            raise CompressionVerificationError(
                f"Missing restored file after directory decompression: {file_path}"
            )
        payload = file_path.read_bytes()
        if len(payload) != entry.size_bytes:
            raise CompressionVerificationError(
                f"Size mismatch for restored file {file_path}: expected {entry.size_bytes}, got {len(payload)}"
            )
        payload_hash = _hash_bytes(payload)
        if payload_hash != entry.sha256:
            raise CompressionVerificationError(
                f"Hash mismatch for restored file {file_path}: expected {entry.sha256}, got {payload_hash}"
            )


def _resolve_artifact_path(source: Path, output_path: str | Path | None) -> Path:
    if output_path is None:
        return source.parent / f"{source.name}{DEFAULT_ARTIFACT_SUFFIX}"
    return Path(output_path)


def _resolve_file_output_path(
    *,
    artifact: Path,
    source_name: str,
    output_path: str | Path | None,
) -> Path:
    if output_path is None:
        return artifact.parent / source_name
    resolved = Path(output_path)
    if resolved.exists() and resolved.is_dir():
        return resolved / source_name
    return resolved


def _resolve_directory_output_path(
    *,
    artifact: Path,
    source_name: str,
    output_path: str | Path | None,
) -> Path:
    if output_path is None:
        return artifact.parent / source_name
    return Path(output_path)


def _safe_member_destination(root: Path, member_name: str) -> Path:
    candidate = (root / member_name).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise CompressionVerificationError(
            f"Unsafe archive member path detected: {member_name!r}"
        ) from exc
    return candidate


def _metadata_path_for_artifact(artifact_path: Path) -> Path:
    return artifact_path.with_suffix(f"{artifact_path.suffix}.json")


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(temp_path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _gzip_compress(payload: bytes, *, level: int) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=level, mtime=0) as handle:
        handle.write(payload)
    return buffer.getvalue()


def _coerce_level(value: int | None, *, default: int) -> int:
    if value is None:
        return default
    level = int(value)
    if level < 1:
        raise ValueError(f"compression_level must be >= 1, got {level}")
    return level


def _timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "COMPRESSION_SCHEMA_VERSION",
    "CompressionDependencyError",
    "CompressionError",
    "CompressionManifestEntry",
    "CompressionResult",
    "CompressionVerificationError",
    "DecompressionResult",
    "compress_checkpoint",
    "compress_directory",
    "decompress_checkpoint",
    "load_compression_metadata",
]
