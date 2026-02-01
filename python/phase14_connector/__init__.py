"""
Phase-14 Backend Connector & Integration Verification Layer.

This module provides READ-ONLY connector layer that maps backend phases
to a unified format for frontend consumption.

Phase-14 has ZERO AUTHORITY - it cannot approve, modify, or override
any backend decision. All values are pass-through only.

Exports:
    Enums:
        ConnectorRequestType: Request type (STATUS_CHECK, READINESS_CHECK, FULL_EVALUATION)
    
    Dataclasses (all frozen=True):
        ConnectorInput: Input for connector
        ConnectorOutput: Output from connector (READ-ONLY from backend)
        ConnectorResult: Full result container
    
    Functions:
        validate_input: Validate input contract
        map_handoff_to_output: Map Phase-13 to output (READ-ONLY)
        propagate_blocking: Check blocking propagation
        create_default_output: Create default blocked output
        create_result: Create result container
"""
from .connector_types import ConnectorRequestType
from .connector_context import ConnectorInput, ConnectorOutput, ConnectorResult
from .connector_engine import (
    validate_input,
    map_handoff_to_output,
    propagate_blocking,
    create_default_output,
    create_result
)

__all__ = [
    # Enums
    "ConnectorRequestType",
    # Dataclasses
    "ConnectorInput",
    "ConnectorOutput",
    "ConnectorResult",
    # Functions
    "validate_input",
    "map_handoff_to_output",
    "propagate_blocking",
    "create_default_output",
    "create_result",
]
