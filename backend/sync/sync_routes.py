"""YGB sync routes for legacy chunk sync and /api/sync file sync."""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from backend.auth.auth_guard import require_auth
from backend.sync.chunker import get_chunk, has_chunk, store_chunk
from backend.sync.health import get_sync_health, should_alert
from backend.sync.manifest import load_manifest
from backend.sync.peer_transport import DEVICE_ID, MANIFEST_PATH, get_peers, save_peer_manifest
from backend.sync.sync_engine import (
    SyncMode,
    get_last_sync_cycle,
    get_local_sync_index,
    get_sync_mode,
    is_sync_stale,
    sync_status_message,
)
from backend.sync.tailscale_sync import TailscaleSyncEngine

logger = logging.getLogger("ygb.sync.routes")

sync_router = APIRouter(tags=["sync"], dependencies=[Depends(require_auth)])
api_sync_router = APIRouter(tags=["sync-api"])


@sync_router.get("/manifest")
async def legacy_manifest() -> dict:
    """Return the legacy chunk manifest for existing sync consumers."""
    manifest = load_manifest(MANIFEST_PATH)
    return {
        "device_id": manifest.device_id,
        "vector_clock": manifest.vector_clock,
        "files": manifest.files,
        "last_sync": manifest.last_sync,
        "version": manifest.version,
    }


@sync_router.get("/chunk/{chunk_hash}")
async def serve_chunk(chunk_hash: str) -> Response:
    """Serve a legacy chunk by hash."""
    data = get_chunk(chunk_hash)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_hash[:16]} not found")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-Chunk-Hash": chunk_hash,
            "X-Chunk-Size": str(len(data)),
        },
    )


@sync_router.get("/chunk/{chunk_hash}/exists")
async def check_chunk(chunk_hash: str) -> dict:
    """Check whether a legacy chunk exists locally."""
    return {"exists": has_chunk(chunk_hash), "chunk_hash": chunk_hash}


@sync_router.post("/push_manifest")
async def receive_manifest(request: Request) -> dict:
    """Receive and cache a peer's legacy manifest."""
    try:
        data = await request.json()
        peer_id = data.get("device_id", "unknown")
        save_peer_manifest(peer_id, data)
        logger.info("Received manifest from peer %s (%d files)", peer_id, len(data.get("files", {})))
        return {"status": "ok", "peer_id": peer_id}
    except Exception as exc:
        logger.error("Failed to process peer manifest: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@sync_router.post("/push_chunk")
async def receive_chunk(request: Request) -> dict:
    """Receive a legacy chunk from a peer."""
    chunk_hash = request.headers.get("X-Chunk-Hash", "")
    if not chunk_hash:
        raise HTTPException(status_code=400, detail="Missing X-Chunk-Hash header")
    data = await request.body()
    if not store_chunk(chunk_hash, data):
        raise HTTPException(status_code=400, detail="Chunk integrity verification failed")
    return {"status": "ok", "chunk_hash": chunk_hash, "size": len(data)}


@sync_router.get("/status")
async def sync_status() -> dict:
    """Comprehensive sync status for the legacy dashboard."""
    health = get_sync_health()
    mode = get_sync_mode()
    index = get_local_sync_index()
    last_cycle = get_last_sync_cycle()
    local_files = index.get_file_count()
    local_bytes = index.get_total_bytes()
    last_completed_at = (
        last_cycle.completed_at if last_cycle is not None else str(health.get("last_sync") or "")
    )
    stale = is_sync_stale(mode=mode, last_completed_at=last_completed_at)
    message = sync_status_message(
        mode,
        peers_attempted=last_cycle.peers_attempted if last_cycle is not None else 0,
        peers_succeeded=last_cycle.peers_succeeded if last_cycle is not None else 0,
    )
    if mode == SyncMode.STANDALONE:
        health["status"] = "HEALTHY"
    elif mode == SyncMode.DEGRADED:
        health["status"] = "DEGRADED"
    health["mode"] = mode.value
    health["local_files"] = local_files
    health["local_bytes"] = local_bytes
    health["message"] = message
    health["stale"] = stale
    health["alerts"] = should_alert(health)
    return health


@sync_router.get("/peers")
async def peer_status() -> dict:
    """List known peers and their connectivity status."""
    peers = get_peers()
    return {
        "device_id": DEVICE_ID,
        "peers": peers,
        "total": len(peers),
        "online": sum(1 for peer in peers if peer.get("status") == "ONLINE"),
    }


@sync_router.post("/trigger_sync")
async def trigger_sync() -> dict:
    """Manually trigger the legacy sync cycle."""
    try:
        from backend.sync.sync_engine import sync_cycle

        result = sync_cycle()
        return {"status": "ok", "result": result}
    except Exception as exc:
        logger.error("Manual sync trigger failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@sync_router.post("/trigger_recovery")
async def trigger_recovery(request: Request) -> dict:
    """Trigger legacy recovery from peers or cloud."""
    try:
        body = await request.json()
        source = body.get("source", "auto")
        from backend.sync.recovery import full_recovery

        result = full_recovery(source=source)
        return {"status": "ok", "result": result}
    except Exception as exc:
        logger.error("Recovery trigger failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_sync_router.get("/manifest")
async def api_manifest() -> dict:
    """Return a simple {relative_path: sha256} manifest for file sync."""
    return TailscaleSyncEngine().build_manifest()


@api_sync_router.post("/receive")
async def api_receive(request: Request) -> dict:
    """Receive a syncable file as JSON with a base64 payload."""
    try:
        body = await request.json()
        relative_path = str(body.get("path", "")).strip()
        expected_sha256 = str(body.get("sha256", "")).strip()
        content_b64 = str(body.get("content_b64", "")).strip()
        if not relative_path or not expected_sha256 or not content_b64:
            raise HTTPException(status_code=400, detail="path, sha256, and content_b64 are required")
        content = base64.b64decode(content_b64)
        actual_sha256 = TailscaleSyncEngine().write_received_file(relative_path, content, expected_sha256)
        return {
            "status": "ok",
            "path": relative_path,
            "sha256": actual_sha256,
            "size": len(content),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_sync_router.get("/file")
async def api_file(path: str = Query(..., min_length=1)) -> Response:
    """Serve a syncable file by relative path."""
    try:
        content = TailscaleSyncEngine().read_sync_file(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


@api_sync_router.get("/status")
async def api_status() -> dict:
    """Return the latest file-sync status snapshot."""
    return TailscaleSyncEngine().get_status()
