from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse

from backend.auth.auth_guard import require_auth

from api.services.report_service import (
    guess_report_media_type,
    list_report_entries,
    read_report_content,
    resolve_report_file,
)


def build_report_router(project_root: Path) -> APIRouter:
    router = APIRouter(tags=["reports"])

    @router.get("/api/reports")
    async def list_reports(user=Depends(require_auth)):
        return list_report_entries(project_root)

    @router.get("/api/reports/{filename}")
    async def download_report(filename: str, user=Depends(require_auth)):
        file_path = resolve_report_file(project_root, filename)
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=guess_report_media_type(file_path),
        )

    @router.get("/api/reports/{filename}/content")
    async def get_report_content(filename: str, user=Depends(require_auth)):
        return PlainTextResponse(read_report_content(project_root, filename))

    return router
