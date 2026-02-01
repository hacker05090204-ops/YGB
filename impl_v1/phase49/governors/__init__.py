# Phase-49 Governors Package
"""All 14 governors for execution control."""

from .g01_execution_kernel import ExecutionState, ExecutionTransition, ExecutionKernel
from .g02_browser_types import BrowserType, BrowserLaunchRequest, BrowserLaunchResult
from .g03_browser_safety import BrowserSafetyCheck, BrowserSafetyResult, check_browser_safety
from .g04_voice_proxy import VoiceOutputRequest, VoiceOutputResult, VoiceOutputType
from .g05_assistant_mode import AssistantMode, AssistantExplanation
from .g06_autonomy_modes import AutonomyMode, AutonomySession
from .g07_cve_intelligence import CVERecord, CVEQueryResult
from .g08_licensing import LicenseStatus, LicenseValidation
from .g09_device_trust import DeviceTrustLevel, DeviceRegistration
from .g10_owner_alerts import AlertType, OwnerAlert
from .g11_execution_seal import ExecutionSealResult, seal_execution_intent
from .g12_voice_input import VoiceIntentType, VoiceInputStatus, VoiceIntent, validate_voice_input
from .g13_dashboard_router import ApprovalStatus, ApprovalRequest, ApprovalDecision, create_approval_request, submit_decision
from .g14_target_discovery import DiscoverySource, TargetCandidate, DiscoveryResult, discover_targets
