"""
Test No Forbidden Behavior - Phase-01 Core
REIMPLEMENTED-2026

Tests to verify that NO forbidden patterns exist in Phase-01.
These tests scan the source code for forbidden symbols IN CODE CONTEXT ONLY.
Documentation describing forbidden patterns is allowed.

Forbidden patterns (in code, not docs):
- auto_* prefixes as variable/function names
- network, socket, http, requests imports
- subprocess, os.system usage
- threading, multiprocessing imports
- async/await keywords
"""

import pytest
import os
import re
from pathlib import Path


# Path to phase01_core source files
PHASE01_PATH = Path(__file__).parent.parent


class TestNoForbiddenSymbols:
    """Tests to ensure no forbidden symbols exist in Phase-01 source."""

    def get_source_files(self):
        """Get all Python source files in phase01_core (excluding tests)."""
        source_files = []
        for py_file in PHASE01_PATH.glob('*.py'):
            if py_file.name != '__init__.py' or py_file.read_text().strip():
                source_files.append(py_file)
        return source_files

    def read_all_source(self):
        """Read content of all source files."""
        content = ""
        for py_file in self.get_source_files():
            content += py_file.read_text()
        return content

    def get_code_only(self, content):
        """
        Extract only code lines, excluding comments and docstrings.
        This allows documentation to mention forbidden terms while
        ensuring they don't appear in actual code.
        """
        lines = content.split('\n')
        code_lines = []
        in_docstring = False
        docstring_char = None
        
        for line in lines:
            stripped = line.strip()
            
            # Skip comment lines
            if stripped.startswith('#'):
                continue
            
            # Handle docstrings
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                        # Single line docstring
                        continue
                    in_docstring = True
                    continue
            else:
                if docstring_char in stripped:
                    in_docstring = False
                continue
            
            code_lines.append(line)
        
        return '\n'.join(code_lines)

    def test_no_auto_prefix_variables(self):
        """Verify no auto_* variable/function definitions exist."""
        for py_file in self.get_source_files():
            content = py_file.read_text()
            code_only = self.get_code_only(content)
            
            # Match auto_ as variable assignment or function def
            matches = re.findall(r'\bauto_\w+\s*=', code_only)
            matches += re.findall(r'def\s+auto_\w+', code_only)
            
            assert len(matches) == 0, f"Found forbidden auto_* in {py_file.name}: {matches}"

    def test_no_thread_import(self):
        """Verify no threading import exists."""
        content = self.read_all_source()
        
        matches = re.findall(r'\bimport\s+threading\b', content)
        matches += re.findall(r'\bfrom\s+threading\b', content)
        
        assert len(matches) == 0, f"Found forbidden threading imports: {matches}"

    def test_no_async_keyword(self):
        """Verify no async/await keywords exist."""
        content = self.read_all_source()
        
        async_matches = re.findall(r'\basync\s+def\b', content)
        await_matches = re.findall(r'\bawait\b', content)
        
        assert len(async_matches) == 0, f"Found forbidden 'async def': {async_matches}"
        assert len(await_matches) == 0, f"Found forbidden 'await': {await_matches}"

    def test_no_subprocess_import(self):
        """Verify no subprocess import exists."""
        content = self.read_all_source()
        
        matches = re.findall(r'\bimport\s+subprocess\b', content)
        matches += re.findall(r'\bfrom\s+subprocess\b', content)
        
        assert len(matches) == 0, f"Found forbidden subprocess imports: {matches}"

    def test_no_os_system_call(self):
        """Verify no os.system calls exist."""
        content = self.read_all_source()
        
        matches = re.findall(r'\bos\.system\b', content)
        
        assert len(matches) == 0, f"Found forbidden os.system calls: {matches}"

    def test_no_socket_import(self):
        """Verify no socket import exists."""
        content = self.read_all_source()
        
        matches = re.findall(r'\bimport\s+socket\b', content)
        matches += re.findall(r'\bfrom\s+socket\b', content)
        
        assert len(matches) == 0, f"Found forbidden socket imports: {matches}"

    def test_no_http_import(self):
        """Verify no http/requests imports exist."""
        content = self.read_all_source()
        
        matches = re.findall(r'\bimport\s+requests\b', content)
        matches += re.findall(r'\bimport\s+http\b', content)
        matches += re.findall(r'\bimport\s+urllib\b', content)
        
        assert len(matches) == 0, f"Found forbidden http imports: {matches}"

    def test_no_multiprocessing_import(self):
        """Verify no multiprocessing import exists."""
        content = self.read_all_source()
        
        matches = re.findall(r'\bimport\s+multiprocessing\b', content)
        matches += re.findall(r'\bfrom\s+multiprocessing\b', content)
        
        assert len(matches) == 0, f"Found forbidden multiprocessing imports: {matches}"


class TestNoForbiddenImports:
    """Tests to verify only safe imports are used."""

    def test_only_stdlib_imports(self):
        """Verify only Python standard library imports are used."""
        # Allowed stdlib modules for Phase-01
        allowed_imports = {
            'dataclasses',
            'typing',
            'enum',
            '__future__',
        }
        
        source_files = list(PHASE01_PATH.glob('*.py'))
        
        for py_file in source_files:
            content = py_file.read_text()
            
            # Find all import statements
            imports = re.findall(r'^import\s+(\w+)', content, re.MULTILINE)
            imports += re.findall(r'^from\s+(\w+)', content, re.MULTILINE)
            
            for imp in imports:
                # Skip relative imports (from . or from ..)
                if imp.startswith('.'):
                    continue
                # Skip internal phase01 imports
                if imp.startswith('phase01') or imp == 'python':
                    continue
                    
                assert imp in allowed_imports, \
                    f"File {py_file.name} has forbidden import: {imp}"


class TestNoExecutionLogic:
    """Tests to verify Phase-01 contains no execution logic."""

    def test_no_main_block(self):
        """Verify no if __name__ == '__main__' blocks exist."""
        source_files = list(PHASE01_PATH.glob('*.py'))
        
        for py_file in source_files:
            content = py_file.read_text()
            
            matches = re.findall(r'if\s+__name__\s*==\s*["\']__main__["\']', content)
            
            assert len(matches) == 0, \
                f"File {py_file.name} has forbidden __main__ block"

    def test_no_file_operations(self):
        """Verify no file operations exist in code (not docs)."""
        source_files = list(PHASE01_PATH.glob('*.py'))
        
        for py_file in source_files:
            content = py_file.read_text()
            
            # Check for open() calls in code context
            lines = content.split('\n')
            in_docstring = False
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # Skip comments
                if stripped.startswith('#'):
                    continue
                    
                # Handle docstrings
                if '"""' in stripped or "'''" in stripped:
                    if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                        in_docstring = not in_docstring
                    continue
                
                if in_docstring:
                    continue
                    
                if re.search(r'\bopen\s*\(', line):
                    assert False, \
                        f"File {py_file.name} line {i+1} has forbidden open() call"


class TestInvariantConstants:
    """Tests to verify invariant-related constants are properly defined."""

    def test_no_scoring_constant_is_false(self):
        """Verify INVARIANT_NO_SCORING_OR_RANKING is True (scoring forbidden)."""
        from python.phase01_core.invariants import INVARIANT_NO_SCORING_OR_RANKING
        assert INVARIANT_NO_SCORING_OR_RANKING is True

    def test_no_background_constant_is_false(self):
        """Verify INVARIANT_NO_BACKGROUND_ACTIONS is True (background forbidden)."""
        from python.phase01_core.invariants import INVARIANT_NO_BACKGROUND_ACTIONS
        assert INVARIANT_NO_BACKGROUND_ACTIONS is True

    def test_background_execution_not_allowed(self):
        """Verify BACKGROUND_EXECUTION_ALLOWED is False."""
        from python.phase01_core.constants import BACKGROUND_EXECUTION_ALLOWED
        assert BACKGROUND_EXECUTION_ALLOWED is False

    def test_autonomous_execution_not_allowed(self):
        """Verify AUTONOMOUS_EXECUTION_ALLOWED is False."""
        from python.phase01_core.constants import AUTONOMOUS_EXECUTION_ALLOWED
        assert AUTONOMOUS_EXECUTION_ALLOWED is False
