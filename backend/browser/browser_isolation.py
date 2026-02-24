"""
Browser Isolation Guard — Edge Headless Launch Config & Enforcement.

Mirrors C++ edge_headless_engine.cpp logic in Python.

RULES:
  - No Microsoft login
  - No session persistence outside project dir
  - Domain whitelist enforcement
  - Isolated automation profile

GOVERNANCE: MODE-A only. Zero decision authority.
"""
import os
import subprocess
import logging
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, FrozenSet
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =========================================================================
# DOMAIN WHITELIST (mirrors C++ engine)
# =========================================================================

ALLOWED_DOMAINS: FrozenSet[str] = frozenset([
    # NVD / CVE feeds
    "nvd.nist.gov",
    "services.nvd.nist.gov",
    "cve.org",
    "www.cve.org",
    "cveawg.mitre.org",
    # OWASP
    "owasp.org",
    "www.owasp.org",
    "cheatsheetseries.owasp.org",
    # MITRE CWE
    "cwe.mitre.org",
    "capec.mitre.org",
    # CVE details
    "www.cvedetails.com",
    "cvedetails.com",
    # Whitelisted security blogs
    "portswigger.net",
    "www.portswigger.net",
    "blog.cloudflare.com",
    "security.googleblog.com",
    "msrc.microsoft.com",
])

# Blocked URL patterns
BLOCKED_URL_PATTERNS = [
    "login", "signin", "signup", "register", "oauth", "auth/",
    "account", "password", "credential", "session",
    ".exe", ".msi", ".bat", ".ps1", ".sh",
    "exploit-db.com", "pastebin.com",
]


# =========================================================================
# EDGE LAUNCH CONFIG
# =========================================================================

@dataclass
class EdgeLaunchConfig:
    edge_path: str = "msedge"
    user_data_dir: str = "./automation_profile"
    timeout_seconds: int = 15
    max_response_bytes: int = 131072  # 128KB
    headless: bool = True

    def build_args(self, url: str) -> List[str]:
        args = [self.edge_path]
        if self.headless:
            args.append("--headless=new")
        args.extend([
            "--disable-extensions",
            "--disable-sync",
            "--disable-features=NetworkService",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-background-networking",
            "--disable-translate",
            "--disable-component-update",
            "--no-sandbox",
            "--inprivate",
            "--dump-dom",
            url,
        ])
        return args


# =========================================================================
# ISOLATION CHECKS
# =========================================================================

@dataclass
class IsolationCheckResult:
    domain_allowed: bool = False
    url_not_blocked: bool = False
    https_only: bool = False
    no_login: bool = True
    no_sync: bool = True
    isolated_profile: bool = True
    all_passed: bool = False
    rejection_reason: str = ""


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    if "://" in url:
        url = url.split("://", 1)[1]
    url = url.split("/", 1)[0]
    url = url.split(":", 1)[0]  # Strip port
    return url.lower()


def check_isolation(url: str,
                    config: Optional[EdgeLaunchConfig] = None) -> IsolationCheckResult:
    """Run all isolation checks on a URL before fetching."""
    if config is None:
        config = EdgeLaunchConfig()

    result = IsolationCheckResult()

    # 1. HTTPS only
    result.https_only = url.startswith("https://")
    if not result.https_only:
        result.rejection_reason = "Only HTTPS URLs allowed"
        return result

    # 2. Domain whitelist
    domain = extract_domain(url)
    result.domain_allowed = domain in ALLOWED_DOMAINS
    if not result.domain_allowed:
        result.rejection_reason = f"Domain '{domain}' not in whitelist"
        return result

    # 3. Blocked URL patterns
    url_lower = url.lower()
    for pattern in BLOCKED_URL_PATTERNS:
        if pattern in url_lower:
            result.url_not_blocked = False
            result.rejection_reason = f"URL contains blocked pattern: {pattern}"
            return result
    result.url_not_blocked = True

    # 4. Profile isolation
    result.isolated_profile = (
        config.user_data_dir != "Default" and
        bool(config.user_data_dir)
    )
    result.no_login = config.headless
    result.no_sync = True  # --disable-sync always set

    result.all_passed = all([
        result.domain_allowed,
        result.url_not_blocked,
        result.https_only,
        result.no_login,
        result.no_sync,
        result.isolated_profile,
    ])

    return result


# =========================================================================
# SAFE FETCH (subprocess Edge call)
# =========================================================================

@dataclass
class FetchResult:
    success: bool = False
    url: str = ""
    content: str = ""
    error: str = ""
    elapsed_ms: float = 0.0
    content_bytes: int = 0
    content_hash: str = ""


def safe_fetch(url: str,
               config: Optional[EdgeLaunchConfig] = None) -> FetchResult:
    """Fetch URL content using isolated headless Edge."""
    if config is None:
        config = EdgeLaunchConfig()

    result = FetchResult(url=url)

    # Isolation check
    iso = check_isolation(url, config)
    if not iso.all_passed:
        result.error = f"BLOCKED: {iso.rejection_reason}"
        logger.warning(f"Fetch blocked: {url} — {iso.rejection_reason}")
        return result

    import time
    t_start = time.monotonic()

    try:
        args = config.build_args(url)
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )

        elapsed = (time.monotonic() - t_start) * 1000
        result.elapsed_ms = round(elapsed, 1)

        raw = proc.stdout[:config.max_response_bytes]
        if not raw:
            result.error = "No content returned"
            return result

        result.content = raw
        result.content_bytes = len(raw)
        result.content_hash = hashlib.sha256(
            raw.encode('utf-8', errors='ignore')).hexdigest()[:32]
        result.success = True

    except subprocess.TimeoutExpired:
        result.error = "Fetch timed out"
    except FileNotFoundError:
        result.error = "Edge browser not found at configured path"
    except Exception as e:
        result.error = "Fetch error: internal failure"
        logger.exception("Safe fetch failed for %s", url)

    return result


# =========================================================================
# SELF-TEST
# =========================================================================

def run_isolation_tests():
    """Run isolation layer self-tests."""
    logger.info("=" * 60)
    logger.info("BROWSER ISOLATION TESTS")
    logger.info("=" * 60)

    tests_passed = 0
    tests_failed = 0

    def check(name, expected, actual):
        nonlocal tests_passed, tests_failed
        if expected == actual:
            tests_passed += 1
            logger.info(f"  PASS: {name}")
        else:
            tests_failed += 1
            logger.info(f"  FAIL: {name} (expected={expected}, got={actual})")

    # Domain whitelist tests
    check("NVD allowed", True,
          check_isolation("https://nvd.nist.gov/vuln/detail/CVE-2024-1234").all_passed)
    check("OWASP allowed", True,
          check_isolation("https://owasp.org/Top10/").all_passed)
    check("MITRE allowed", True,
          check_isolation("https://cwe.mitre.org/data/definitions/79.html").all_passed)
    check("Google blocked", False,
          check_isolation("https://www.google.com/search?q=test").all_passed)
    check("GitHub blocked", False,
          check_isolation("https://github.com/user/repo").all_passed)
    check("Random site blocked", False,
          check_isolation("https://example.com/page").all_passed)

    # URL pattern blocking
    check("Login blocked", False,
          check_isolation("https://nvd.nist.gov/login").all_passed)
    check("OAuth blocked", False,
          check_isolation("https://owasp.org/oauth/callback").all_passed)
    check("Exe blocked", False,
          check_isolation("https://nvd.nist.gov/download.exe").all_passed)

    # HTTP blocked (HTTPS only)
    check("HTTP blocked", False,
          check_isolation("http://nvd.nist.gov/vuln/detail/CVE-2024-1234").all_passed)

    # Profile isolation
    config = EdgeLaunchConfig(user_data_dir="Default")
    check("Default profile blocked", False,
          check_isolation("https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
                          config).all_passed)

    logger.info(f"\n  Results: {tests_passed} passed, {tests_failed} failed")
    logger.info("=" * 60)

    return tests_failed == 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [BROWSER-ISO] %(message)s')
    import sys
    ok = run_isolation_tests()
    sys.exit(0 if ok else 1)
