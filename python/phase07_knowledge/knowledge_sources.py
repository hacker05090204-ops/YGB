"""
KnowledgeSource enum - Phase-07 Bug Intelligence.
REIMPLEMENTED-2026

Closed enum for knowledge sources.
"""

from enum import Enum


class KnowledgeSource(Enum):
    """
    Closed enum representing knowledge sources.
    
    Sources:
        CVE: Common Vulnerabilities and Exposures
        CWE: Common Weakness Enumeration
        MANUAL: Manually defined explanation
        UNKNOWN: Unknown/unrecognized bug type
    """
    CVE = "cve"
    CWE = "cwe"
    MANUAL = "manual"
    UNKNOWN = "unknown"
