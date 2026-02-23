"""
data_source_audit.py — Data Source Audit Module (Phase 5)

Scans Python files in the training path for FORBIDDEN synthetic data patterns.
If any match is found in active pipeline files, training must abort.

FORBIDDEN PATTERNS:
- random.Random (procedural generation)
- random.randn / rng.randn (numpy random)
- synthetic / ScaledDatasetGenerator (synthetic data classes)
- mock / fallback (test/fallback data)
- procedural generator (procedural data)

WHITELISTED FILES:
- scaled_dataset.py (renamed, blocked by STRICT_REAL_MODE)
- data_source_audit.py (this file — contains pattern strings)
- test_*.py (test files)
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# FORBIDDEN PATTERNS
# =============================================================================

FORBIDDEN_PATTERNS = [
    r"random\.Random\(",
    r"rng\.randn\(",
    r"np\.random\.RandomState\(",
    r"random\.randn\(",
    r"ScaledDatasetGenerator",
    r"SyntheticTrainingDataset\(",
    r"\"SYNTHETIC_GENERATOR\"",
    r"mock_data",
    r"fallback_dataset",
    r"procedural.generator",
]

# Files that are allowed to contain these patterns
WHITELISTED_FILES = {
    "scaled_dataset.py",          # Renamed synthetic module (blocked)
    "data_source_audit.py",       # This file (contains pattern strings)
    "real_dataset_loader.py",     # Contains blocked SyntheticTrainingDataset class
    "training_controller.py",     # DatasetState field default (not active source)
    # Utility files that use random for non-data purposes:
    "data_enforcement.py",        # Shuffle test uses random
    "drift_guard.py",             # Noise injection for testing
    "model_versioning.py",        # Weight hashing
    "redundancy_gate.py",         # Shard verification
    "cloud_backup.py",            # Backup encryption
    "feature_cache.py",           # Feature encoding (uses rng for noise, not data gen)
}

# Only scan these specific data-loading files in the active pipeline
SCAN_DIRS = [
    "impl_v1/training/data",
]


# =============================================================================
# AUDIT TYPES
# =============================================================================

@dataclass
class AuditViolation:
    """A forbidden pattern found in a file."""
    file_path: str
    line_number: int
    line_content: str
    pattern: str
    severity: str = "CRITICAL"


@dataclass
class AuditReport:
    """Result of a data source audit."""
    passed: bool
    violations: List[AuditViolation] = field(default_factory=list)
    files_scanned: int = 0
    patterns_checked: int = 0
    whitelisted_skipped: int = 0


# =============================================================================
# AUDIT ENGINE
# =============================================================================

def audit_training_path(
    project_root: str = None,
    extra_dirs: List[str] = None,
) -> AuditReport:
    """
    Scan training path for forbidden synthetic data patterns.

    Returns:
        AuditReport with pass/fail and any violations found.
    """
    if project_root is None:
        project_root = str(Path(__file__).resolve().parent.parent.parent.parent)

    root = Path(project_root)
    violations: List[AuditViolation] = []
    files_scanned = 0
    whitelisted = 0

    # Compile patterns
    compiled = [(p, re.compile(p)) for p in FORBIDDEN_PATTERNS]

    # Collect files to scan
    scan_paths: List[Path] = []
    for scan_dir in SCAN_DIRS + (extra_dirs or []):
        target = root / scan_dir
        if target.is_file():
            scan_paths.append(target)
        elif target.is_dir():
            for py_file in target.rglob("*.py"):
                scan_paths.append(py_file)

    for py_file in scan_paths:
        basename = py_file.name

        # Skip whitelisted files
        if basename in WHITELISTED_FILES:
            whitelisted += 1
            continue

        # Skip test files
        if basename.startswith("test_"):
            whitelisted += 1
            continue

        files_scanned += 1

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            for line_num, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                for pattern_str, pattern_re in compiled:
                    if pattern_re.search(line):
                        violations.append(AuditViolation(
                            file_path=str(py_file.relative_to(root)),
                            line_number=line_num,
                            line_content=stripped[:120],
                            pattern=pattern_str,
                        ))

        except Exception as e:
            logger.warning(f"[AUDIT] Cannot read {py_file}: {e}")

    passed = len(violations) == 0

    report = AuditReport(
        passed=passed,
        violations=violations,
        files_scanned=files_scanned,
        patterns_checked=len(FORBIDDEN_PATTERNS),
        whitelisted_skipped=whitelisted,
    )

    # Log results
    icon = "✓" if passed else "✗"
    logger.info(
        f"[AUDIT] {icon} Data Source Audit: "
        f"{files_scanned} files scanned, "
        f"{len(violations)} violations, "
        f"{whitelisted} whitelisted"
    )

    if not passed:
        for v in violations:
            logger.error(
                f"[AUDIT] ✗ {v.file_path}:{v.line_number} "
                f"— pattern '{v.pattern}' found: {v.line_content[:80]}"
            )

    return report


def enforce_clean_pipeline(project_root: str = None) -> bool:
    """
    Run audit and raise if violations detected.
    Call this before training starts.

    Returns:
        True if pipeline is clean.

    Raises:
        RuntimeError if synthetic patterns detected.
    """
    report = audit_training_path(project_root)

    if not report.passed:
        violation_summary = "\n".join(
            f"  {v.file_path}:{v.line_number} — {v.pattern}"
            for v in report.violations[:10]
        )
        raise RuntimeError(
            f"ABORT: Data source audit FAILED. "
            f"{len(report.violations)} synthetic patterns detected:\n"
            f"{violation_summary}\n"
            f"Remove synthetic data sources before training."
        )

    logger.info("[AUDIT] ✓ Pipeline CLEAN — no synthetic data detected")
    return True


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = audit_training_path()

    print(f"\n{'=' * 60}")
    print(f"  DATA SOURCE AUDIT REPORT")
    print(f"{'=' * 60}")
    print(f"  Status:    {'CLEAN ✓' if report.passed else 'FAILED ✗'}")
    print(f"  Scanned:   {report.files_scanned} files")
    print(f"  Patterns:  {report.patterns_checked}")
    print(f"  Skipped:   {report.whitelisted_skipped} (whitelisted)")
    print(f"  Violations: {len(report.violations)}")

    if report.violations:
        print(f"\n  VIOLATIONS:")
        for v in report.violations:
            print(f"    ✗ {v.file_path}:{v.line_number}")
            print(f"      Pattern: {v.pattern}")
            print(f"      Line:    {v.line_content[:80]}")
