"""
YGB Peer Transport — Chunk-level file transfer between mesh devices.

Uses FastAPI endpoints for serving chunks and HTTP requests for fetching.
All transfers happen over the WireGuard/Tailscale encrypted mesh.

Endpoints added to the main YGB server:
  GET  /sync/manifest       → Return this device's manifest
  GET  /sync/chunk/{hash}   → Return a specific chunk by hash
  POST /sync/push_manifest  → Receive a peer's manifest update
  POST /sync/push_chunk     → Receive a chunk from a peer
  GET  /sync/peers          → List known peers and their status
"""

import json
import logging
import os
import asyncio
import threading
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from config.storage_config import SYNC_ROOT as DEFAULT_SYNC_ROOT

logger = logging.getLogger("ygb.sync.peer")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


SYNC_ROOT = Path(_get_env("YGB_SYNC_ROOT", str(DEFAULT_SYNC_ROOT)))
SYNC_META = SYNC_ROOT / "ygb_sync"
MANIFEST_PATH = SYNC_META / "manifest.json"
PEER_STATE = SYNC_META / "peer_state"
DEVICE_ID = _get_env("YGB_DEVICE_ID", "laptop_a")
PEER_RETRY_BUDGET = max(1, int(_get_env("YGB_PEER_RETRY_BUDGET", "3")))
PEER_BACKOFF_BASE_SECONDS = max(
    0.0,
    float(_get_env("YGB_PEER_BACKOFF_BASE_SECONDS", "1")),
)
PEER_BACKOFF_MAX_SECONDS = max(
    PEER_BACKOFF_BASE_SECONDS,
    float(_get_env("YGB_PEER_BACKOFF_MAX_SECONDS", "4")),
)
_PEER_STATUSES: dict[str, "PeerStatus"] = {}


class PeerStatus(Enum):
    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    DEGRADED = "DEGRADED"


def _set_peer_status(peer_name: str, status: "PeerStatus") -> None:
    _PEER_STATUSES[peer_name] = status


def get_peer_statuses() -> dict[str, "PeerStatus"]:
    return dict(_PEER_STATUSES)


async def _async_backoff_sleep(delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)


def _run_async_backoff_sleep(delay_seconds: float) -> None:
    if delay_seconds <= 0:
        return
    try:
        asyncio.run(_async_backoff_sleep(delay_seconds))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_async_backoff_sleep(delay_seconds))
        finally:
            loop.close()


def _peer_status_from_health(health_status: str) -> "PeerStatus":
    if health_status == "ONLINE":
        return PeerStatus.REACHABLE
    if health_status == "ERROR":
        return PeerStatus.DEGRADED
    return PeerStatus.UNREACHABLE


def _parse_peers() -> List[Dict[str, str]]:
    """Parse peer nodes from env var."""
    peer_nodes_raw = _get_env("YGB_PEER_NODES", "")
    if not peer_nodes_raw:
        return []
    peers = []
    for entry in peer_nodes_raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 3:
            scheme = "https" if parts[2] == "8443" else "http"
            peers.append({
                "name": parts[0],
                "ip": parts[1],
                "port": parts[2],
                "url": f"{scheme}://{parts[1]}:{parts[2]}",
            })
        elif len(parts) == 2:
            peers.append({
                "name": parts[0],
                "ip": parts[1],
                "port": "8000",
                "url": f"http://{parts[1]}:8000",
            })
    return peers


def get_peers() -> List[Dict]:
    """Get configured peers with connectivity status."""
    peers = _parse_peers()
    for peer in peers:
        peer["status"] = check_peer_health(peer["url"])
        peer_status = _peer_status_from_health(peer["status"])
        peer["peer_status"] = peer_status.value
        _set_peer_status(peer["name"], peer_status)
    return peers


def check_peer_health(peer_url: str, timeout: float = 2.0) -> str:
    """Check if a peer is reachable. Returns 'ONLINE', 'OFFLINE', or 'ERROR'."""
    try:
        import urllib.request
        for health_path in ("/api/health", "/health"):
            req = urllib.request.Request(
                f"{peer_url}{health_path}",
                headers={"User-Agent": "YGB-Sync"},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return "ONLINE"
            except Exception:
                continue
        return "ERROR"
    except Exception:
        return "OFFLINE"


def fetch_peer_manifest(peer_url: str, timeout: float = 5.0) -> Optional[dict]:
    """Fetch a peer's sync manifest."""
    try:
        import urllib.request
        for manifest_path in ("/api/sync/manifest", "/sync/manifest"):
            req = urllib.request.Request(
                f"{peer_url}{manifest_path}",
                headers={
                    "User-Agent": "YGB-Sync",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data
            except Exception:
                continue
    except Exception as e:
        logger.debug("Failed to fetch manifest from %s: %s", peer_url, e)
        return None
    return None


def fetch_chunk_from_peer(peer_url: str, chunk_hash: str, timeout: float = 30.0) -> Optional[bytes]:
    """Download a single chunk from a peer."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{peer_url}/sync/chunk/{chunk_hash}",
            headers={"User-Agent": "YGB-Sync"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        logger.debug("Failed to fetch chunk %s from %s: %s", chunk_hash[:12], peer_url, e)
        return None


def parallel_download_chunks(
    chunk_hashes: List[str],
    peers: List[Dict],
    max_workers: int = 4,
) -> Dict[str, bytes]:
    """
    Download multiple chunks from multiple peers in parallel.
    Round-robins chunks across available online peers.
    Returns {chunk_hash: data} for successfully downloaded chunks.
    """
    if not chunk_hashes:
        return {}

    online_peers = [p for p in peers if p.get("status") == "ONLINE"]
    if not online_peers:
        logger.warning("No online peers for parallel download")
        return {}

    results: Dict[str, bytes] = {}
    worker_count = min(max_workers, len(online_peers), len(chunk_hashes))
    retry_budget: dict[str, int] = {
        peer["name"]: PEER_RETRY_BUDGET for peer in online_peers
    }
    retry_budget_lock = threading.Lock()

    def _remaining_budget(peer_name: str) -> int:
        with retry_budget_lock:
            return retry_budget.get(peer_name, 0)

    def _consume_budget(peer_name: str) -> int:
        with retry_budget_lock:
            remaining = max(0, retry_budget.get(peer_name, 0) - 1)
            retry_budget[peer_name] = remaining
            return remaining

    def _update_status_from_budget(peer_name: str, remaining: int) -> None:
        if remaining <= 0:
            _set_peer_status(peer_name, PeerStatus.UNREACHABLE)
        else:
            _set_peer_status(peer_name, PeerStatus.DEGRADED)

    def _download_with_retry(peer: Dict[str, str], chunk_hash: str) -> Optional[bytes]:
        peer_name = peer["name"]
        for attempt in range(1, PEER_RETRY_BUDGET + 1):
            if _remaining_budget(peer_name) <= 0:
                _set_peer_status(peer_name, PeerStatus.UNREACHABLE)
                return None
            data = fetch_chunk_from_peer(peer["url"], chunk_hash)
            if data:
                _set_peer_status(peer_name, PeerStatus.REACHABLE)
                return data
            remaining = _consume_budget(peer_name)
            _update_status_from_budget(peer_name, remaining)
            if remaining <= 0 or attempt >= PEER_RETRY_BUDGET:
                break
            delay = min(
                PEER_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                PEER_BACKOFF_MAX_SECONDS,
            )
            _run_async_backoff_sleep(float(delay))
        return None

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for i, ch in enumerate(chunk_hashes):
            peer = online_peers[i % len(online_peers)]
            future = executor.submit(
                _download_with_retry, peer, ch,
            )
            futures[future] = (ch, peer["name"])

        for future in as_completed(futures):
            ch, peer_name = futures[future]
            try:
                data = future.result()
                if data:
                    results[ch] = data
                    _set_peer_status(peer_name, PeerStatus.REACHABLE)
                    logger.debug("Downloaded chunk %s from %s", ch[:12], peer_name)
                else:
                    logger.warning(
                        "Chunk %s unavailable from %s after retries (remaining budget=%d)",
                        ch[:12],
                        peer_name,
                        _remaining_budget(peer_name),
                    )
            except Exception as e:
                remaining = _consume_budget(peer_name)
                _update_status_from_budget(peer_name, remaining)
                logger.warning("Download failed chunk %s from %s: %s", ch[:12], peer_name, e)

    logger.info(
        "Parallel download: %d/%d chunks from %d peers",
        len(results), len(chunk_hashes), len(online_peers),
    )
    return results


def push_manifest_to_peer(peer_url: str, manifest_data: dict, timeout: float = 5.0) -> bool:
    """Push our manifest to a peer."""
    try:
        import urllib.request
        payload = json.dumps(manifest_data).encode("utf-8")
        req = urllib.request.Request(
            f"{peer_url}/sync/push_manifest",
            data=payload,
            headers={
                "User-Agent": "YGB-Sync",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug("Failed to push manifest to %s: %s", peer_url, e)
        return False


def save_peer_manifest(peer_name: str, manifest_data: dict):
    """Cache a peer's manifest locally."""
    PEER_STATE.mkdir(parents=True, exist_ok=True)
    path = PEER_STATE / f"{peer_name}.json"
    path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")


def load_peer_manifest(peer_name: str) -> Optional[dict]:
    """Load a cached peer manifest."""
    path = PEER_STATE / f"{peer_name}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "Failed to load cached peer manifest for %s: %s",
                peer_name,
                exc,
                exc_info=True,
            )
    return None


def discover_online_peers() -> List[Dict]:
    """Discover which peers are currently online."""
    peers = _parse_peers()
    online = []
    for peer in peers:
        status = check_peer_health(peer["url"], timeout=2.0)
        peer["status"] = status
        peer_status = _peer_status_from_health(status)
        peer["peer_status"] = peer_status.value
        _set_peer_status(peer["name"], peer_status)
        if status == "ONLINE":
            online.append(peer)
    logger.info("Peer discovery: %d/%d online", len(online), len(peers))
    return online
