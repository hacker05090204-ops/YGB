from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends

from api.services.runtime_status_service import (
    get_accuracy_snapshot_payload,
    get_runtime_status_payload,
)


def build_runtime_router(
    *,
    project_root: Path,
    require_auth_dependency,
    g38_available: bool,
    get_auto_trainer: Callable[[], Any],
    repair_runtime_artifacts_if_needed: Callable[..., dict],
    read_validated_telemetry: Callable[
        [Path], tuple[Optional[Dict[str, Any]], Optional[str]]
    ],
    get_runtime_status_cached: Callable[[], Optional[Dict[str, Any]]],
    store_runtime_status_cached: Callable[[Dict[str, Any]], Dict[str, Any]],
    logger,
) -> APIRouter:
    router = APIRouter(tags=["runtime-status"])

    @router.get("/runtime/status")
    async def runtime_status(user=Depends(require_auth_dependency)):
        return get_runtime_status_payload(
            project_root=project_root,
            g38_available=g38_available,
            get_auto_trainer=get_auto_trainer,
            repair_runtime_artifacts_if_needed=repair_runtime_artifacts_if_needed,
            read_validated_telemetry=read_validated_telemetry,
            get_runtime_status_cached=get_runtime_status_cached,
            store_runtime_status_cached=store_runtime_status_cached,
            logger=logger,
        )

    @router.get("/api/accuracy/snapshot")
    async def accuracy_snapshot(user=Depends(require_auth_dependency)):
        return get_accuracy_snapshot_payload(
            project_root=project_root,
            g38_available=g38_available,
            get_auto_trainer=get_auto_trainer,
            read_validated_telemetry=read_validated_telemetry,
            logger=logger,
        )

    return router
