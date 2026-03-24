"""Canonical scheduling hooks for training execution control."""

from __future__ import annotations

from typing import Any, Callable, Optional

_execution_validator: Optional[Callable[[], None]] = None


def register_execution_validator(validator: Optional[Callable[[], None]]) -> None:
    global _execution_validator
    _execution_validator = validator


def validate_execution() -> None:
    if _execution_validator is not None:
        _execution_validator()


def guarded_training_call(
    validator: Optional[Callable[[], None]], action: Callable[..., Any], *args, **kwargs
):
    if validator is not None:
        validator()
    validate_execution()
    return action(*args, **kwargs)
