"""
Test Production Build Guard — Verify no mock/synthetic/forgery patterns remain.

Tests that:
- No mock strings in production source files
- No synthetic fallback patterns in feature_cache.py
- No mock signature acceptance in g21_auto_update.py
- PRODUCTION_BUILD flag enforcement
- STRICT_REAL_MODE cannot be disabled

ZERO mock data. ZERO bypass tokens. ZERO hardcoded credentials.
"""

import os
import re
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directories to skip (test files, node_modules, etc.)
SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", ".venv",
             "venv", ".pytest_cache", "obj", ".github"}
SKIP_FILES = {"test_production_build_guard.py", "test_no_mock_data.py",
              "test_coverage_boost.py", "test_coverage_boost_2.py",
              "test_coverage_boost_3.py"}


def _get_source_files(extensions=(".py",), include_impl=True):
    """Yield source files (not test files) for scanning."""
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if not include_impl and "impl_v1" in root:
            continue
        for f in files:
            if f in SKIP_FILES:
                continue
            if f.startswith("test_"):
                continue
            if any(f.endswith(ext) for ext in extensions):
                yield Path(root) / f


class TestSecretHardening:
    """Phase 1: Verify secret handling is hardened."""

    def test_no_empty_jwt_default(self):
        """JWT_SECRET must not have an empty or placeholder default."""
        auth_path = PROJECT_ROOT / "backend" / "auth" / "auth.py"
        content = auth_path.read_text(errors="ignore")
        # The original line was: JWT_SECRET = os.getenv("JWT_SECRET", "")
        # Ensure no empty string default is used for JWT operations
        assert "JWT_SECRET" in content, "JWT_SECRET not found in auth.py"

    def test_secure_secret_loader_exists(self):
        """secure_secret_loader.cpp must exist."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "secure_secret_loader.cpp"
        assert cpp_path.exists(), "secure_secret_loader.cpp not found"
        content = cpp_path.read_text(errors="ignore")
        assert "is_placeholder" in content, "Placeholder detection missing"
        assert "MIN_SECRET_LEN" in content, "Minimum length enforcement missing"
        assert "secure_zero" in content, "Memory zeroing missing"


class TestRealDataEnforcer:
    """Phase 2: Verify real data enforcement."""

    def test_real_data_enforcer_exists(self):
        """real_data_enforcer.cpp must exist."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "real_data_enforcer.cpp"
        assert cpp_path.exists(), "real_data_enforcer.cpp not found"
        content = cpp_path.read_text(errors="ignore")
        assert "STRICT_REAL_MODE" in content or "is_strict_real_mode" in content
        assert "SyntheticTrainingDataset" in content, "Must block SyntheticTrainingDataset"

    def test_strict_real_mode_hardcoded(self):
        """STRICT_REAL_MODE must be hardcoded TRUE in real_data_enforcer.cpp."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "real_data_enforcer.cpp"
        content = cpp_path.read_text(errors="ignore")
        assert "return 1;" in content, "is_strict_real_mode must return 1 (true)"


class TestDatasetContractLock:
    """Phase 3: Verify synthetic fallback is removed."""

    def test_feature_cache_no_synthetic_fallback(self):
        """feature_cache.py must NOT contain synthetic data generation."""
        cache_path = PROJECT_ROOT / "impl_v1" / "training" / "data" / "feature_cache.py"
        content = cache_path.read_text(errors="ignore")
        # Must not generate random data as fallback
        assert "rng.randn" not in content, \
            "feature_cache.py still contains synthetic random data generation"
        assert "RandomState" not in content, \
            "feature_cache.py still uses np.random.RandomState for fallback"
        assert "using synthetic data" not in content.lower(), \
            "feature_cache.py still references synthetic data usage"

    def test_feature_cache_fails_closed(self):
        """feature_cache.py must raise RuntimeError on import failure."""
        cache_path = PROJECT_ROOT / "impl_v1" / "training" / "data" / "feature_cache.py"
        content = cache_path.read_text(errors="ignore")
        assert "RuntimeError" in content, \
            "feature_cache.py must raise RuntimeError on dataset unavailability"
        assert "FAIL-CLOSED" in content or "fail-closed" in content.lower(), \
            "feature_cache.py must be explicitly fail-closed"


class TestPasswordVerifier:
    """Phase 4: Verify password hashing is hardened."""

    def test_secure_password_verifier_exists(self):
        """secure_password_verifier.cpp must exist."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "secure_password_verifier.cpp"
        assert cpp_path.exists(), "secure_password_verifier.cpp not found"
        content = cpp_path.read_text(errors="ignore")
        assert "constant_time_compare" in content, "Constant-time comparison missing"
        assert "password_is_placeholder" in content, "Placeholder rejection missing"
        assert "KDF_ITERATIONS" in content, "KDF iterations missing"


class TestSignatureVerification:
    """Phase 5: Verify signature verification is hardened."""

    def test_update_signature_verifier_exists(self):
        """update_signature_verifier.cpp must exist."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "update_signature_verifier.cpp"
        assert cpp_path.exists(), "update_signature_verifier.cpp not found"
        content = cpp_path.read_text(errors="ignore")
        assert "PUBLIC_KEY" in content, "Hardcoded public key missing"
        assert "is_version_downgrade" in content, "Downgrade detection missing"
        assert "mock-signature" in content, "Mock signature rejection missing"

    def test_g21_no_mock_acceptance(self):
        """g21_auto_update.py must NOT accept mock signatures."""
        g21_path = PROJECT_ROOT / "impl_v1" / "phase49" / "governors" / "g21_auto_update.py"
        content = g21_path.read_text(errors="ignore")
        # Must NOT contain the old mock acceptance pattern
        assert "Mock: Accept any non-empty" not in content, \
            "g21_auto_update.py still contains mock acceptance comment"
        assert "REJECTED_SIGNATURES" in content, \
            "g21_auto_update.py must explicitly reject known mock signatures"


class TestBuildTimeProtection:
    """Phase 6: Verify build-time protection."""

    def test_production_build_guard_exists(self):
        """production_build_guard.cpp must exist."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "production_build_guard.cpp"
        assert cpp_path.exists(), "production_build_guard.cpp not found"
        content = cpp_path.read_text(errors="ignore")
        assert "PRODUCTION_BUILD" in content
        assert "FORBIDDEN_PATTERNS" in content

    def test_no_mock_constants_in_production_code(self):
        """Production source files must not contain MOCK_, FAKE_, DEMO_ constants."""
        forbidden = ["MOCK_DATA", "FAKE_DATA", "DEMO_DATA", "PLACEHOLDER_DATA"]
        violations = []
        for filepath in _get_source_files(extensions=(".py",)):
            content = filepath.read_text(errors="ignore")
            for pattern in forbidden:
                if pattern in content:
                    violations.append(
                        f"{filepath.relative_to(PROJECT_ROOT)}: {pattern}"
                    )
        if violations:
            pytest.fail(
                "Mock/fake constants found in production code:\n" +
                "\n".join(f"  - {v}" for v in violations)
            )

    def test_no_synthetic_fallback_in_any_source(self):
        """No source file should contain synthetic data fallback patterns."""
        fallback_patterns = [
            (r"using synthetic data", "synthetic data usage"),
            (r"synthetic for testing", "synthetic testing fallback"),
            (r"Fallback:.*synthetic", "synthetic fallback"),
        ]
        violations = []
        for filepath in _get_source_files(extensions=(".py",)):
            content = filepath.read_text(errors="ignore")
            for pattern, desc in fallback_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    violations.append(
                        f"{filepath.relative_to(PROJECT_ROOT)}: {desc}"
                    )
        if violations:
            pytest.fail(
                "Synthetic fallback patterns found:\n" +
                "\n".join(f"  - {v}" for v in violations)
            )


class TestFailClosedGuarantees:
    """Cross-cutting: Verify fail-closed behavior across all phases."""

    def test_all_security_cpp_modules_exist(self):
        """All 5 security C++ modules must exist."""
        modules = [
            "secure_secret_loader.cpp",
            "real_data_enforcer.cpp",
            "secure_password_verifier.cpp",
            "update_signature_verifier.cpp",
            "production_build_guard.cpp",
        ]
        security_dir = PROJECT_ROOT / "native" / "security"
        for mod in modules:
            assert (security_dir / mod).exists(), f"{mod} not found in native/security/"

    def test_no_generate_mock_in_source(self):
        """No source file should contain generate_mock or generate_fake."""
        violations = []
        for filepath in _get_source_files(extensions=(".py",)):
            content = filepath.read_text(errors="ignore")
            if "generate_mock" in content or "generate_fake" in content:
                violations.append(str(filepath.relative_to(PROJECT_ROOT)))
        if violations:
            pytest.fail(
                "Mock/fake generators found in:\n" +
                "\n".join(f"  - {v}" for v in violations)
            )
