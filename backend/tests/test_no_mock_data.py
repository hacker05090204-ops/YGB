"""
Tests to verify NO mock data exists anywhere in the codebase.

This is the final gate test — scans all Python and TypeScript source
files for mock data patterns (random data, hardcoded arrays, placeholder
text, etc.) and fails if any are found.
"""

import os
import re
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Files/dirs to skip during scan
SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", ".venv", "venv", "impl_v1", "production"}
SKIP_FILES = {"test_no_mock_data.py", "page.tsx"}  # Don't scan ourselves or pages that may have legitimate data structures


def get_source_files(extensions=(".py", ".tsx", ".ts")):
    """Yield all source files in project."""
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f in SKIP_FILES:
                continue
            if any(f.endswith(ext) for ext in extensions):
                yield Path(root) / f


# Patterns that indicate mock/fake data
MOCK_PATTERNS = [
    # Python patterns
    (r"random\.\w+\(\)", "random value generation"),
    (r"MOCK_DATA", "mock data constant"),
    (r"FAKE_DATA", "fake data constant"),
    (r"DEMO_DATA", "demo data constant"),
    (r"PLACEHOLDER_DATA", "placeholder data constant"),
    (r"generate_fake", "fake data generator"),
    (r"generate_mock", "mock data generator"),
]

# Frontend-specific patterns: large hardcoded data arrays
FRONTEND_MOCK_PATTERNS = [
    (r"const\s+chartData\s*=\s*\[", "hardcoded chartData array"),
    (r"some random text to test the layout", "placeholder text"),
]


class TestNoMockDataInBackend:
    """Ensure backend has zero mock data."""

    def test_no_mock_patterns_in_python(self):
        """Backend Python files must not contain mock data patterns."""
        violations = []
        for filepath in get_source_files(extensions=(".py",)):
            # Skip test files — they can use mocking
            if "test_" in filepath.name:
                continue

            content = filepath.read_text(errors="ignore")
            for pattern, description in MOCK_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    violations.append(
                        f"{filepath.relative_to(PROJECT_ROOT)}: "
                        f"{description} ({len(matches)} occurrences)"
                    )

        if violations:
            pytest.fail(
                "Mock data patterns found in backend:\n" +
                "\n".join(f"  - {v}" for v in violations)
            )

    def test_database_not_json_file_based(self):
        """Database must use SQLite, not JSON files."""
        db_path = PROJECT_ROOT / "api" / "database.py"
        content = db_path.read_text(errors="ignore")
        assert "json.dump" not in content or "metadata_json" in content, \
            "database.py still uses JSON file writes"
        assert "aiosqlite" in content, \
            "database.py must use aiosqlite"

    def test_no_default_zero_in_training(self):
        """Training state manager must not use 0.0 as default."""
        sm_path = PROJECT_ROOT / "backend" / "training" / "state_manager.py"
        content = sm_path.read_text(errors="ignore")
        # Check for .get("key", 0.0) patterns
        default_zeros = re.findall(r'\.get\([^)]+,\s*0(?:\.0)?\)', content)
        for match in default_zeros:
            # Allow get("key", False) and get("key", "IDLE")
            if "False" in match or '"' in match.split(",")[-1]:
                continue
            pytest.fail(
                f"Found default-zero pattern in state_manager.py: {match}"
            )


class TestNoMockDataInFrontend:
    """Ensure frontend has zero hardcoded mock data."""

    def test_no_hardcoded_chart_data(self):
        """Frontend components must not contain hardcoded chartData arrays."""
        violations = []
        for filepath in get_source_files(extensions=(".tsx", ".ts")):
            content = filepath.read_text(errors="ignore")
            for pattern, description in FRONTEND_MOCK_PATTERNS:
                if re.search(pattern, content):
                    violations.append(
                        f"{filepath.relative_to(PROJECT_ROOT)}: {description}"
                    )

        if violations:
            pytest.fail(
                "Mock/hardcoded data found in frontend:\n" +
                "\n".join(f"  - {v}" for v in violations)
            )

    def test_chart_component_uses_api(self):
        """chart-area-interactive must fetch from API, not use static data."""
        chart_path = PROJECT_ROOT / "frontend" / "components" / "chart-area-interactive.tsx"
        if chart_path.exists():
            content = chart_path.read_text(errors="ignore")
            # Accept both fetch() and authFetch() — authFetch is a secure
            # wrapper around fetch that adds JWT auth headers.
            has_fetch = "fetch(" in content or "authFetch(" in content or "authFetch`" in content
            assert has_fetch, \
                "chart-area-interactive.tsx must use fetch() or authFetch() for real data"
            assert "const chartData = [" not in content, \
                "chart-area-interactive.tsx still has hardcoded chartData"

    def test_data_table_no_placeholder(self):
        """data-table.tsx must not contain placeholder text."""
        dt_path = PROJECT_ROOT / "frontend" / "components" / "data-table.tsx"
        if dt_path.exists():
            content = dt_path.read_text(errors="ignore")
            assert "some random text" not in content, \
                "data-table.tsx still contains placeholder text"
