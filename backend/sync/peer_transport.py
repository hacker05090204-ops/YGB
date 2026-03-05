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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("ygb.sync.peer")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", "D:\\"))
SYNC_META = SYNC_ROOT / "ygb_sync"
MANIFEST_PATH = SYNC_META / "manifest.json"
PEER_STATE = SYNC_META / "peer_state"
DEVICE_ID = os.getenv("YGB_DEVICE_ID", "laptop_a")

# Peer format: "name:ip:port" — e.g. "laptop_b:100.64.0.2:8000"
_PEER_NODES_RAW = os.getenv("YGB_PEER_NODES", "")


def _parse_peers() -> List[Dict[str, str]]:
    """Parse peer nodes from env var."""
    if not _PEER_NODES_RAW:
        return []
    peers = []
    for entry in _PEER_NODES_RAW.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 3:
            peers.append({
                "name": parts[0],
                "ip": parts[1],
                "port": parts[2],
                "url": f"http://{parts[1]}:{parts[2]}",
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
    return peers


def check_peer_health(peer_url: str, timeout: float = 2.0) -> str:
    """Check if a peer is reachable. Returns 'ONLINE', 'OFFLINE', or 'ERROR'."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{peer_url}/health",
            headers={"User-Agent": "YGB-Sync"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return "ONLINE"
        return "ERROR"
    except Exception:
        return "OFFLINE"


def fetch_peer_manifest(peer_url: str, timeout: float = 5.0) -> Optional[dict]:
    """Fetch a peer's sync manifest."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{peer_url}/sync/manifest",
            headers={
                "User-Agent": "YGB-Sync",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception as e:
        logger.debug("Failed to fetch manifest from %s: %s", peer_url, e)
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
    online_peers = [p for p in peers if p.get("status") == "ONLINE"]
    if not online_peers:
        logger.warning("No online peers for parallel download")
        return {}

    results: Dict[str, bytes] = {}
    worker_count = min(max_workers, len(online_peers), len(chunk_hashes))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for i, ch in enumerate(chunk_hashes):
            peer = online_peers[i % len(online_peers)]
            future = executor.submit(
                fetch_chunk_from_peer, peer["url"], ch,
            )
            futures[future] = (ch, peer["name"])

        for future in as_completed(futures):
            ch, peer_name = futures[future]
            try:
                data = future.result()
                if data:
                    results[ch] = data
                    logger.debug("Downloaded chunk %s from %s", ch[:12], peer_name)
                else:
                    logger.warning("Empty chunk %s from %s", ch[:12], peer_name)
            except Exception as e:
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
        except Exception:
            pass
    return None


def discover_online_peers() -> List[Dict]:
    """Discover which peers are currently online."""
    peers = _parse_peers()
    online = []
    for peer in peers:
        status = check_peer_health(peer["url"], timeout=2.0)
        peer["status"] = status
        if status == "ONLINE":
            online.append(peer)
    logger.info("Peer discovery: %d/%d online", len(online), len(peers))
    return online
