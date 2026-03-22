"""
YGB Sync API Routes — FastAPI endpoints for peer sync and health monitoring.

These endpoints are imported by the main server and added to the FastAPI app.
They handle:
  - Manifest exchange between peers
  - Chunk serving for parallel downloads
  - Sync health dashboard data
  - Recovery triggers

Usage in server.py:
    from backend.sync.sync_routes import sync_router
    app.include_router(sync_router, prefix="/sync")
"""

import json
import logging
from pathlib import Path

try:
    from fastapi import APIRouter, Depends, HTTPException, Request, Response
    from fastapi.responses import JSONResponse
except ImportError:
    # Stub for import safety when FastAPI not available
    pass

from backend.auth.auth_guard import require_auth
from backend.sync.manifest import load_manifest, DEVICE_ID
from backend.sync.chunker import get_chunk, has_chunk, store_chunk, CHUNK_CACHE
from backend.sync.health import get_sync_health, should_alert
from backend.sync.peer_transport import get_peers, save_peer_manifest, SYNC_META, MANIFEST_PATH

logger = logging.getLogger("ygb.sync.routes")

sync_router = APIRouter(tags=["sync"], dependencies=[Depends(require_auth)])


@sync_router.get("/manifest")
async def get_manifest():
    """Return this device's sync manifest for peer exchange."""
    manifest = load_manifest(MANIFEST_PATH)
    return {
        "device_id": manifest.device_id,
        "vector_clock": manifest.vector_clock,
        "files": manifest.files,
        "last_sync": manifest.last_sync,
        "version": manifest.version,
    }


@sync_router.get("/chunk/{chunk_hash}")
async def serve_chunk(chunk_hash: str):
    """Serve a chunk by its hash for peer download."""
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
async def check_chunk(chunk_hash: str):
    """Check if a chunk exists locally."""
    return {"exists": has_chunk(chunk_hash), "chunk_hash": chunk_hash}


@sync_router.post("/push_manifest")
async def receive_manifest(request: Request):
    """Receive a peer's manifest update."""
    try:
        data = await request.json()
        peer_id = data.get("device_id", "unknown")
        save_peer_manifest(peer_id, data)
        logger.info("Received manifest from peer %s (%d files)",
                     peer_id, len(data.get("files", {})))
        return {"status": "ok", "peer_id": peer_id}
    except Exception as e:
        logger.error("Failed to process peer manifest: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@sync_router.post("/push_chunk")
async def receive_chunk(request: Request):
    """Receive a chunk from a peer."""
    chunk_hash = request.headers.get("X-Chunk-Hash", "")
    if not chunk_hash:
        raise HTTPException(status_code=400, detail="Missing X-Chunk-Hash header")

    data = await request.body()
    if store_chunk(chunk_hash, data):
        return {"status": "ok", "chunk_hash": chunk_hash, "size": len(data)}
    else:
        raise HTTPException(status_code=400, detail="Chunk integrity verification failed")


@sync_router.get("/status")
async def sync_status():
    """Comprehensive sync status for the dashboard."""
    health = get_sync_health()
    alerts = should_alert(health)
    health["alerts"] = alerts
    return health


@sync_router.get("/peers")
async def peer_status():
    """List known peers and their connectivity status."""
    peers = get_peers()
    return {
        "device_id": DEVICE_ID,
        "peers": peers,
        "total": len(peers),
        "online": sum(1 for p in peers if p.get("status") == "ONLINE"),
    }


@sync_router.post("/trigger_sync")
async def trigger_sync():
    """Manually trigger a sync cycle."""
    try:
        from backend.sync.sync_engine import sync_cycle
        result = sync_cycle()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Manual sync trigger failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@sync_router.post("/trigger_recovery")
async def trigger_recovery(request: Request):
    """Trigger recovery from peers or cloud."""
    try:
        body = await request.json()
        source = body.get("source", "auto")  # 'auto', 'peers', 'cloud'

        from backend.sync.recovery import full_recovery
        result = full_recovery(source=source)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Recovery trigger failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
