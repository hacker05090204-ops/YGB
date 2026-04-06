# G21: Auto-Update Governance
"""Infrastructure-gated auto-update governance contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from typing import Optional, Protocol, runtime_checkable


AUTO_UPDATE_PROVISIONING_MESSAGE = (
    "AutoUpdater requires real update server URL and signing key. "
    "Set YGB_UPDATE_SERVER and YGB_UPDATE_SIGNING_KEY env vars."
)

MIN_SIGNATURE_LENGTH = 64
REJECTED_SIGNATURES = frozenset(
    {
        "",
        "mock-signature",
        "mock_signature",
        "test-signature",
        "dummy-signature",
        "unsigned",
        "placeholder-signature",
    }
)


class RealBackendNotConfiguredError(RuntimeError):
    pass


class UpdateStatus(Enum):
    """Legacy export retained for package compatibility."""

    NONE_AVAILABLE = "NONE_AVAILABLE"
    AVAILABLE = "AVAILABLE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    INSTALLED = "INSTALLED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class UpdateChannel(Enum):
    """Legacy export retained for package compatibility."""

    STABLE = "STABLE"
    BETA = "BETA"
    ALPHA = "ALPHA"


@dataclass(frozen=True)
class UpdateContract:
    """Real update payload contract required by the production updater."""

    update_id: str
    version: str
    signature: str
    download_url: str
    checksum_sha256: str


UpdateInfo = UpdateContract


@dataclass(frozen=True)
class UpdateApproval:
    """Legacy approval export retained for package compatibility."""

    approval_id: str
    update_id: str
    user_id: str
    approved: bool
    approved_at: Optional[str]


@runtime_checkable
class UpdateVerifier(Protocol):
    """Mandatory verifier interface for future real update backends."""

    def verify_signature(self, update: UpdateContract) -> bool:
        ...


class AutoUpdater:
    """Fail-closed production updater pending a real signed update backend."""

    def __init__(
        self,
        *,
        update_server: str | None = None,
        signing_key: str | None = None,
        verifier: UpdateVerifier | None = None,
    ):
        self._update_server = update_server or os.environ.get("YGB_UPDATE_SERVER")
        self._signing_key = signing_key or os.environ.get("YGB_UPDATE_SIGNING_KEY")
        self._verifier = verifier

    def _enforce_signature_policy(self) -> None:
        if self._update_server and self._signing_key and self._verifier is None:
            raise PermissionError(
                "AutoUpdater cannot connect without a real UpdateVerifier. "
                "Signature verification is mandatory for all updates."
            )

    def check_for_update(self) -> UpdateContract | None:
        """Return an update only from a real backend; currently fail closed."""

        self._enforce_signature_policy()
        raise RealBackendNotConfiguredError(AUTO_UPDATE_PROVISIONING_MESSAGE)

    def apply_update(self, update: UpdateContract) -> bool:
        """Apply a real, verified update only when the backend is provisioned."""

        del update
        self._enforce_signature_policy()
        raise RealBackendNotConfiguredError(AUTO_UPDATE_PROVISIONING_MESSAGE)


def check_for_updates() -> UpdateContract | None:
    """Module-level compatibility wrapper for the governed update check."""

    return AutoUpdater().check_for_update()


def install_update(update: UpdateContract) -> bool:
    """Module-level compatibility wrapper for governed update application."""

    return AutoUpdater().apply_update(update)


def request_update_approval(update_id: str, user_id: str) -> UpdateApproval:
    """Legacy compatibility hook retained while the real backend is unconfigured."""

    del update_id, user_id
    raise RealBackendNotConfiguredError(AUTO_UPDATE_PROVISIONING_MESSAGE)


def rollback() -> bool:
    """Legacy compatibility hook retained while the real backend is unconfigured."""

    raise RealBackendNotConfiguredError(AUTO_UPDATE_PROVISIONING_MESSAGE)


def verify_signature(
    update: UpdateContract,
    verifier: UpdateVerifier | None = None,
) -> tuple[bool, str]:
    """Require an injected real verifier; never allow signature bypass."""

    if not isinstance(update.signature, str):
        return False, "Signature verification failed: signature must be a string"

    normalized_signature = update.signature.strip()
    if normalized_signature != update.signature:
        return False, "Signature verification failed: signature must not contain surrounding whitespace"

    if normalized_signature in REJECTED_SIGNATURES:
        return False, "Signature verification failed: rejected known non-production signature"

    if len(update.signature) < 64:
        return False, "Signature verification failed: signature must be at least 64 characters"

    if verifier is None:
        return False, "Signature verification requires a real UpdateVerifier implementation"

    try:
        verified = verifier.verify_signature(update)
    except Exception as exc:  # pragma: no cover - defensive bridge handling
        return False, f"Signature verification failed: {exc}"

    if not verified:
        return False, "Signature verification failed"

    return True, "Signature verified"


def clear_update_state() -> None:
    """No mutable update state is kept while the real backend is unconfigured."""


def can_auto_update_execute() -> tuple[bool, str]:
    """Auto-update execution remains blocked without explicit human approval."""

    return False, "Auto-update REQUIRES user approval - no forced updates"


def can_update_skip_signature() -> tuple[bool, str]:
    """Signature verification is mandatory for every real update path."""

    return False, "Signature verification is MANDATORY for all updates"


def can_update_prevent_rollback() -> tuple[bool, str]:
    """Rollback rights remain mandatory in the governed contract."""

    return False, "Rollback MUST always be available after update"
