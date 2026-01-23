"""
DecisionContext dataclass - Phase-06 Decision Aggregation.
REIMPLEMENTED-2026

Frozen dataclass aggregating inputs from Phase-02, 03, 04, 05.
No execution logic - context only.
"""

from dataclasses import dataclass

from python.phase02_actors.actors import ActorType
from python.phase03_trust.trust_zones import TrustZone
from python.phase04_validation.requests import ValidationResponse
from python.phase05_workflow.state_machine import TransitionResponse


@dataclass(frozen=True)
class DecisionContext:
    """
    Immutable context for decision resolution.
    
    Aggregates inputs from prior phases:
        - validation_response: Phase-04 ValidationResponse
        - transition_response: Phase-05 TransitionResponse
        - actor_type: Phase-02 ActorType
        - trust_zone: Phase-03 TrustZone
    """
    validation_response: ValidationResponse
    transition_response: TransitionResponse
    actor_type: ActorType
    trust_zone: TrustZone
