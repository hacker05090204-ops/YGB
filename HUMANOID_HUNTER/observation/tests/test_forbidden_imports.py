"""
Phase-31 Forbidden Imports Tests.

Tests that forbidden imports are not present in observation module.
"""
import ast
import pytest
from pathlib import Path


# Path to observation module
OBSERVATION_MODULE_PATH = Path(__file__).parent.parent


# Forbidden imports per Phase-31 requirements
FORBIDDEN_MODULES = [
    "os",
    "subprocess",
    "socket",
    "asyncio",
    "playwright",
    "selenium",
    "requests",
    "httpx",
]

# Forbidden patterns
FORBIDDEN_PATTERNS = [
    "async def",
    "await ",
    "exec(",
    "eval(",
]

# Forbidden future phase imports
FORBIDDEN_PHASE_IMPORTS = [
    "phase32",
    "phase33",
    "phase34",
    "phase35",
]


def get_module_files() -> list[Path]:
    """Get all Python files in observation module (excluding tests)."""
    files = []
    for file in OBSERVATION_MODULE_PATH.glob("*.py"):
        if file.name != "__init__.py" or file.parent == OBSERVATION_MODULE_PATH:
            files.append(file)
    return [f for f in files if "tests" not in str(f)]


def get_source_content(filepath: Path) -> str:
    """Read source file content."""
    return filepath.read_text(encoding="utf-8")


class TestForbiddenModuleImports:
    """Test that forbidden modules are not imported."""
    
    @pytest.mark.parametrize("module", FORBIDDEN_MODULES)
    def test_forbidden_module_not_imported(self, module: str) -> None:
        """Verify forbidden module is not imported."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            
            # Parse AST to check imports
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name != module, \
                            f"Forbidden import '{module}' found in {filepath}"
                        assert not alias.name.startswith(f"{module}."), \
                            f"Forbidden import '{module}.*' found in {filepath}"
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert node.module != module, \
                            f"Forbidden 'from {module}' import in {filepath}"
                        assert not node.module.startswith(f"{module}."), \
                            f"Forbidden 'from {module}.*' import in {filepath}"


class TestForbiddenPatterns:
    """Test that forbidden code patterns are not present."""
    
    def test_no_async_def(self) -> None:
        """No async def in observation module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            assert "async def" not in content, \
                f"Forbidden 'async def' found in {filepath}"
    
    def test_no_await(self) -> None:
        """No await in observation module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            # Check for await that's not in a comment
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "await " in line:
                    assert False, f"Forbidden 'await' found in {filepath}:{i}"
    
    def test_no_exec(self) -> None:
        """No exec() in observation module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "exec":
                        assert False, f"Forbidden 'exec()' found in {filepath}"
    
    def test_no_eval(self) -> None:
        """No eval() in observation module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "eval":
                        assert False, f"Forbidden 'eval()' found in {filepath}"


class TestForbiddenPhaseImports:
    """Test that future phase imports are not present."""
    
    @pytest.mark.parametrize("phase", FORBIDDEN_PHASE_IMPORTS)
    def test_no_future_phase_import(self, phase: str) -> None:
        """No future phase imports."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            assert phase not in content, \
                f"Forbidden future phase '{phase}' reference in {filepath}"


class TestAllowedImportsOnly:
    """Test that only allowed imports are used."""
    
    def test_imports_are_from_allowed_sources(self) -> None:
        """All imports are from allowed sources."""
        allowed_modules = {
            "enum",
            "dataclasses",
            "typing",
            "hashlib",
            "uuid",
            # Internal imports are allowed
            "observation_types",
            "observation_context",
            "observation_engine",
        }
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        base_module = alias.name.split(".")[0]
                        assert base_module in allowed_modules, \
                            f"Unexpected import '{alias.name}' in {filepath}"
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        base_module = node.module.split(".")[0]
                        # Allow relative imports (start with .)
                        if not node.module.startswith("."):
                            assert base_module in allowed_modules, \
                                f"Unexpected 'from {node.module}' import in {filepath}"


class TestNoNetworkCapability:
    """Test that no network capability exists."""
    
    def test_no_http_patterns(self) -> None:
        """No HTTP-related patterns."""
        http_patterns = ["http://", "https://", "urllib", "http.client"]
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            for pattern in http_patterns:
                assert pattern not in content, \
                    f"Network pattern '{pattern}' found in {filepath}"
    
    def test_no_socket_patterns(self) -> None:
        """No socket-related patterns."""
        socket_patterns = ["socket.", "connect(", "bind(", "listen("]
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            # Skip test files
            if "test" in filepath.name:
                continue
            for pattern in socket_patterns:
                # Only check if not in a docstring or comment
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    stripped = line.lstrip()
                    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    if pattern in line and "socket" in line:
                        assert False, f"Socket pattern '{pattern}' found in {filepath}:{i}"


class TestNoFileSystemAccess:
    """Test that no file system access exists."""
    
    def test_no_open_calls(self) -> None:
        """No open() calls for file access."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "open":
                        assert False, f"Forbidden 'open()' found in {filepath}"
    
    def test_no_pathlib_write(self) -> None:
        """No pathlib write operations."""
        write_patterns = [".write_text(", ".write_bytes(", ".mkdir(", ".touch("]
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            for pattern in write_patterns:
                assert pattern not in content, \
                    f"File write pattern '{pattern}' found in {filepath}"
