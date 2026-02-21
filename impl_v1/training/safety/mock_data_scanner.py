"""
mock_data_scanner.py — Production Mock Data Scanner

Scans production code for dangerous patterns:
  - "placeholder"
  - "mock_"
  - "dummy"
  - "test_dataset"

If found in production paths → abort training.
Whitelist: tests/, test_*.py, __pycache__

Prevents accidental training on synthetic/mock data.
"""

import os
import re
import logging
from dataclasses import dataclass
from typing import List, Tuple, Set

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Patterns that indicate mock/placeholder data
FORBIDDEN_PATTERNS = [
    r'placeholder\s*=',
    r'mock_data\s*=',
    r'mock_features\s*=',
    r'mock_labels\s*=',
    r'dummy_data\s*=',
    r'dummy_features\s*=',
    r'test_dataset\s*=.*random',
    r'fake_data\s*=',
    r'synthetic_fallback\s*=\s*True',
    r'np\.random\.randn.*#.*mock',
    r'torch\.randn.*#.*mock',
]

# Directories to whitelist (never scan)
WHITELIST_DIRS = {
    'tests', 'test', '__pycache__', '.git', 'node_modules',
    '.vscode', '.gemini', 'venv', 'env', '.tox',
}

# File patterns to whitelist
WHITELIST_FILES = {
    'test_*.py', 'conftest.py', '*_test.py',
}

# Production paths to scan
PRODUCTION_PATHS = [
    'impl_v1/phase49/runtime',
    'impl_v1/phase49/governors',
    'impl_v1/training/data',
    'impl_v1/training/config',
    'backend/training',
    'training/validation',
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ScanResult:
    """Result of a mock data scan."""
    passed: bool
    violations: List[dict]
    files_scanned: int
    patterns_checked: int


# =============================================================================
# SCANNER
# =============================================================================

def _is_whitelisted(filepath: str) -> bool:
    """Check if file is whitelisted (test file or test directory)."""
    parts = filepath.replace('\\', '/').split('/')
    
    # Check directory whitelist
    for part in parts:
        if part in WHITELIST_DIRS:
            return True
    
    # Check file pattern whitelist
    basename = os.path.basename(filepath)
    if basename.startswith('test_') or basename.endswith('_test.py'):
        return True
    if basename == 'conftest.py':
        return True
    
    return False


def scan_file(filepath: str) -> List[dict]:
    """Scan a single file for mock data patterns.
    
    Args:
        filepath: Path to scan.
    
    Returns:
        List of violation dicts with line, pattern, content.
    """
    violations = []
    
    if _is_whitelisted(filepath):
        return violations
    
    if not filepath.endswith('.py'):
        return violations
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            for pattern in FORBIDDEN_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append({
                        'file': filepath,
                        'line': i,
                        'pattern': pattern,
                        'content': stripped[:120],
                    })
    
    except Exception as e:
        logger.warning(f"[MOCK_SCAN] Could not read {filepath}: {e}")
    
    return violations


def scan_production(project_root: str = None) -> ScanResult:
    """Scan production code for mock data.
    
    Args:
        project_root: Project root directory. Default: auto-detect.
    
    Returns:
        ScanResult with pass/fail and violations.
    """
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
    
    all_violations = []
    files_scanned = 0
    
    for rel_path in PRODUCTION_PATHS:
        scan_dir = os.path.join(project_root, rel_path)
        if not os.path.isdir(scan_dir):
            continue
        
        for root, dirs, files in os.walk(scan_dir):
            # Skip whitelisted dirs
            dirs[:] = [d for d in dirs if d not in WHITELIST_DIRS]
            
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                
                filepath = os.path.join(root, fname)
                files_scanned += 1
                violations = scan_file(filepath)
                all_violations.extend(violations)
    
    passed = len(all_violations) == 0
    
    result = ScanResult(
        passed=passed,
        violations=all_violations,
        files_scanned=files_scanned,
        patterns_checked=len(FORBIDDEN_PATTERNS),
    )
    
    if passed:
        logger.info(
            f"[MOCK_SCAN] PASS: {files_scanned} files scanned, "
            f"0 violations"
        )
    else:
        logger.error(
            f"[MOCK_SCAN] FAIL: {len(all_violations)} violations in "
            f"{files_scanned} files"
        )
        for v in all_violations[:5]:
            logger.error(f"  {v['file']}:{v['line']} — {v['content']}")
    
    return result
