"""
Test: No duplicate route definitions in api/server.py.

Parses the source file for @app.get/post/put/delete/patch/websocket decorators
and fails if the same (method, path) pair appears more than once.
"""

import re
import pytest
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).parent.parent.parent
SERVER_FILE = PROJECT_ROOT / "api" / "server.py"


def _extract_route_declarations(source: str):
    """Extract (method, path) tuples from FastAPI route decorators."""
    # Pattern: @app.{method}("{path}")  or @app.{method}('/path')
    pattern = re.compile(
        r'@app\.(get|post|put|delete|patch|websocket)\(\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    return [(m.group(1).upper(), m.group(2)) for m in pattern.finditer(source)]


class TestNoDuplicateRoutes:
    """Regression test: no duplicate route paths per HTTP method."""

    def test_server_file_exists(self):
        assert SERVER_FILE.exists(), f"Server file not found: {SERVER_FILE}"

    def test_no_duplicate_routes(self):
        """Each (method, path) pair must appear at most once."""
        source = SERVER_FILE.read_text(errors="ignore")
        routes = _extract_route_declarations(source)

        counts = Counter(routes)
        duplicates = {route: count for route, count in counts.items() if count > 1}

        if duplicates:
            lines = []
            for (method, path), count in sorted(duplicates.items()):
                lines.append(f"  {method} {path} — declared {count} times")
            pytest.fail(
                "Duplicate route declarations found in api/server.py:\n"
                + "\n".join(lines)
            )

    def test_no_duplicate_function_names(self):
        """Route handler function names must be unique."""
        source = SERVER_FILE.read_text(errors="ignore")
        # Find all async def and def after @app decorators
        pattern = re.compile(
            r'@app\.\w+\([^)]+\)\s*\n(?:@app\.\w+\([^)]+\)\s*\n)*'
            r'async\s+def\s+(\w+)|'
            r'@app\.\w+\([^)]+\)\s*\n(?:@app\.\w+\([^)]+\)\s*\n)*'
            r'def\s+(\w+)',
        )
        names = []
        for m in pattern.finditer(source):
            name = m.group(1) or m.group(2)
            if name:
                names.append(name)

        counts = Counter(names)
        duplicates = {name: count for name, count in counts.items() if count > 1}

        if duplicates:
            lines = [f"  {name} — defined {count} times" for name, count in sorted(duplicates.items())]
            pytest.fail(
                "Duplicate route handler names found:\n"
                + "\n".join(lines)
            )
