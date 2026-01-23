"""
Bug Knowledge Resolver - Phase-07 Bug Intelligence.
REIMPLEMENTED-2026

Pure function for resolving bug information.
NEVER guesses - returns UNKNOWN for unrecognized types.
"""

from python.phase07_knowledge.bug_types import BugType
from python.phase07_knowledge.explanations import BugExplanation, get_known_explanations


def resolve_bug_info(bug_type: BugType) -> BugExplanation:
    """
    Resolve bug information from the knowledge registry.
    
    If bug_type is UNKNOWN or not in registry, returns
    the UNKNOWN explanation.
    
    This function is PURE:
    - No side effects
    - No guessing
    - Deterministic
    - No network calls
    - No file access
    
    Args:
        bug_type: The BugType enum value to look up
        
    Returns:
        BugExplanation for the given bug type
    """
    registry = get_known_explanations()
    
    # Return explanation if found, otherwise return UNKNOWN
    return registry.get(bug_type, registry[BugType.UNKNOWN])
