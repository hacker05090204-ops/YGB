"""
Phase-07: Bug Intelligence & Knowledge Resolution Layer
REIMPLEMENTED-2026

Provides deterministic bug intelligence and knowledge resolution.
Returns UNKNOWN for unrecognized bugs - NEVER guesses.

Supports bilingual explanations (English + Hindi).

Exports:
    - BugType: Enum of bug types
    - KnowledgeSource: Enum of knowledge sources
    - BugExplanation: Frozen dataclass for explanations
    - lookup_bug_type: String to BugType conversion
    - resolve_bug_info: Get explanation for bug type
"""

from python.phase07_knowledge.bug_types import BugType, lookup_bug_type
from python.phase07_knowledge.knowledge_sources import KnowledgeSource
from python.phase07_knowledge.explanations import BugExplanation, get_known_explanations
from python.phase07_knowledge.resolver import resolve_bug_info

__all__ = [
    "BugType",
    "KnowledgeSource",
    "BugExplanation",
    "lookup_bug_type",
    "resolve_bug_info",
    "get_known_explanations",
]
