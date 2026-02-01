"""
BugType enum - Phase-07 Bug Intelligence.
REIMPLEMENTED-2026

Closed enum for bug types.
UNKNOWN is returned for unrecognized bugs - NO GUESSING.
"""

from enum import Enum
from typing import Dict


class BugType(Enum):
    """
    Closed enum representing all known bug types.
    
    UNKNOWN is returned for unrecognized bugs.
    The resolver NEVER guesses - it uses explicit mapping only.
    """
    XSS = "xss"
    SQLI = "sqli"
    IDOR = "idor"
    SSRF = "ssrf"
    CSRF = "csrf"
    XXE = "xxe"
    PATH_TRAVERSAL = "path_traversal"
    OPEN_REDIRECT = "open_redirect"
    RCE = "rce"
    LFI = "lfi"
    UNKNOWN = "unknown"


# Explicit name-to-type mapping - NO GUESSING
_NAME_TO_TYPE: Dict[str, BugType] = {
    "xss": BugType.XSS,
    "sqli": BugType.SQLI,
    "idor": BugType.IDOR,
    "ssrf": BugType.SSRF,
    "csrf": BugType.CSRF,
    "xxe": BugType.XXE,
    "path_traversal": BugType.PATH_TRAVERSAL,
    "open_redirect": BugType.OPEN_REDIRECT,
    "rce": BugType.RCE,
    "lfi": BugType.LFI,
    "unknown": BugType.UNKNOWN,
}


def lookup_bug_type(bug_name: str) -> BugType:
    """
    Convert a string bug name to BugType enum.
    
    Returns BugType.UNKNOWN if not recognized.
    NEVER guesses - explicit mapping only.
    
    Args:
        bug_name: The bug type name (case insensitive)
        
    Returns:
        BugType enum value, or UNKNOWN if not found
    """
    return _NAME_TO_TYPE.get(bug_name.lower(), BugType.UNKNOWN)
