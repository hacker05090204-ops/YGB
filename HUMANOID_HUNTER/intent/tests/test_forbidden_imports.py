"""
Phase-33 Forbidden Imports Tests.

Tests that forbidden imports are not present in intent module.
"""
import ast
import pytest
from pathlib import Path


# Path to intent module
INTENT_MODULE_PATH = Path(__file__).parent.parent


# Forbidden imports per Phase-33 requirements
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

# Forbidden future phase imports
FORBIDDEN_PHASE_IMPORTS = [
    "phase34",
    "phase35",
    "phase36",
]


def get_module_files() -> list[Path]:
    """Get all Python files in intent module (excluding tests)."""
    files = []
    for file in INTENT_MODULE_PATH.glob("*.py"):
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
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert node.module != module, \
                            f"Forbidden 'from {module}' import in {filepath}"


class TestForbiddenPatterns:
    """Test that forbidden code patterns are not present."""
    
    def test_no_async_def(self) -> None:
        """No async def in intent module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            assert "async def" not in content, \
                f"Forbidden 'async def' found in {filepath}"
    
    def test_no_await(self) -> None:
        """No await in intent module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "await " in line:
                    assert False, f"Forbidden 'await' found in {filepath}:{i}"
    
    def test_no_exec(self) -> None:
        """No exec() in intent module."""
        for filepath in get_module_files():
            content = get_source_content(filepath)
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "exec":
                        assert False, f"Forbidden 'exec()' found in {filepath}"
    
    def test_no_eval(self) -> None:
        """No eval() in intent module."""
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


class TestNoAIDecisionLogic:
    """Test that no AI decision logic is present."""
    
    def test_no_ai_libraries(self) -> None:
        """No AI/ML libraries imported."""
        ai_libraries = ["openai", "anthropic", "langchain", "transformers", "torch", "tensorflow"]
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            for lib in ai_libraries:
                assert lib not in content, \
                    f"AI library '{lib}' found in {filepath}"
    
    def test_no_auto_decide_functions(self) -> None:
        """No auto-decide or auto-continue functions."""
        forbidden_patterns = ["auto_decide", "auto_continue", "auto_select", "ai_decision"]
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            for pattern in forbidden_patterns:
                assert pattern not in content.lower(), \
                    f"Forbidden pattern '{pattern}' found in {filepath}"


class TestNoExecutionLogic:
    """Test that no execution logic is present."""
    
    def test_no_execute_functions(self) -> None:
        """No execute functions in intent module."""
        forbidden = ["execute_instruction", "run_instruction", "do_execute"]
        
        for filepath in get_module_files():
            content = get_source_content(filepath)
            for pattern in forbidden:
                assert pattern not in content.lower(), \
                    f"Execution pattern '{pattern}' found in {filepath}"
