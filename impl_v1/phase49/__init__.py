# Phase-49: Final Execution, Browser, Voice & Intelligence Layer
"""
CRITICAL: This is the FIRST phase with actual execution capabilities.
All prior phases (01-48) are pure governance with no execution logic.

This phase implements 14 governors that control:
- Execution kernel state machine
- Browser launch (C++ native)
- Voice input/output (TTS proxy)
- Dashboard approval flow
- Target discovery (read-only)
- CVE intelligence (read-only)
- Device trust & licensing
- Final execution seal

NO SILENT EXECUTION - Human approval mandatory for EXECUTING state.
"""

from .governors.g01_execution_kernel import (
    ExecutionState,
    ExecutionTransition,
    ExecutionKernel,
)
from .governors.g02_browser_types import (
    BrowserType,
    BrowserLaunchRequest,
    BrowserLaunchResult,
)
from .governors.g03_browser_safety import (
    BrowserSafetyCheck,
    BrowserSafetyResult,
    check_browser_safety,
)
from .governors.g04_voice_proxy import (
    VoiceOutputRequest,
    VoiceOutputResult,
    VoiceOutputType,
)
from .governors.g05_assistant_mode import (
    AssistantMode,
    AssistantExplanation,
)
from .governors.g06_autonomy_modes import (
    AutonomyMode,
    AutonomySession,
)
from .governors.g07_cve_intelligence import (
    CVERecord,
    CVEQueryResult,
)
from .governors.g08_licensing import (
    LicenseStatus,
    LicenseValidation,
)
from .governors.g09_device_trust import (
    DeviceTrustLevel,
    DeviceRegistration,
)
from .governors.g10_owner_alerts import (
    AlertType,
    OwnerAlert,
)
from .governors.g11_execution_seal import (
    ExecutionSealResult,
    seal_execution_intent,
)
from .governors.g12_voice_input import (
    VoiceIntentType,
    VoiceInputStatus,
    VoiceIntent,
    validate_voice_input,
)
from .governors.g13_dashboard_router import (
    ApprovalStatus,
    ApprovalRequest,
    ApprovalDecision,
    create_approval_request,
    submit_decision,
)
from .governors.g14_target_discovery import (
    DiscoverySource,
    TargetCandidate,
    DiscoveryResult,
    discover_targets,
)

__all__ = [
    # G1
    "ExecutionState",
    "ExecutionTransition",
    "ExecutionKernel",
    # G2
    "BrowserType",
    "BrowserLaunchRequest",
    "BrowserLaunchResult",
    # G3
    "BrowserSafetyCheck",
    "BrowserSafetyResult",
    "check_browser_safety",
    # G4
    "VoiceOutputRequest",
    "VoiceOutputResult",
    "VoiceOutputType",
    # G5
    "AssistantMode",
    "AssistantExplanation",
    # G6
    "AutonomyMode",
    "AutonomySession",
    # G7
    "CVERecord",
    "CVEQueryResult",
    # G8
    "LicenseStatus",
    "LicenseValidation",
    # G9
    "DeviceTrustLevel",
    "DeviceRegistration",
    # G10
    "AlertType",
    "OwnerAlert",
    # G11
    "ExecutionSealResult",
    "seal_execution_intent",
    # G12
    "VoiceIntentType",
    "VoiceInputStatus",
    "VoiceIntent",
    "validate_voice_input",
    # G13
    "ApprovalStatus",
    "ApprovalRequest",
    "ApprovalDecision",
    "create_approval_request",
    "submit_decision",
    # G14
    "DiscoverySource",
    "TargetCandidate",
    "DiscoveryResult",
    "discover_targets",
]

