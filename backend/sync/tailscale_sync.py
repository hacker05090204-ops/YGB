"""File-level Tailscale sync engine for YGB peer replication."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from backend.observability.metrics import metrics_registry

logger = logging.getLogger("ygb.sync.tailscale")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = PROJECT_ROOT / "data" / "sync_status.json"
SYNCABLE_PREFIXES = ("data/raw/", "checkpoints/")
_ENV_CACHE: dict[str, str] | None = None


def _load_local_env() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    env_path = PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    _ENV_CACHE = values
    return values


def _get_env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    return _load_local_env().get(name, default)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_relative_path(relative_path: str) -> Path:
    candidate = Path(relative_path.replace("\\", "/"))
    if candidate.is_absolute():
        raise ValueError(f"Absolute path not allowed: {relative_path}")
    parts = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"Parent traversal not allowed: {relative_path}")
        parts.append(part)
    normalized = Path(*parts)
    normalized_str = normalized.as_posix()
    if not any(normalized_str.startswith(prefix) for prefix in SYNCABLE_PREFIXES):
        raise ValueError(f"Path is not syncable: {relative_path}")
    return normalized


def _resolve_sync_root(raw_root: str) -> Path:
    explicit = Path(raw_root).expanduser() if raw_root else PROJECT_ROOT
    candidate = explicit.resolve()
    if (candidate / "data" / "raw").exists() or (candidate / "checkpoints").exists():
        return candidate
    return PROJECT_ROOT


def _iter_syncable_files(sync_root: Path) -> list[Path]:
    files: list[Path] = []
    for relative_dir in ("data/raw", "checkpoints"):
        root = sync_root / relative_dir
        if not root.exists():
            continue
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.endswith((".tmp", ".partial", ".lock")):
                continue
            files.append(file_path)
    return files


@dataclass(frozen=True)
class SyncResult:
    files_sent: int
    files_received: int
    bytes_sent: int
    bytes_received: int
    errors: int
    peer_id: str
    base_url: str


class TailscaleSyncEngine:
    """Sync data/raw and checkpoints between configured Tailscale peers."""

    def __init__(self) -> None:
        device_id = _get_env("YGB_DEVICE_ID", "").strip()
        self.device_id = device_id or socket.gethostname().lower()
        sync_root_value = _get_env("YGB_SYNC_ROOT", str(PROJECT_ROOT))
        self.sync_root = _resolve_sync_root(sync_root_value)
        self.peers = self._parse_peers(_get_env("YGB_PEER_NODES", ""))
        self.interval = int(_get_env("YGB_SYNC_INTERVAL_SEC", "300") or "300")
        chunk_size_mb = int(_get_env("YGB_CHUNK_SIZE_MB", "64") or "64")
        self.chunk_size = chunk_size_mb * 1024 * 1024
        self.status_path = STATUS_PATH

    @staticmethod
    def _parse_peers(raw: str) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        for part in raw.split(","):
            stripped = part.strip()
            if not stripped:
                continue
            pieces = stripped.split(":")
            if len(pieces) < 3:
                continue
            device_id, host, port = pieces[0], pieces[1], pieces[2]
            try:
                port_int = int(port)
            except ValueError:
                continue
            scheme = "https" if port_int == 8443 else "http"
            peers.append(
                {
                    "device_id": device_id,
                    "host": host,
                    "ip": host,
                    "port": port_int,
                    "scheme": scheme,
                }
            )
        return peers

    @staticmethod
    def _coerce_manifest(payload: Any) -> dict[str, str]:
        if isinstance(payload, dict) and isinstance(payload.get("files"), dict):
            payload = payload["files"]
        if not isinstance(payload, dict):
            return {}
        return {str(path): str(sha) for path, sha in payload.items()}

    @staticmethod
    def _base_url(peer: dict[str, Any]) -> str:
        return f"{peer['scheme']}://{peer['host']}:{peer['port']}"

    def build_manifest(self) -> dict[str, str]:
        manifest: dict[str, str] = {}
        for file_path in _iter_syncable_files(self.sync_root):
            relative_path = file_path.relative_to(self.sync_root).as_posix()
            manifest[relative_path] = _sha256_file(file_path)
        return manifest

    def read_sync_file(self, relative_path: str) -> bytes:
        normalized = _normalize_relative_path(relative_path)
        target = (self.sync_root / normalized).resolve()
        if not target.exists():
            raise FileNotFoundError(relative_path)
        return target.read_bytes()

    def write_received_file(self, relative_path: str, content: bytes, expected_sha256: str) -> str:
        actual_sha256 = _sha256_bytes(content)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"SHA256 mismatch for {relative_path}: expected {expected_sha256}, got {actual_sha256}"
            )
        normalized = _normalize_relative_path(relative_path)
        target = (self.sync_root / normalized).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(f"{target.suffix}.tmp")
        temp_path.write_bytes(content)
        os.replace(temp_path, target)
        return actual_sha256

    def get_status(self) -> dict[str, Any]:
        if self.status_path.exists():
            try:
                return json.loads(self.status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("sync_status_json_invalid", extra={"path": str(self.status_path)})
        return {
            "device_id": self.device_id,
            "sync_root": str(self.sync_root),
            "last_sync_time": "",
            "peers_connected": 0,
            "files_synced_last_cycle": 0,
            "files_sent": 0,
            "files_received": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "errors": 0,
            "peer_results": [],
            "peers_configured": self.peers,
        }

    async def _fetch_peer_manifest(
        self,
        peer: dict[str, Any],
        session: aiohttp.ClientSession,
    ) -> tuple[dict[str, str] | None, int]:
        base_url = self._base_url(peer)
        try:
            async with session.get(
                f"{base_url}/api/sync/manifest",
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "sync_peer_manifest_error",
                        extra={"peer": peer["device_id"], "status": response.status, "url": base_url},
                    )
                    return None, 1
                payload = await response.json()
                return self._coerce_manifest(payload), 0
        except Exception as exc:
            logger.warning(
                "sync_peer_manifest_exception",
                extra={"peer": peer["device_id"], "error": str(exc), "url": base_url},
            )
            return None, 1

    async def sync_with_peer(
        self,
        peer: dict[str, Any],
        session: aiohttp.ClientSession,
    ) -> SyncResult:
        base_url = self._base_url(peer)
        sent = 0
        received = 0
        bytes_sent = 0
        bytes_received = 0
        errors = 0

        peer_manifest, manifest_errors = await self._fetch_peer_manifest(peer, session)
        errors += manifest_errors
        if peer_manifest is None:
            return SyncResult(sent, received, bytes_sent, bytes_received, errors, peer["device_id"], base_url)

        local_manifest = self.build_manifest()

        for relative_path, local_sha256 in local_manifest.items():
            if peer_manifest.get(relative_path) == local_sha256:
                continue
            target = self.sync_root / relative_path
            if not target.exists():
                continue
            file_size = target.stat().st_size
            if file_size > self.chunk_size:
                logger.info(
                    "sync_skip_large_file",
                    extra={"peer": peer["device_id"], "path": relative_path, "size": file_size},
                )
                continue
            payload = {
                "path": relative_path,
                "sha256": local_sha256,
                "content_b64": base64.b64encode(target.read_bytes()).decode("ascii"),
            }
            try:
                async with session.post(
                    f"{base_url}/api/sync/receive",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60, connect=10),
                ) as response:
                    if response.status != 200:
                        errors += 1
                        continue
                    body = await response.json()
                    if body.get("sha256") != local_sha256:
                        errors += 1
                        continue
                    sent += 1
                    bytes_sent += file_size
            except Exception as exc:
                logger.warning(
                    "sync_push_exception",
                    extra={"peer": peer["device_id"], "path": relative_path, "error": str(exc)},
                )
                errors += 1

        for relative_path, peer_sha256 in peer_manifest.items():
            if not relative_path.startswith("data/raw/"):
                continue
            if local_manifest.get(relative_path) == peer_sha256:
                continue
            try:
                async with session.get(
                    f"{base_url}/api/sync/file",
                    params={"path": relative_path},
                    timeout=aiohttp.ClientTimeout(total=60, connect=10),
                ) as response:
                    if response.status != 200:
                        errors += 1
                        continue
                    content = await response.read()
                actual_sha256 = _sha256_bytes(content)
                if actual_sha256 != peer_sha256:
                    errors += 1
                    continue
                self.write_received_file(relative_path, content, peer_sha256)
                received += 1
                bytes_received += len(content)
            except Exception as exc:
                logger.warning(
                    "sync_pull_exception",
                    extra={"peer": peer["device_id"], "path": relative_path, "error": str(exc)},
                )
                errors += 1

        return SyncResult(sent, received, bytes_sent, bytes_received, errors, peer["device_id"], base_url)

    async def run_sync_cycle(self) -> dict[str, Any]:
        if not self.peers:
            payload = {
                "device_id": self.device_id,
                "sync_root": str(self.sync_root),
                "last_sync_time": _now_iso(),
                "peers_connected": 0,
                "files_synced_last_cycle": 0,
                "files_sent": 0,
                "files_received": 0,
                "bytes_sent": 0,
                "bytes_received": 0,
                "errors": 0,
                "peer_results": [],
                "peers_configured": self.peers,
                "warning": "No peers configured in YGB_PEER_NODES",
            }
            _atomic_write_json(self.status_path, payload)
            return payload

        peer_results: list[dict[str, Any]] = []
        files_sent = 0
        files_received = 0
        bytes_sent = 0
        bytes_received = 0
        errors = 0
        peers_connected = 0

        async with aiohttp.ClientSession() as session:
            for peer in self.peers:
                result = await self.sync_with_peer(peer, session)
                if result.errors == 0:
                    peers_connected += 1
                files_sent += result.files_sent
                files_received += result.files_received
                bytes_sent += result.bytes_sent
                bytes_received += result.bytes_received
                errors += result.errors
                peer_results.append(
                    {
                        "device_id": result.peer_id,
                        "base_url": result.base_url,
                        "files_sent": result.files_sent,
                        "files_received": result.files_received,
                        "bytes_sent": result.bytes_sent,
                        "bytes_received": result.bytes_received,
                        "errors": result.errors,
                    }
                )
                metrics_registry.increment("sync_files_sent", result.files_sent)
                metrics_registry.increment("sync_files_received", result.files_received)
                metrics_registry.increment("sync_errors", result.errors)

        payload = {
            "device_id": self.device_id,
            "sync_root": str(self.sync_root),
            "last_sync_time": _now_iso(),
            "peers_connected": peers_connected,
            "files_synced_last_cycle": files_sent + files_received,
            "files_sent": files_sent,
            "files_received": files_received,
            "bytes_sent": bytes_sent,
            "bytes_received": bytes_received,
            "errors": errors,
            "peer_results": peer_results,
            "peers_configured": self.peers,
        }
        _atomic_write_json(self.status_path, payload)
        return payload
