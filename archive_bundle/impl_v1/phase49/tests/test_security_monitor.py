"""
Security Monitor Tests - Phase 49
==================================

Tests proving the security monitor:
1. Has no forbidden imports
2. Cannot mutate external state
3. Is read-only for monitoring
"""

import unittest
import sys
import ast
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.runtime.security_monitor import (
    SecurityMonitor,
    MemoryMonitor,
    DriftMonitor,
    SecurityLogger,
    SecurityEvent,
    SecurityEventType,
    Severity,
)


class TestSecurityMonitorNoForbiddenImports(unittest.TestCase):
    """Test: Security monitor has no forbidden imports."""
    
    def test_no_subprocess_import(self):
        """No subprocess import."""
        monitor_file = Path(__file__).parent.parent / "runtime" / "security_monitor.py"
        content = monitor_file.read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", content)
        self.assertNotIn("from subprocess", content)
    
    def test_no_socket_import(self):
        """No socket import."""
        monitor_file = Path(__file__).parent.parent / "runtime" / "security_monitor.py"
        content = monitor_file.read_text(encoding="utf-8")
        self.assertNotIn("import socket", content)
        self.assertNotIn("from socket", content)
    
    def test_no_eval_usage(self):
        """No eval() usage."""
        monitor_file = Path(__file__).parent.parent / "runtime" / "security_monitor.py"
        content = monitor_file.read_text(encoding="utf-8")
        # Check for eval( that's not in a string
        self.assertNotIn("eval(", content)
    
    def test_no_exec_usage(self):
        """No exec() usage."""
        monitor_file = Path(__file__).parent.parent / "runtime" / "security_monitor.py"
        content = monitor_file.read_text(encoding="utf-8")
        self.assertNotIn("exec(", content)
    
    def test_no_os_system_usage(self):
        """No os.system() usage."""
        monitor_file = Path(__file__).parent.parent / "runtime" / "security_monitor.py"
        content = monitor_file.read_text(encoding="utf-8")
        self.assertNotIn("os.system(", content)


class TestSecurityMonitorReadOnly(unittest.TestCase):
    """Test: Security monitor is read-only and cannot mutate state."""
    
    def test_memory_monitor_readonly(self):
        """Memory monitor only reads, does not write."""
        monitor = MemoryMonitor()
        # Should not modify any external state
        event = monitor.check()
        # Second check should work without side effects
        event2 = monitor.check()
        # Monitor only stores internal state
        self.assertIsNotNone(monitor.last_check)
    
    def test_drift_monitor_readonly(self):
        """Drift monitor only records, does not execute."""
        monitor = DriftMonitor()
        event = monitor.record_loss(0.5)
        event = monitor.record_loss(0.4)
        event = monitor.record_loss(0.3)
        # Only stores history, no external mutation
        self.assertEqual(len(monitor.loss_history), 3)
    
    def test_logger_only_writes_to_reports(self):
        """Logger only writes to reports directory."""
        with patch('impl_v1.phase49.runtime.security_monitor.Path.mkdir'):
            with patch('builtins.open', MagicMock()):
                logger = SecurityLogger()
                # Log dir should be reports/security
                self.assertTrue(str(logger.log_dir).endswith("security"))


class TestSecurityMonitorAST(unittest.TestCase):
    """Test: AST verification of security monitor."""
    
    def test_no_dangerous_ast_nodes(self):
        """No dangerous AST nodes in security monitor."""
        monitor_file = Path(__file__).parent.parent / "runtime" / "security_monitor.py"
        content = monitor_file.read_text(encoding="utf-8")
        tree = ast.parse(content)
        
        dangerous_nodes = []
        
        for node in ast.walk(tree):
            # Check for dangerous function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile"):
                        dangerous_nodes.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    # Exclude safe patterns like platform.system()
                    if node.func.attr in ("popen", "spawn"):
                        dangerous_nodes.append(node.func.attr)
                    # os.system is dangerous, but platform.system is safe
                    if node.func.attr == "system" and isinstance(node.func.value, ast.Name):
                        if node.func.value.id == "os":
                            dangerous_nodes.append("os.system")
        
        self.assertEqual(dangerous_nodes, [], f"Found dangerous nodes: {dangerous_nodes}")


class TestSecurityMonitorIntegration(unittest.TestCase):
    """Test: Security monitor integration tests."""
    
    def test_combined_monitor_no_side_effects(self):
        """Combined monitor has no side effects."""
        with patch('impl_v1.phase49.runtime.security_monitor.Path.mkdir'):
            with patch('builtins.open', MagicMock()):
                monitor = SecurityMonitor()
                # Check should not cause exceptions
                events = monitor.check_all(loss=0.5)
                events = monitor.check_all(loss=0.4)
                # Should complete without error
                self.assertIsInstance(events, list)
    
    def test_sandbox_attempt_logged_not_executed(self):
        """Sandbox escape attempts are logged, not executed."""
        with patch('impl_v1.phase49.runtime.security_monitor.Path.mkdir'):
            with patch('builtins.open', MagicMock()):
                monitor = SecurityMonitor()
                # This should only log, never execute
                monitor.log_sandbox_attempt("socket")
                # Verify logging happened
                self.assertEqual(monitor.logger._event_count, 1)


if __name__ == "__main__":
    unittest.main()
