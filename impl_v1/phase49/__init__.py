# Phase-49: Final Execution, Browser, Voice & Intelligence Layer
"""
CRITICAL: This is the FIRST phase with actual execution capabilities.
All prior phases (01-48) are pure governance with no execution logic.

This phase implements 24 governors that control:
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
- Interactive browser session (OBSERVE_ONLY)
- Dashboard state & events
- Auto-update governance
- User/Admin database

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
from .governors.g19_interactive_browser import (
    InteractiveMode,
    SessionState,
    Platform,
    InteractiveSession,
    ObservationResult,
    create_interactive_session,
    perform_observation,
    detect_platform,
    can_session_execute,
    can_session_interact,
)
from .governors.g20_dashboard_state import (
    DashboardPanel,
    UserMode,
    ActivityType,
    DashboardState,
    DashboardEvent,
    create_dashboard_state,
    update_activity_with_targets,
    can_dashboard_approve_execution,
)
from .governors.g21_auto_update import (
    UpdateStatus,
    UpdateChannel,
    UpdateInfo,
    UpdateApproval,
    check_for_updates,
    request_update_approval,
    install_update,
    rollback,
    can_auto_update_execute,
)
from .governors.g22_user_database import (
    UserRole,
    Permission,
    User,
    UserSession,
    Admin,
    create_user,
    create_session,
    create_admin,
    can_database_delete_without_approval,
)
from .governors.g23_reasoning_engine import (
    ReportSection,
    EvidenceType,
    ReasoningStatus,
    EvidencePack,
    StructuredReport,
    VoiceScript,
    ReasoningResult,
    create_evidence_pack,
    perform_reasoning,
    can_reasoning_execute,
    can_reasoning_decide,
    can_reasoning_modify_state,
)
from .governors.g24_system_evolution import (
    PythonVersionStatus,
    DependencyStatus,
    UpdateDecision,
    SystemMode,
    HealthStatus,
    RollbackDecision,
    check_python_version_upgrade,
    check_dependency_stability,
    create_update_policy,
    check_update_policy,
    check_system_health,
    check_rollback_availability,
    can_evolution_governor_execute,
    can_evolution_governor_modify,
    can_evolution_governor_approve,
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
    # G19
    "InteractiveMode",
    "SessionState",
    "Platform",
    "InteractiveSession",
    "ObservationResult",
    "create_interactive_session",
    "perform_observation",
    "detect_platform",
    "can_session_execute",
    "can_session_interact",
    # G20
    "DashboardPanel",
    "UserMode",
    "ActivityType",
    "DashboardState",
    "DashboardEvent",
    "create_dashboard_state",
    "update_activity_with_targets",
    "can_dashboard_approve_execution",
    # G21
    "UpdateStatus",
    "UpdateChannel",
    "UpdateInfo",
    "UpdateApproval",
    "check_for_updates",
    "request_update_approval",
    "install_update",
    "rollback",
    "can_auto_update_execute",
    # G22
    "UserRole",
    "Permission",
    "User",
    "UserSession",
    "Admin",
    "create_user",
    "create_session",
    "create_admin",
    "can_database_delete_without_approval",
    # G23
    "ReportSection",
    "EvidenceType",
    "ReasoningStatus",
    "EvidencePack",
    "StructuredReport",
    "VoiceScript",
    "ReasoningResult",
    "create_evidence_pack",
    "perform_reasoning",
    "can_reasoning_execute",
    "can_reasoning_decide",
    "can_reasoning_modify_state",
    # G24
    "PythonVersionStatus",
    "DependencyStatus",
    "UpdateDecision",
    "SystemMode",
    "HealthStatus",
    "RollbackDecision",
    "check_python_version_upgrade",
    "check_dependency_stability",
    "create_update_policy",
    "check_update_policy",
    "check_system_health",
    "check_rollback_availability",
    "can_evolution_governor_execute",
    "can_evolution_governor_modify",
    "can_evolution_governor_approve",
]


