"""
governance — Centralized governance sector.

Re-exports all governance modules from backend.governance and
provides access to phase governance docs.
"""

import warnings
import logging

logger = logging.getLogger(__name__)

# Direct re-exports from backend.governance
try:
    from backend.governance.approval_ledger import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.approval_ledger (%s)",
        exc,
    )

try:
    from backend.governance.audit_archive import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.audit_archive (%s)",
        exc,
    )

try:
    from backend.governance.authority_lock import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.authority_lock (%s)",
        exc,
    )

try:
    from backend.governance.auto_mode_controller import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.auto_mode_controller (%s)",
        exc,
    )

try:
    from backend.governance.automation_enforcer import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.automation_enforcer (%s)",
        exc,
    )

try:
    from backend.governance.certification_gate import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.certification_gate (%s)",
        exc,
    )

try:
    from backend.governance.clock_guard import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.clock_guard (%s)",
        exc,
    )

try:
    from backend.governance.device_authority import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.device_authority (%s)",
        exc,
    )

try:
    from backend.governance.governance_policy_check import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.governance_policy_check (%s)",
        exc,
    )

try:
    from backend.governance.incident_reconciler import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.incident_reconciler (%s)",
        exc,
    )

try:
    from backend.governance.mode_progression import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.mode_progression (%s)",
        exc,
    )

try:
    from backend.governance.representation_guard import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: backend.governance.representation_guard (%s)",
        exc,
    )

# Policy configuration
try:
    from governance.real_data_rollout_governor import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: governance.real_data_rollout_governor (%s)",
        exc,
    )

try:
    from governance.training_quality_gates import *  # noqa: F401, F403
except ImportError as exc:
    logger.debug(
        "Optional governance import unavailable: governance.training_quality_gates (%s)",
        exc,
    )

logger.debug("[GOVERNANCE] Centralized governance sector loaded")
