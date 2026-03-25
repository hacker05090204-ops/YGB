"""Telemetry and health check endpoints for YGB API."""

import asyncio
from datetime import datetime, UTC
from typing import Dict, Any, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .base import get_project_root, serialize_strategy

# Create router
router = APIRouter(prefix="/api", tags=["telemetry"])


# Discovery functions (would be imported from main app in production)
def discover_python_phases() -> List[Dict[str, Any]]:
    """Discover available Python phases."""
    import sys
    from pathlib import Path

    project_root = get_project_root()
    phases = []

    # Phases 01-19 in python/
    python_dir = project_root / "python"
    if python_dir.exists():
        for item in python_dir.iterdir():
            if item.is_dir() and item.name.startswith("phase"):
                try:
                    num = int(item.name.replace("phase", "").split("_")[0])
                    phases.append(
                        {
                            "name": item.name,
                            "number": num,
                            "path": str(item),
                            "available": True,
                            "description": f"Phase {num:02d} - {item.name.split('_', 1)[-1].replace('_', ' ').title()}",
                        }
                    )
                except ValueError:
                    pass

    # Phases 20-49 in impl_v1/
    impl_dir = project_root / "impl_v1"
    if impl_dir.exists():
        for item in impl_dir.iterdir():
            if item.is_dir() and item.name.startswith("phase"):
                try:
                    num = int(item.name.replace("phase", ""))
                    phases.append(
                        {
                            "name": item.name,
                            "number": num,
                            "path": str(item),
                            "available": True,
                            "description": f"Phase {num:02d} - Implementation Layer",
                        }
                    )
                except ValueError:
                    pass

    return sorted(phases, key=lambda x: x["number"])


def discover_hunter_modules() -> Dict[str, bool]:
    """Discover available HUMANOID_HUNTER modules."""
    import sys
    from pathlib import Path

    project_root = get_project_root()
    modules = {}
    hunter_dir = project_root / "HUMANOID_HUNTER"

    if hunter_dir.exists():
        for item in hunter_dir.iterdir():
            if (
                item.is_dir()
                and not item.name.startswith("_")
                and not item.name.startswith(".")
            ):
                modules[item.name] = True

    return modules


def get_g38_status() -> Dict[str, Any]:
    """Get G38 training status."""
    # This would import from main app in production
    return {
        "available": False,
        "training_active": False,
        "models_trained": 0,
        "error": "G38 runtime not initialized",
    }


def get_cache_headers(max_age: int = 5, immutable: bool = False) -> Dict[str, str]:
    """Generate cache control headers."""
    cache_control = f"public, max-age={max_age}"
    if immutable:
        cache_control += ", immutable"

    return {
        "Cache-Control": cache_control,
        "X-Request-Time": datetime.now(UTC).isoformat(),
    }


@router.get("/health")
async def health_check():
    """Health check endpoint with system status."""
    try:
        phases, hunter_modules = await asyncio.gather(
            asyncio.to_thread(discover_python_phases),
            asyncio.to_thread(discover_hunter_modules),
        )

        return JSONResponse(
            content={
                "status": "ok",
                "ygb_root": str(get_project_root()),
                "python_phases": len([p for p in phases if p["number"] <= 19]),
                "impl_phases": len([p for p in phases if p["number"] >= 20]),
                "hunter_modules": len(hunter_modules),
                "hunter_integration": hunter_modules,
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "1.0.0",
            },
            headers=get_cache_headers(max_age=15),
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            },
            status_code=500,
            headers=get_cache_headers(max_age=5),
        )


@router.get("/bounty/phases")
async def get_bounty_phases():
    """Get all available bounty phases."""
    try:
        phases = await asyncio.to_thread(discover_python_phases)
        return JSONResponse(
            content={
                p["name"]: {
                    "number": p["number"],
                    "available": p["available"],
                    "description": p["description"],
                }
                for p in phases
            },
            headers=get_cache_headers(max_age=3600, immutable=True),
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
            headers=get_cache_headers(max_age=5),
        )


@router.get("/orchestrator/status")
async def get_orchestrator_status():
    """Expose orchestrator telemetry, queue, and agent registry state."""
    # This would get status from the actual orchestrator in production
    try:
        return JSONResponse(
            content={
                "status": "ok",
                "agents": 0,
                "tasks_queued": 0,
                "tasks_processed": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "memory_usage": "0 MB",
                "uptime": 0,
            },
            headers=get_cache_headers(max_age=5),
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
            headers=get_cache_headers(max_age=5),
        )


@router.get("/cluster/status")
async def get_cluster_status():
    """Expose distributed cluster coordination state."""
    # This would get actual cluster status in production
    try:
        return JSONResponse(
            content={
                "status": "standalone",
                "node_id": "single-node",
                "nodes": 1,
                "leader": True,
                "replication_factor": 1,
            },
            headers=get_cache_headers(max_age=5),
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
            headers=get_cache_headers(max_age=5),
        )


@router.get("/g38/status")
async def get_g38_status_endpoint():
    """Get G38 training system status."""
    try:
        status = await asyncio.to_thread(get_g38_status)
        return JSONResponse(
            content=status,
            headers=get_cache_headers(max_age=30),
        )
    except Exception as e:
        return JSONResponse(
            content={
                "available": False,
                "error": str(e),
            },
            status_code=500,
            headers=get_cache_headers(max_age=5),
        )


@router.get("/system/stats")
async def get_system_stats():
    """Get system-wide statistics."""
    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())

        return JSONResponse(
            content={
                "cpu_percent": psutil.cpu_percent(),
                "memory_usage_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "memory_percent": process.memory_percent(),
                "threads": process.num_threads(),
                "open_files": len(process.open_files()),
                "connections": len(process.connections()),
                "timestamp": datetime.now(UTC).isoformat(),
            },
            headers=get_cache_headers(max_age=10),
        )
    except ImportError:
        # psutil not installed, return basic info
        return JSONResponse(
            content={
                "cpu_percent": 0,
                "memory_usage_mb": 0,
                "memory_percent": 0,
                "threads": 0,
                "open_files": 0,
                "connections": 0,
                "note": "Install psutil for detailed system stats",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            headers=get_cache_headers(max_age=10),
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
            headers=get_cache_headers(max_age=5),
        )
