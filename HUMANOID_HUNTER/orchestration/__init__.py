"""
Phase-25 Orchestration Binding & Execution Intent Sealing.

This module provides orchestration binding governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Planning defines intent
- Orchestration seals intent
- Execution never decides intent

Exports:
    Enums (CLOSED):
        OrchestrationIntentState: DRAFT, SEALED, REJECTED
        OrchestrationDecision: ACCEPT, REJECT
    
    Dataclasses (all frozen=True):
        OrchestrationIntent: Sealed orchestration intent
        OrchestrationContext: Orchestration context
        OrchestrationResult: Orchestration result
    
    Functions (pure, deterministic):
        bind_plan_to_intent: Bind plan to intent
        seal_orchestration_intent: Seal intent
        decide_orchestration: Make orchestration decision
"""
from .orchestration_types import (
    OrchestrationIntentState,
    OrchestrationDecision
)
from .orchestration_context import (
    OrchestrationIntent,
    OrchestrationContext,
    OrchestrationResult
)
from .orchestration_engine import (
    bind_plan_to_intent,
    seal_orchestration_intent,
    decide_orchestration
)

__all__ = [
    # Enums
    "OrchestrationIntentState",
    "OrchestrationDecision",
    # Dataclasses
    "OrchestrationIntent",
    "OrchestrationContext",
    "OrchestrationResult",
    # Functions
    "bind_plan_to_intent",
    "seal_orchestration_intent",
    "decide_orchestration",
]
