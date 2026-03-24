from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException


def list_report_entries(project_root: Path) -> dict:
    report_dir = project_root / "report"
    if not report_dir.exists():
        return {"reports": [], "count": 0}

    reports = []
    for file in sorted(report_dir.glob("*.txt"), reverse=True):
        stat = file.stat()
        reports.append(
            {
                "filename": file.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "download_url": f"/api/reports/{file.name}",
            }
        )
    return {"reports": reports, "count": len(reports)}


def resolve_report_file(project_root: Path, filename: str) -> Path:
    report_dir = project_root / "report"
    file_path = report_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    if not str(file_path.resolve()).startswith(str(report_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    return file_path


def guess_report_media_type(file_path: Path) -> str:
    return mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"


def read_report_content(project_root: Path, filename: str) -> str:
    file_path = resolve_report_file(project_root, filename)
    return file_path.read_text(encoding="utf-8")
