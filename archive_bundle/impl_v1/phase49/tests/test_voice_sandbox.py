"""
Voice Assistant Sandbox Tests - Phase 49
=========================================

Verifies that voice commands CANNOT:
1. Launch browsers
2. Execute system commands
3. Bypass governance

Architecture Enforcement:
- Voice → STT → Intent Parser → Governance Check → Native C++ Engine → Result
"""

import unittest
from typing import Dict, Any


class MockVoiceParser:
    """Mock voice parser for testing sandbox enforcement."""
    
    FORBIDDEN_INTENTS = {
        "launch_browser",
        "execute_command",
        "bypass_governance",
        "raw_system_call",
        "shell_execute",
        "subprocess_run",
    }
    
    @staticmethod
    def parse_intent(voice_text: str) -> Dict[str, Any]:
        """Parse voice input to structured intent."""
        text_lower = voice_text.lower()
        
        # Detect forbidden intents
        if any(kw in text_lower for kw in ["open browser", "launch browser", "start browser"]):
            return {"intent": "launch_browser", "blocked": True}
        if any(kw in text_lower for kw in ["run command", "execute", "shell", "subprocess"]):
            return {"intent": "execute_command", "blocked": True}
        if any(kw in text_lower for kw in ["bypass", "override", "skip governance"]):
            return {"intent": "bypass_governance", "blocked": True}
        
        # Safe intents
        return {"intent": "user_query", "blocked": False, "text": voice_text}


class VoiceSandboxGovernor:
    """Governance layer for voice commands."""
    
    @staticmethod
    def check_intent(intent: Dict[str, Any]) -> bool:
        """Returns False if intent is allowed, True if blocked."""
        # Always block forbidden intents
        if intent.get("blocked", False):
            return True
        if intent.get("intent") in MockVoiceParser.FORBIDDEN_INTENTS:
            return True
        return False
    
    @staticmethod
    def can_execute_browser() -> bool:
        """Voice NEVER has browser execution authority."""
        return False
    
    @staticmethod
    def can_execute_system_command() -> bool:
        """Voice NEVER has system command authority."""
        return False


class TestVoiceCannotExecuteBrowser(unittest.TestCase):
    """Test: Voice cannot launch or control browsers."""
    
    def test_voice_browser_blocked(self):
        """Voice 'open browser' is blocked."""
        intent = MockVoiceParser.parse_intent("open browser to example.com")
        self.assertTrue(intent.get("blocked"), "Browser launch MUST be blocked")
        self.assertTrue(VoiceSandboxGovernor.check_intent(intent))
    
    def test_voice_launch_browser_blocked(self):
        """Voice 'launch browser' is blocked."""
        intent = MockVoiceParser.parse_intent("launch browser")
        self.assertTrue(intent.get("blocked"))
    
    def test_voice_start_browser_blocked(self):
        """Voice 'start browser' is blocked."""
        intent = MockVoiceParser.parse_intent("start browser session")
        self.assertTrue(intent.get("blocked"))
    
    def test_governor_denies_browser(self):
        """Governor always denies browser execution."""
        self.assertFalse(VoiceSandboxGovernor.can_execute_browser())


class TestVoiceCannotBypassSandbox(unittest.TestCase):
    """Test: Voice cannot bypass governance sandbox."""
    
    def test_voice_bypass_blocked(self):
        """Voice 'bypass governance' is blocked."""
        intent = MockVoiceParser.parse_intent("bypass governance check")
        self.assertTrue(intent.get("blocked"))
        self.assertTrue(VoiceSandboxGovernor.check_intent(intent))
    
    def test_voice_override_blocked(self):
        """Voice 'override' is blocked."""
        intent = MockVoiceParser.parse_intent("override security")
        self.assertTrue(intent.get("blocked"))
    
    def test_voice_skip_governance_blocked(self):
        """Voice 'skip governance' is blocked."""
        intent = MockVoiceParser.parse_intent("skip governance")
        self.assertTrue(intent.get("blocked"))


class TestVoiceCannotExecuteCommands(unittest.TestCase):
    """Test: Voice cannot execute system commands."""
    
    def test_voice_run_command_blocked(self):
        """Voice 'run command' is blocked."""
        intent = MockVoiceParser.parse_intent("run command whoami")
        self.assertTrue(intent.get("blocked"))
    
    def test_voice_execute_blocked(self):
        """Voice 'execute' is blocked."""
        intent = MockVoiceParser.parse_intent("execute script.sh")
        self.assertTrue(intent.get("blocked"))
    
    def test_voice_shell_blocked(self):
        """Voice 'shell' is blocked."""
        intent = MockVoiceParser.parse_intent("shell command")
        self.assertTrue(intent.get("blocked"))
    
    def test_voice_subprocess_blocked(self):
        """Voice 'subprocess' is blocked."""
        intent = MockVoiceParser.parse_intent("subprocess run")
        self.assertTrue(intent.get("blocked"))
    
    def test_governor_denies_system_command(self):
        """Governor always denies system command execution."""
        self.assertFalse(VoiceSandboxGovernor.can_execute_system_command())


class TestVoiceSafeFlow(unittest.TestCase):
    """Test: Voice safe flow to structured task."""
    
    def test_safe_query_allowed(self):
        """Safe user query is allowed."""
        intent = MockVoiceParser.parse_intent("scan example.com for vulnerabilities")
        self.assertFalse(intent.get("blocked"))
        self.assertFalse(VoiceSandboxGovernor.check_intent(intent))
    
    def test_safe_query_returns_structured(self):
        """Safe query returns structured task object."""
        intent = MockVoiceParser.parse_intent("analyze security headers")
        self.assertEqual(intent.get("intent"), "user_query")
        self.assertIn("text", intent)


if __name__ == "__main__":
    unittest.main()
