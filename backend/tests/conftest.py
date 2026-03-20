"""
conftest.py — Shared fixtures for backend/tests.

Provides ephemeral secrets so that KeyManager and ApprovalLedger tests
can construct real instances without requiring external key infrastructure.

Production behavior is NOT weakened:
  - KeyManager still raises in strict mode without YGB_KEY_DIR.
  - This fixture only sets YGB_APPROVAL_SECRET (the non-strict dev fallback)
    when the env var is absent, matching what a real dev workstation would have.
"""

import os
import secrets
import asyncio

import pytest


@pytest.fixture(autouse=True)
def _ensure_approval_secret(monkeypatch):
    """Provide an ephemeral YGB_APPROVAL_SECRET for tests that need KeyManager.

    If neither YGB_KEY_DIR nor YGB_APPROVAL_SECRET is already set, inject a
    random ephemeral secret for this test session.  This mirrors what a
    developer would configure locally — it does NOT weaken production
    fail-closed behavior (strict mode still requires YGB_KEY_DIR with
    real key files).
    """
    if not os.environ.get("YGB_KEY_DIR") and not os.environ.get("YGB_APPROVAL_SECRET"):
        monkeypatch.setenv("YGB_APPROVAL_SECRET", secrets.token_hex(32))


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Keep a default main-thread event loop available for legacy sync tests."""
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    yield
