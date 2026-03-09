import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestTailscaleStartupScripts(unittest.TestCase):
    def test_start_full_stack_has_tailscale_auto_connect(self):
        content = (PROJECT_ROOT / "start_full_stack.ps1").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        self.assertIn("YGB_TAILSCALE_AUTO_CONNECT", content)
        self.assertIn("ensure-tailscale-tailnet.ps1", content)
        self.assertIn("YGB_REMOTE_ONLY", content)
        self.assertIn("Start-Process $remoteFrontendUrl", content)

    def test_start_full_stack_preserves_tsnet_frontend(self):
        content = (PROJECT_ROOT / "start_full_stack.ps1").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        self.assertIn("Test-IsTsNetUrl", content)
        self.assertIn("Using configured private frontend URL", content)
        self.assertIn("YGB_TAILSCALE_AUTO_SERVE", content)

    def test_private_client_launcher_exists(self):
        launcher = (PROJECT_ROOT / "start_private_client.ps1").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        self.assertIn("YGB_REMOTE_ONLY", launcher)
        self.assertIn("YGB_TAILSCALE_OWNER_ACCOUNT", launcher)
        self.assertIn("ygb-nas.tail7521c4.ts.net", launcher)

    def test_tailnet_helper_supports_auth_key_and_unattended(self):
        content = (PROJECT_ROOT / "scripts" / "ensure-tailscale-tailnet.ps1").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        self.assertIn("--auth-key", content)
        self.assertIn("--unattended", content)
        self.assertIn("file:", content)
        self.assertIn("tailscale set --hostname", content)

    def test_serve_script_is_dynamic(self):
        content = (PROJECT_ROOT / "scripts" / "tailscale-serve-ygb.ps1").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        self.assertIn("tailscale status --json", content)
        self.assertIn("Get-TailscaleServeHost", content)
        self.assertNotIn("ygb-nas.tail7521c4.ts.net", content)


if __name__ == "__main__":
    unittest.main()
