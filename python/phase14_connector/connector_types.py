"""
Phase-14 Connector Types.

This module defines enums for connector requests.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ConnectorRequestType(Enum):
    """Type of connector request.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        STATUS_CHECK: Check current status
        READINESS_CHECK: Check browser readiness
        FULL_EVALUATION: Full pipeline evaluation
    """
    STATUS_CHECK = auto()
    READINESS_CHECK = auto()
    FULL_EVALUATION = auto()
