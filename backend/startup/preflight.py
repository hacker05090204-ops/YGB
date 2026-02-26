"""
Startup Preflight Check — Production Readiness Validator

Verifies all critical subsystems before allowing service start:
  1. Required report files exist
  2. HDD writable
  3. GPU query functional (nvidia-smi, 2s timeout)
  4. Precision baseline loaded (reports/runtime_state.json)
  5. Drift baseline loaded
  6. Scope registry valid (data/target_programs.json)

On critical failure → refuse service start + log fatal error.

NO mock data. NO auto-approve. NO bypass.
"""

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class PreflightError(RuntimeError):
    """Raised when a critical preflight check fails — service must NOT start."""
    pass


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    critical: bool = True


@dataclass
class PreflightReport:
    passed: bool
    checks: List[CheckResult] = field(default_factory=list)
    fatal_errors: List[str] = field(default_factory=list)


# =========================================================================
# INDIVIDUAL CHECKS
# =========================================================================

def check_report_directory() -> CheckResult:
    """Verify reports/ directory exists."""
    reports = Path("reports")
    if reports.is_dir():
        return CheckResult("report_directory", True, "reports/ exists")
    return CheckResult("report_directory", False,
                       "reports/ directory missing", critical=True)


def check_hdd_writable() -> CheckResult:
    """Verify filesystem is writable by creating and deleting a temp file."""
    try:
        reports = Path("reports")
        reports.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=str(reports), prefix="preflight_")
        os.close(fd)
        os.unlink(path)
        return CheckResult("hdd_writable", True, "Filesystem writable")
    except Exception as e:
        return CheckResult("hdd_writable", False,
                           f"Filesystem not writable: {e}", critical=True)


def check_gpu_query() -> CheckResult:
    """Verify nvidia-smi responds within 2 seconds."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[:100]
            return CheckResult("gpu_query", False,
                               f"nvidia-smi exit code {result.returncode}: {stderr}",
                               critical=False)  # GPU is optional
        gpu_info = result.stdout.strip()
        if not gpu_info:
            return CheckResult("gpu_query", False,
                               "nvidia-smi returned empty output",
                               critical=False)
        return CheckResult("gpu_query", True, f"GPU available: {gpu_info[:80]}")

    except FileNotFoundError:
        return CheckResult("gpu_query", False,
                           "nvidia-smi not found — no GPU driver installed",
                           critical=False)
    except subprocess.TimeoutExpired:
        return CheckResult("gpu_query", False,
                           "nvidia-smi timed out (>2s)",
                           critical=False)
    except Exception as e:
        return CheckResult("gpu_query", False,
                           f"GPU query error: {e}",
                           critical=False)


def check_precision_baseline() -> CheckResult:
    """Verify runtime state file exists and is parseable."""
    state_path = Path("reports/runtime_state.json")
    if not state_path.exists():
        return CheckResult("precision_baseline", False,
                           "reports/runtime_state.json missing — will initialize baseline mode",
                           critical=False)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        version = data.get("version")
        precision = data.get("rolling_precision")
        if version != 1:
            return CheckResult("precision_baseline", False,
                               f"State version mismatch: {version}",
                               critical=False)
        return CheckResult("precision_baseline", True,
                           f"Precision baseline loaded: {precision:.4f}")
    except Exception as e:
        return CheckResult("precision_baseline", False,
                           f"Failed to parse runtime state: {e}",
                           critical=False)


def check_drift_baseline() -> CheckResult:
    """Verify drift baseline is present in runtime state."""
    state_path = Path("reports/runtime_state.json")
    if not state_path.exists():
        return CheckResult("drift_baseline", False,
                           "No drift baseline — will calibrate from scratch",
                           critical=False)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        kl_ema = data.get("kl_baseline_ema", 0.0)
        if kl_ema <= 0.0:
            return CheckResult("drift_baseline", False,
                               "KL baseline EMA is zero — will calibrate",
                               critical=False)
        return CheckResult("drift_baseline", True,
                           f"Drift baseline loaded: KL_EMA={kl_ema:.6f}")
    except Exception as e:
        return CheckResult("drift_baseline", False,
                           f"Failed to parse drift baseline: {e}",
                           critical=False)


def check_scope_registry() -> CheckResult:
    """Verify target programs registry exists and is valid JSON array."""
    registry_path = Path("data/target_programs.json")
    # Also check phase49 location
    alt_path = Path("impl_v1/phase49/data/target_programs.json")

    target = registry_path if registry_path.exists() else alt_path

    if not target.exists():
        return CheckResult("scope_registry", False,
                           "target_programs.json not found",
                           critical=True)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return CheckResult("scope_registry", False,
                               f"target_programs.json is not a JSON array: {type(data).__name__}",
                               critical=True)
        return CheckResult("scope_registry", True,
                           f"Scope registry valid: {len(data)} programs")
    except json.JSONDecodeError as e:
        return CheckResult("scope_registry", False,
                           f"Invalid JSON in target_programs.json: {e}",
                           critical=True)


# =========================================================================
# BOOT SUMMARY — ENABLED/DISABLED/BLOCKED per feature
# =========================================================================

def check_secrets() -> CheckResult:
    """Verify strong secrets are set (≥32 chars)."""
    required = {
        "JWT_SECRET": os.environ.get("JWT_SECRET", ""),
        "YGB_HMAC_SECRET": os.environ.get("YGB_HMAC_SECRET", ""),
        "YGB_VIDEO_JWT_SECRET": os.environ.get("YGB_VIDEO_JWT_SECRET", ""),
    }
    weak = []
    for name, val in required.items():
        if len(val) < 32:
            weak.append(f"{name} ({len(val)} chars)")
    if weak:
        return CheckResult(
            "secrets", False,
            f"Weak/missing secrets: {', '.join(weak)} — need ≥32 chars",
            critical=False,
        )
    return CheckResult("secrets", True, "All required secrets ≥32 chars")


def check_boot_summary() -> CheckResult:
    """Generate boot summary showing ENABLED/DISABLED/BLOCKED per feature."""
    profile = os.environ.get("YGB_PROFILE", "PRIVACY")
    features = {}

    # CVE Pipeline
    features["cve_pipeline"] = "ENABLED"

    # SMTP
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "") or os.environ.get("SMTP_PASSWORD", "")
    if smtp_host and smtp_user and smtp_pass:
        features["smtp_alerts"] = "ENABLED"
    elif profile == "CONNECTED":
        features["smtp_alerts"] = "BLOCKED (SMTP_HOST/SMTP_USER/SMTP_PASS required)"
    else:
        features["smtp_alerts"] = "DISABLED (privacy mode)"

    # GitHub OAuth
    gh_id = os.environ.get("GITHUB_CLIENT_ID", "")
    gh_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")
    gh_redirect = os.environ.get("GITHUB_REDIRECT_URI", "")
    if gh_id and gh_secret:
        features["github_oauth"] = "ENABLED"
    elif profile == "CONNECTED":
        features["github_oauth"] = "BLOCKED (GITHUB_CLIENT_ID/SECRET required)"
    else:
        features["github_oauth"] = "DISABLED (privacy mode)"

    # Google Drive
    gdrive = os.environ.get("GOOGLE_DRIVE_CREDENTIALS", "")
    if gdrive and Path(gdrive).exists() if gdrive else False:
        features["google_drive_backup"] = "ENABLED"
    elif gdrive:
        features["google_drive_backup"] = "BLOCKED (credentials file not found)"
    else:
        features["google_drive_backup"] = "DISABLED (no credentials)"

    # CVE API Key
    cve_key = os.environ.get("CVE_API_KEY", "")
    if cve_key:
        features["cve_api_key"] = "ENABLED (NVD rate limit bypass)"
    else:
        features["cve_api_key"] = "DISABLED (using free tier)"

    # Training
    strict = os.environ.get("YGB_STRICT_REAL_MODE", "true").lower() != "false"
    features["strict_real_mode"] = "ENABLED" if strict else "DISABLED (lab mode)"

    # Accelerator
    accel = os.environ.get("ACCELERATOR_API_URL", "")
    features["accelerator"] = "ENABLED" if accel else "DISABLED"

    summary_lines = [f"  {k}: {v}" for k, v in features.items()]
    summary = f"Boot Summary (profile={profile}):\n" + "\n".join(summary_lines)

    blocked = [v for v in features.values() if v.startswith("BLOCKED")]
    if blocked and profile == "CONNECTED":
        return CheckResult(
            "boot_summary", False,
            summary,
            critical=False,
        )

    logger.info(summary)
    return CheckResult("boot_summary", True, summary)


# =========================================================================
# PREFLIGHT RUNNER
# =========================================================================

def run_preflight() -> PreflightReport:
    """Run all preflight checks. Raises PreflightError if critical check fails."""
    checks = [
        check_report_directory(),
        check_hdd_writable(),
        check_gpu_query(),
        check_precision_baseline(),
        check_drift_baseline(),
        check_scope_registry(),
        check_secrets(),
        check_boot_summary(),
    ]

    fatal_errors = []
    for check in checks:
        level = "PASS" if check.passed else ("FATAL" if check.critical else "WARN")
        msg = f"[{level}] {check.name}: {check.detail}"
        if check.passed:
            logger.info(msg)
        elif check.critical:
            logger.critical(msg)
            fatal_errors.append(msg)
        else:
            logger.warning(msg)

    report = PreflightReport(
        passed=len(fatal_errors) == 0,
        checks=checks,
        fatal_errors=fatal_errors,
    )

    if not report.passed:
        error_msg = (
            f"PREFLIGHT FAILED — {len(fatal_errors)} critical error(s):\n"
            + "\n".join(f"  • {e}" for e in fatal_errors)
        )
        logger.critical(error_msg)
        raise PreflightError(error_msg)

    logger.info(f"PREFLIGHT PASSED — {len(checks)} checks, all clear.")
    return report


# =========================================================================
# SELF-TEST
# =========================================================================

def _self_test():
    """Quick validation that preflight checks can execute."""
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    try:
        report = run_preflight()
        print(f"\nPreflight result: {'PASS' if report.passed else 'FAIL'}")
        for c in report.checks:
            status = "✓" if c.passed else ("✗" if c.critical else "⚠")
            print(f"  {status} {c.name}: {c.detail}")
        sys.exit(0 if report.passed else 1)
    except PreflightError as e:
        print(f"\nPreflight FATAL: {e}")
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
