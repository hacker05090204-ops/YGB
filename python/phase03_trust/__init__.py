"""
Phase-03 Trust Boundaries Module
REIMPLEMENTED-2026

This module defines trust zones, input sources, and trust boundaries.
It contains NO execution logic.
"""

from python.phase03_trust.trust_zones import TrustZone, get_all_trust_zones
from python.phase03_trust.input_sources import InputSource, get_all_input_sources
from python.phase03_trust.trust_boundaries import (
    TrustBoundary,
    check_trust_crossing,
    TrustViolationError,
)

__all__ = [
    'TrustZone',
    'get_all_trust_zones',
    'InputSource',
    'get_all_input_sources',
    'TrustBoundary',
    'check_trust_crossing',
    'TrustViolationError',
]
