"""Base router utilities and common imports for YGB API routers."""

from typing import Dict, Any, List, Optional
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Common Pydantic models
from pydantic import BaseModel


class StartWorkflowRequest(BaseModel):
    target: str
    mode: str = "READ_ONLY"


class CreateDashboardRequest(BaseModel):
    user_id: str
    user_name: str = "User"


class ExecutionTransitionRequest(BaseModel):
    transition: str


class ApprovalRequest(BaseModel):
    session_id: str
    action: str
    reason: Optional[str] = None


# Common utility functions
def get_project_root() -> Path:
    """Get the project root directory."""
    return PROJECT_ROOT


def serialize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a database record for JSON response."""
    serialized = dict(record)
    for key, value in list(serialized.items()):
        if hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        elif value is not None and (key == "id" or key.endswith("_id")):
            serialized[key] = str(value)
    return serialized


def serialize_strategy(strategy: Any) -> Dict[str, Any]:
    """Serialize a strategy object for JSON response."""
    return {
        "agent_name": getattr(strategy, "agent_name", "workflow-orchestrator"),
        "task_type": getattr(strategy, "task_type", "request"),
        "crawl_depth": getattr(strategy, "crawl_depth", 0),
        "concurrency": getattr(strategy, "concurrency", 1),
        "payload_profile": getattr(strategy, "payload_profile", "standard"),
        "verification_level": getattr(strategy, "verification_level", "standard"),
        "priority": getattr(strategy, "priority", "medium"),
        "rate_limit_per_host": getattr(strategy, "rate_limit_per_host", 1),
        "notes": list(getattr(strategy, "notes", [])),
    }


def create_error_response(message: str, status_code: int = 400) -> Dict[str, Any]:
    """Create a standardized error response."""
    return {
        "error": True,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# Router creation helper
def create_router(prefix: str = "", tags: List[str] = None) -> APIRouter:
    """Create a new router with common configuration."""
    return APIRouter(prefix=prefix, tags=tags or [])
