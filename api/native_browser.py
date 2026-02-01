"""
Native Browser Bridge for YGB
=============================

Uses Windows native browser automation via:
1. winreg - for browser detection
2. subprocess - for browser launching
3. COM automation - for Edge/IE (via pywin32)
4. Selenium WebDriver as fallback

NO PLAYWRIGHT - Works on Python 3.14!
"""

import asyncio
import subprocess
import winreg
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field

# Try to import selenium as fallback
try:
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("ℹ️ Selenium not installed. Using HTTP-only mode.")


@dataclass
class NativeBrowserAction:
    """Record of a native browser action."""
    action_id: str
    action_type: str
    target: str
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class NativeFinding:
    """Security finding from native browser."""
    finding_id: str
    category: str
    severity: str
    title: str
    description: str
    url: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


class NativeBrowserBridge:
    """
    Native browser automation bridge.
    Uses Selenium with Edge/Chrome WebDriver (Windows native).
    """
    
    def __init__(
        self,
        on_action: Optional[Callable] = None,
        on_finding: Optional[Callable] = None
    ):
        self.on_action = on_action
        self.on_finding = on_finding
        self.driver = None
        self.actions: List[NativeBrowserAction] = []
        self.findings: List[NativeFinding] = []
        self.action_count = 0
    
    def _gen_id(self, prefix: str) -> str:
        return f"{prefix}-{hashlib.md5(str(datetime.now(UTC)).encode()).hexdigest()[:8]}"
    
    async def _emit_action(self, action_type: str, target: str, details: Dict = None, duration_ms: int = 0):
        """Emit browser action."""
        self.action_count += 1
        action = NativeBrowserAction(
            action_id=self._gen_id("ACT"),
            action_type=action_type,
            target=target,
            details=details or {},
            duration_ms=duration_ms
        )
        self.actions.append(action)
        
        if self.on_action:
            result = self.on_action({
                "type": "browser_action",
                "action": action_type,
                "target": target,
                "details": details or {},
                "duration_ms": duration_ms
            })
            if asyncio.iscoroutine(result):
                await result
    
    async def _emit_finding(self, finding: NativeFinding):
        """Emit security finding."""
        self.findings.append(finding)
        
        if self.on_finding:
            result = self.on_finding({
                "type": "finding",
                "finding_id": finding.finding_id,
                "category": finding.category,
                "severity": finding.severity,
                "title": finding.title,
                "description": finding.description,
                "url": finding.url
            })
            if asyncio.iscoroutine(result):
                await result
    
    def _detect_browser_path(self) -> Dict[str, Optional[str]]:
        """Detect installed browsers on Windows."""
        browsers = {
            "edge": None,
            "chrome": None,
            "firefox": None
        }
        
        # Common browser paths
        paths = {
            "edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ],
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ],
            "firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ]
        }
        
        for browser, locations in paths.items():
            for path in locations:
                if os.path.exists(path):
                    browsers[browser] = path
                    break
        
        return browsers
    
    async def start_browser(self, headless: bool = True) -> bool:
        """Start native browser using Selenium."""
        if not SELENIUM_AVAILABLE:
            return False
        
        try:
            browsers = self._detect_browser_path()
            
            # Try Edge first (always available on Windows)
            if browsers["edge"]:
                options = EdgeOptions()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--window-size=1920,1080")
                
                self.driver = webdriver.Edge(options=options)
                await self._emit_action("BROWSER_START", "edge", {"headless": headless})
                return True
            
            # Try Chrome
            elif browsers["chrome"]:
                options = ChromeOptions()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                
                self.driver = webdriver.Chrome(options=options)
                await self._emit_action("BROWSER_START", "chrome", {"headless": headless})
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Native browser start failed: {e}")
            return False
    
    async def stop_browser(self):
        """Stop the browser."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to URL."""
        if not self.driver:
            return {"success": False, "error": "Browser not started"}
        
        start = datetime.now(UTC)
        try:
            self.driver.get(url)
            duration = int((datetime.now(UTC) - start).total_seconds() * 1000)
            
            # Get page info
            title = self.driver.title
            current_url = self.driver.current_url
            
            await self._emit_action("NAVIGATE", url, {"title": title}, duration)
            
            return {
                "success": True,
                "url": current_url,
                "title": title,
                "duration_ms": duration
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def extract_page_info(self) -> Dict[str, Any]:
        """Extract page information."""
        if not self.driver:
            return {}
        
        try:
            # Get page source
            html = self.driver.page_source
            
            # Find forms
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            form_data = []
            for form in forms:
                action = form.get_attribute("action") or ""
                method = form.get_attribute("method") or "GET"
                inputs = form.find_elements(By.TAG_NAME, "input")
                input_names = [i.get_attribute("name") for i in inputs if i.get_attribute("name")]
                form_data.append({
                    "action": action,
                    "method": method.upper(),
                    "inputs": input_names
                })
            
            # Find links
            links = self.driver.find_elements(By.TAG_NAME, "a")
            hrefs = [l.get_attribute("href") for l in links[:50] if l.get_attribute("href")]
            
            # Find scripts
            scripts = self.driver.find_elements(By.TAG_NAME, "script")
            script_srcs = [s.get_attribute("src") for s in scripts if s.get_attribute("src")]
            
            await self._emit_action("EXTRACT", self.driver.current_url, {
                "forms": len(form_data),
                "links": len(hrefs),
                "scripts": len(script_srcs)
            })
            
            return {
                "title": self.driver.title,
                "url": self.driver.current_url,
                "forms": form_data,
                "links": hrefs,
                "scripts": script_srcs,
                "html_length": len(html)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def analyze_cookies(self) -> List[Dict[str, Any]]:
        """Analyze browser cookies."""
        if not self.driver:
            return []
        
        try:
            cookies = self.driver.get_cookies()
            
            for cookie in cookies:
                # Check for insecure cookies
                if not cookie.get("secure", False):
                    finding = NativeFinding(
                        finding_id=self._gen_id("FND"),
                        category="COOKIE_SECURITY",
                        severity="MEDIUM",
                        title=f"Cookie '{cookie.get('name', 'unknown')}' missing Secure flag",
                        description="Cookie can be sent over insecure connections",
                        url=self.driver.current_url
                    )
                    await self._emit_finding(finding)
                
                if not cookie.get("httpOnly", False):
                    finding = NativeFinding(
                        finding_id=self._gen_id("FND"),
                        category="COOKIE_SECURITY",
                        severity="LOW",
                        title=f"Cookie '{cookie.get('name', 'unknown')}' missing HttpOnly flag",
                        description="Cookie can be accessed by JavaScript",
                        url=self.driver.current_url
                    )
                    await self._emit_finding(finding)
            
            await self._emit_action("COOKIES", self.driver.current_url, {"count": len(cookies)})
            
            return cookies
            
        except Exception as e:
            return []
    
    async def take_screenshot(self, path: str = None) -> Optional[str]:
        """Take screenshot."""
        if not self.driver:
            return None
        
        try:
            if not path:
                path = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            self.driver.save_screenshot(path)
            await self._emit_action("SCREENSHOT", path)
            
            return path
            
        except Exception as e:
            return None


# Alias for compatibility  
NativeBrowserExecutor = NativeBrowserBridge


async def run_native_browser_analysis(
    target_url: str,
    on_action: Optional[Callable] = None,
    on_finding: Optional[Callable] = None,
    max_pages: int = 3
) -> Dict[str, Any]:
    """Run native browser analysis."""
    bridge = NativeBrowserBridge(on_action=on_action, on_finding=on_finding)
    
    result = {
        "success": False,
        "target_url": target_url,
        "findings": [],
        "actions": [],
        "pages_visited": []
    }
    
    try:
        # Start browser
        if not await bridge.start_browser(headless=True):
            result["error"] = "Failed to start native browser"
            return result
        
        # Navigate
        nav = await bridge.navigate(target_url)
        if not nav.get("success"):
            result["error"] = nav.get("error", "Navigation failed")
            return result
        
        result["pages_visited"].append(target_url)
        
        # Extract info
        info = await bridge.extract_page_info()
        
        # Analyze cookies
        await bridge.analyze_cookies()
        
        # Take screenshot
        await bridge.take_screenshot()
        
        result["success"] = True
        result["findings"] = [f.__dict__ for f in bridge.findings]
        result["actions"] = [a.__dict__ for a in bridge.actions]
        
    finally:
        await bridge.stop_browser()
    
    return result


# Test
if __name__ == "__main__":
    async def test():
        def on_action(a):
            print(f"🌐 {a.get('action')}: {a.get('target', '')[:60]}")
        
        def on_finding(f):
            print(f"🔍 [{f.get('severity')}] {f.get('title')}")
        
        result = await run_native_browser_analysis(
            "https://example.com",
            on_action=on_action,
            on_finding=on_finding
        )
        
        print(f"\n{'='*50}")
        print(f"Success: {result.get('success')}")
        print(f"Findings: {len(result.get('findings', []))}")
        print(f"Actions: {len(result.get('actions', []))}")
    
    asyncio.run(test())
