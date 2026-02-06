"""
Frontend Hardening Specification - Phase 49
============================================

REQUIREMENTS:
1. package-lock.json with pinned versions
2. No CDN without Subresource Integrity (SRI)
3. Content Security Policy header enforced
4. No inline JS without nonce
5. No eval() in JavaScript
6. No unsanitized innerHTML

CI RULES:
- Block build if new dependency without hash pin
- Scan for CSP violations
- Check for eval patterns
"""

from dataclasses import dataclass
from typing import List, Dict, Set
from enum import Enum


# =============================================================================
# CSP CONFIGURATION
# =============================================================================

RECOMMENDED_CSP = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],  # NO 'unsafe-inline' or 'unsafe-eval'
    "style-src": ["'self'", "'unsafe-inline'"],  # Allow inline styles
    "img-src": ["'self'", "data:", "https:"],
    "font-src": ["'self'"],
    "connect-src": ["'self'"],
    "frame-ancestors": ["'none'"],
    "form-action": ["'self'"],
    "base-uri": ["'self'"],
    "object-src": ["'none'"],
}

FORBIDDEN_CSP_VALUES = {
    "'unsafe-eval'",      # Allows eval()
    "'unsafe-inline'",    # Allows inline scripts (in script-src)
    "*",                  # Wildcard
    "data:",              # In script-src, allows data: scripts
}


# =============================================================================
# DEPENDENCY RULES
# =============================================================================

class DependencyRisk(Enum):
    """Risk level for dependencies."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DependencyRule:
    """Rule for dependency management."""
    rule: str
    risk: DependencyRisk
    enforcement: str


DEPENDENCY_RULES: List[DependencyRule] = [
    DependencyRule(
        rule="All versions must be pinned (no ^, ~, *, latest)",
        risk=DependencyRisk.HIGH,
        enforcement="lockfile-lint",
    ),
    DependencyRule(
        rule="package-lock.json must exist and be committed",
        risk=DependencyRisk.HIGH,
        enforcement="CI check",
    ),
    DependencyRule(
        rule="No CDN scripts without SRI hash",
        risk=DependencyRisk.CRITICAL,
        enforcement="HTML scan",
    ),
    DependencyRule(
        rule="npm audit must pass with no high/critical vulns",
        risk=DependencyRisk.HIGH,
        enforcement="npm audit --audit-level=high",
    ),
]


# =============================================================================
# FORBIDDEN PATTERNS
# =============================================================================

FORBIDDEN_JS_PATTERNS: Dict[str, str] = {
    "eval(": "Do not use eval() - use safe alternatives",
    "new Function(": "Do not use Function constructor",
    "innerHTML =": "Use textContent or DOMPurify.sanitize()",
    "outerHTML =": "Use safe DOM manipulation",
    "document.write": "Do not use document.write",
    "setTimeout(string": "Pass function reference, not string",
    "setInterval(string": "Pass function reference, not string",
}

SAFE_ALTERNATIVES: Dict[str, str] = {
    "eval()": "JSON.parse() for JSON, safe parser for expressions",
    "innerHTML": "textContent, createElement, or DOMPurify.sanitize()",
    "document.write": "DOM manipulation methods",
    "string in setTimeout": "setTimeout(functionRef, delay)",
}


# =============================================================================
# SRI (Subresource Integrity)
# =============================================================================

@dataclass
class SRIRequirement:
    """SRI requirement for external resources."""
    element: str
    attribute: str
    algorithm: str


SRI_REQUIREMENTS: List[SRIRequirement] = [
    SRIRequirement(
        element="script",
        attribute="integrity",
        algorithm="sha384",
    ),
    SRIRequirement(
        element="link[rel=stylesheet]",
        attribute="integrity",
        algorithm="sha384",
    ),
]


# =============================================================================
# SECURITY HEADERS
# =============================================================================

REQUIRED_HEADERS: Dict[str, str] = {
    "Content-Security-Policy": "See RECOMMENDED_CSP",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def check_csp_safety(csp_header: str) -> List[str]:
    """Check CSP header for unsafe values."""
    issues = []
    
    for unsafe in FORBIDDEN_CSP_VALUES:
        if unsafe in csp_header:
            if unsafe == "'unsafe-inline'" and "script-src" in csp_header:
                issues.append(f"CSP contains {unsafe} in script-src")
            elif unsafe == "'unsafe-eval'":
                issues.append(f"CSP contains {unsafe}")
            elif unsafe == "*":
                issues.append("CSP contains wildcard (*)")
    
    return issues


def get_recommended_csp_header() -> str:
    """Get the recommended CSP header string."""
    parts = []
    for directive, values in RECOMMENDED_CSP.items():
        parts.append(f"{directive} {' '.join(values)}")
    return "; ".join(parts)


def get_forbidden_patterns() -> Dict[str, str]:
    """Get forbidden JS patterns and their fixes."""
    return FORBIDDEN_JS_PATTERNS


def get_dependency_rules() -> List[DependencyRule]:
    """Get dependency management rules."""
    return DEPENDENCY_RULES
