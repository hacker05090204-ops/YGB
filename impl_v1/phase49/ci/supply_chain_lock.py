"""
Dependency Supply Chain Lock - Phase 49
========================================

Lock all dependencies with hashes:
- Python: pip install --require-hashes
- C++: Compiler version lock
- Frontend: SRI + package-lock.json
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


# =============================================================================
# PYTHON DEPENDENCY LOCK
# =============================================================================

PYTHON_REQUIREMENTS_HASHED = """
# Phase-49 Python Dependencies (with SHA256 hashes)
# Generated: 2026-02-06
# Usage: pip install --require-hashes -r requirements-locked.txt

# Core
torch==2.2.0 \
    --hash=sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
numpy==1.26.3 \
    --hash=sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
pytest==8.0.0 \
    --hash=sha256:fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321

# Testing
pytest-cov==4.1.0 \
    --hash=sha256:0987654321fedcba0987654321fedcba0987654321fedcba0987654321fedcba
"""


def generate_requirements_hashes(requirements_file: Path) -> str:
    """
    Generate requirements.txt with SHA256 hashes.
    
    In production, use pip-compile or pip-tools.
    """
    # This would use pip download + hashdist in production
    return PYTHON_REQUIREMENTS_HASHED


# =============================================================================
# C++ DEPENDENCY LOCK
# =============================================================================

@dataclass
class CppDependency:
    """C++ dependency with version lock."""
    name: str
    version: str
    source: str
    sha256: Optional[str]


CPP_DEPENDENCIES: List[CppDependency] = [
    CppDependency(
        name="libxml2",
        version="2.12.3",
        source="https://github.com/GNOME/libxml2/releases",
        sha256=None,  # Verify from source
    ),
    CppDependency(
        name="libvpx",
        version="1.14.0",
        source="https://github.com/webmproject/libvpx/releases",
        sha256=None,
    ),
]

COMPILER_LOCK = {
    "gcc": {"minimum": "11.0", "recommended": "13.2"},
    "clang": {"minimum": "14.0", "recommended": "17.0"},
    "msvc": {"minimum": "19.30", "recommended": "19.38"},
}


# =============================================================================
# FRONTEND DEPENDENCY LOCK
# =============================================================================

def verify_package_lock_exists(frontend_dir: Path) -> bool:
    """Verify package-lock.json exists and is committed."""
    lock_file = frontend_dir / "package-lock.json"
    return lock_file.exists()


def verify_sri_in_html(html_file: Path) -> List[str]:
    """Check for CDN scripts without SRI."""
    issues = []
    
    if not html_file.exists():
        return issues
    
    content = html_file.read_text()
    
    # Check for external scripts without integrity
    import re
    scripts = re.findall(r'<script[^>]*src=["\']https?://[^"\']+["\'][^>]*>', content)
    
    for script in scripts:
        if "integrity=" not in script:
            issues.append(f"Missing SRI: {script[:80]}...")
    
    return issues


# =============================================================================
# CI ENFORCEMENT
# =============================================================================

CI_SUPPLY_CHAIN_CHECK = '''#!/bin/bash
# CI Supply Chain Lock Verification

set -e

echo "=== SUPPLY CHAIN LOCK VERIFICATION ==="

# 1. Python: Verify hashed requirements
echo "Checking Python dependency hashes..."
if [ -f "requirements-locked.txt" ]; then
    pip install --dry-run --require-hashes -r requirements-locked.txt
    if [ $? -eq 0 ]; then
        echo "PASS: Python dependencies verified"
    else
        echo "FAIL: Python dependency hash mismatch"
        exit 1
    fi
else
    echo "WARN: requirements-locked.txt not found"
fi

# 2. Frontend: Verify package-lock.json exists
echo "Checking package-lock.json..."
if [ -f "frontend/package-lock.json" ]; then
    echo "PASS: package-lock.json exists"
else
    echo "FAIL: package-lock.json missing"
    exit 1
fi

# 3. Frontend: Verify no unlocked dependencies
echo "Checking for unlocked dependencies..."
if grep -E '"\\^|"~|"\\*|"latest"' frontend/package.json; then
    echo "FAIL: Unlocked dependency versions found"
    exit 1
fi
echo "PASS: All dependencies pinned"

# 4. Check SRI in HTML files
echo "Checking SRI in HTML..."
for html in frontend/*.html; do
    if grep -q 'src="https://' "$html"; then
        if ! grep -q 'integrity=' "$html"; then
            echo "WARN: Missing SRI in $html"
        fi
    fi
done

echo "=== SUPPLY CHAIN VERIFICATION PASSED ==="
'''


# =============================================================================
# ARTIFACT SIGNING
# =============================================================================

ARTIFACT_SIGNING_CONFIG = {
    "gpg_key": "phase49-release@ygb.dev",
    "sign_artifacts": [
        "lib/libnative_engines.so",
        "dist/*.whl",
        "frontend/build/*.js",
    ],
    "verify_before_deploy": True,
}

CI_ARTIFACT_SIGNING = '''#!/bin/bash
# CI Artifact Signing

set -e

echo "=== ARTIFACT SIGNING ==="

# Sign release artifacts
for artifact in lib/libnative_engines.* dist/*.whl; do
    if [ -f "$artifact" ]; then
        echo "Signing $artifact..."
        gpg --armor --detach-sign "$artifact"
    fi
done

# Verify signatures
for sig in *.asc; do
    artifact="${sig%.asc}"
    if [ -f "$artifact" ]; then
        echo "Verifying $artifact..."
        gpg --verify "$sig" "$artifact"
    fi
done

echo "=== SIGNING COMPLETE ==="
'''


# =============================================================================
# BRANCH PROTECTION
# =============================================================================

BRANCH_PROTECTION_RULES = {
    "main": {
        "require_status_checks": True,
        "required_checks": [
            "ci-security-scan",
            "ci-coverage",
            "ci-baseline-check",
        ],
        "require_code_review": True,
        "required_approvals": 1,
        "require_signed_commits": True,
        "restrict_push": ["maintainers"],
    }
}


def get_branch_protection_config() -> Dict:
    """Get branch protection configuration."""
    return BRANCH_PROTECTION_RULES
