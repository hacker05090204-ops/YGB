"""Centralized execution validation hooks.

This layer does not change governance rules; it only makes the existing control
checks mandatory and reusable so execution entrypoints cannot bypass them.
"""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import HTTPException


def enforce_governed_execution(
    *,
    action_name: str,
    can_ai_execute: Callable[[], tuple[bool, str]],
    can_ai_submit: Callable[[], tuple[bool, str]],
    target_url: Optional[str] = None,
    validate_target_url: Optional[Callable[[str], tuple[bool, list[dict]]]] = None,
    normalize_target: bool = False,
) -> Optional[str]:
    execute_allowed, execute_reason = can_ai_execute()
    if execute_allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Governance blocked execution for {action_name}: {execute_reason}",
        )

    submit_allowed, submit_reason = can_ai_submit()
    if submit_allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Governance blocked submission for {action_name}: {submit_reason}",
        )

    if target_url is None:
        return None

    normalized = target_url.strip()
    if (
        normalize_target
        and normalized
        and not normalized.startswith(("http://", "https://"))
    ):
        normalized = f"https://{normalized}"

    if validate_target_url is not None and normalized:
        is_safe, violations = validate_target_url(normalized)
        if not is_safe:
            message = violations[0]["message"] if violations else "Target rejected"
            raise HTTPException(
                status_code=400, detail=f"Target URL rejected: {message}"
            )

    return normalized
