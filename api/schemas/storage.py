from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    name: str
    email: Optional[str] = None
    role: str = "researcher"


class CreateTargetRequest(BaseModel):
    program_name: str
    scope: str
    link: Optional[str] = None
    platform: Optional[str] = None
    payout_tier: str = "MEDIUM"


class CreateBountyRequest(BaseModel):
    user_id: str
    target_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    severity: str = "MEDIUM"


class UpdateBountyRequest(BaseModel):
    bounty_id: str
    status: str
    reward: Optional[float] = None


class CreateSessionRequest(BaseModel):
    user_id: str
    mode: str
    target_scope: Optional[str] = None
