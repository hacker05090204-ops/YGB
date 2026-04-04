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
except ImportError:
    pass

try:
    from backend.governance.audit_archive import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.authority_lock import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.auto_mode_controller import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.automation_enforcer import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.certification_gate import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.clock_guard import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.device_authority import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.governance_policy_check import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.incident_reconciler import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.mode_progression import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from backend.governance.representation_guard import *  # noqa: F401, F403
except ImportError:
    pass

# Policy configuration
try:
    from governance.real_data_rollout_governor import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from governance.training_quality_gates import *  # noqa: F401, F403
except ImportError:
    pass

logger.debug("[GOVERNANCE] Centralized governance sector loaded")
