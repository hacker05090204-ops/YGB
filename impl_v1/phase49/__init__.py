# Phase-49: Final Execution, Browser, Voice & Intelligence Layer
"""
CRITICAL: This is the FIRST phase with actual execution capabilities.
All prior phases (01-48) are pure governance with no execution logic.

This phase implements 18 governors that control:
- Execution kernel state machine
- Browser launch (C++ native)
- Voice input/output (TTS proxy)
- Dashboard approval flow
- Target discovery (read-only)
- CVE intelligence (read-only, real API)
- Device trust & licensing
- Final execution seal
- Gmail owner alerts
- Voice reporting (bilingual)
- Screen inspection (read-only)

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
from .governors.g15_cve_api import (
    CVEAPIConfig,
    CVEAPIResult,
    APIStatus,
    fetch_cves_passive,
    can_cve_trigger_execution,
)
from .governors.g16_gmail_alerts import (
    GmailAlertConfig,
    AlertSendResult,
    VerificationPassword,
    generate_verification_password,
    send_alert,
    can_email_approve_execution,
)
from .governors.g17_voice_reporting import (
    VoiceReportType,
    VoiceReport,
    ProgressNarration,
    generate_high_impact_tips,
    explain_report,
    can_voice_execute,
)
from .governors.g18_screen_inspection import (
    InspectionMode,
    ScreenInspectionRequest,
    InspectionResult,
    create_inspection_request,
    can_execute_inspection,
    can_inspection_interact,
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
    # G15
    "CVEAPIConfig",
    "CVEAPIResult",
    "APIStatus",
    "fetch_cves_passive",
    "can_cve_trigger_execution",
    # G16
    "GmailAlertConfig",
    "AlertSendResult",
    "VerificationPassword",
    "generate_verification_password",
    "send_alert",
    "can_email_approve_execution",
    # G17
    "VoiceReportType",
    "VoiceReport",
    "ProgressNarration",
    "generate_high_impact_tips",
    "explain_report",
    "can_voice_execute",
    # G18
    "InspectionMode",
    "ScreenInspectionRequest",
    "InspectionResult",
    "create_inspection_request",
    "can_execute_inspection",
    "can_inspection_interact",
]
