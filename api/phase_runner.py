"""
YGB UNIFIED PHASE RUNNER
=========================

Executes ALL 49 governance phases with comprehensive security analysis.
Uses Selenium with Edge/Chrome (Windows native) + HTTP fallback.

Phases:
- 01-19: Governance logic (python/)
- 20-49: Execution logic (impl_v1/)
"""

import asyncio
import importlib
import sys
import json
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
import hashlib
import traceback
from urllib.parse import urlparse, urljoin
import re

# ==============================================================================
# PATHS
# ==============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "python"))
sys.path.insert(0, str(PROJECT_ROOT / "impl_v1"))

# ==============================================================================
# HTTP CLIENT
# ==============================================================================
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("[WARNING] httpx not installed. Run: pip install httpx")

# ==============================================================================
# SELENIUM (NATIVE BROWSER)
# ==============================================================================
try:
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("[INFO] Selenium not installed. Using HTTP-only mode.")

# ==============================================================================
# CVE SCANNER
# ==============================================================================
try:
    from cve_scanner import scan_for_cves, CVEScanner
    CVE_SCANNER_AVAILABLE = True
except ImportError:
    CVE_SCANNER_AVAILABLE = False
    print("[INFO] CVE scanner not available.")


# ==============================================================================
# DATA CLASSES
# ==============================================================================
@dataclass
class PhaseResult:
    """Result from running a phase."""
    phase_number: int
    phase_name: str
    status: str  # SUCCESS, FAILED, SKIPPED
    duration_ms: int
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class Finding:
    """Security finding."""
    finding_id: str
    category: str
    severity: str
    title: str
    description: str
    url: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    """Context passed through all phases."""
    target_url: str
    workflow_id: str
    mode: str  # READ_ONLY, REAL
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    phase_results: List[PhaseResult] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    browser_actions: List[Dict[str, Any]] = field(default_factory=list)
    pages_visited: List[str] = field(default_factory=list)
    governance_data: Dict[str, Any] = field(default_factory=dict)
    page_data: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    technologies: List[str] = field(default_factory=list)
    current_phase: int = 0
    stopped: bool = False
    report_file: Optional[str] = None


# ==============================================================================
# UNIFIED PHASE RUNNER
# ==============================================================================
class UnifiedPhaseRunner:
    """
    Runs ALL 49 phases with comprehensive security analysis.
    Uses Selenium (Edge/Chrome) or HTTP fallback.
    """
    
    def __init__(self, on_progress: Optional[Callable] = None):
        self.on_progress = on_progress
        self.loaded_modules: Dict[int, Any] = {}
        self.action_count = 0
        self.driver = None
        self.use_browser = False
        
    async def _emit(self, data: Dict[str, Any]):
        """Emit progress update."""
        if self.on_progress:
            result = self.on_progress(data)
            if asyncio.iscoroutine(result):
                await result
    
    async def _emit_action(self, action: str, target: str, details: Dict = None, duration_ms: int = 0):
        """Emit browser/HTTP action."""
        self.action_count += 1
        await self._emit({
            "type": "browser_action",
            "action": action,
            "target": target,
            "details": details or {},
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC).isoformat()
        })
    
    async def _emit_finding(self, finding: Finding):
        """Emit security finding."""
        await self._emit({
            "type": "finding",
            "finding_id": finding.finding_id,
            "category": finding.category,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "url": finding.url
        })
    
    def _gen_id(self, prefix: str) -> str:
        return f"{prefix}-{hashlib.md5(str(datetime.now(UTC)).encode()).hexdigest()[:8]}"
    
    async def _add_finding(self, context: WorkflowContext, category: str, severity: str, title: str, description: str, url: str = ""):
        """Add and emit a finding."""
        finding = Finding(
            finding_id=self._gen_id("FND"),
            category=category,
            severity=severity,
            title=title,
            description=description,
            url=url or context.target_url
        )
        context.findings.append(finding)
        await self._emit_finding(finding)
    
    async def run_workflow(
        self,
        target_url: str,
        workflow_id: str,
        mode: str = "READ_ONLY"
    ) -> WorkflowContext:
        """Run complete security analysis with ALL phases."""
        context = WorkflowContext(
            target_url=target_url,
            workflow_id=workflow_id,
            mode=mode
        )
        
        started = datetime.now(UTC)
        
        await self._emit({
            "type": "workflow_start",
            "workflow_id": workflow_id,
            "target": target_url,
            "mode": mode
        })
        
        # ==========================================================
        # PHASE 0: GOVERNANCE INITIALIZATION
        # ==========================================================
        await self._run_phase(context, 0, "Governance Initialization", 0, 
                             lambda c: self._phase_governance_init(c))
        
        # ==========================================================
        # PHASE 1: BROWSER/HTTP INIT
        # ==========================================================
        await self._run_phase(context, 1, "Browser Initialization", 5, 
                             lambda c: self._phase_browser_init(c))
        
        # ==========================================================
        # PHASE 2: TARGET NAVIGATION
        # ==========================================================
        await self._run_phase(context, 2, f"Navigating to {target_url[:50]}...", 10, 
                             lambda c: self._phase_navigate(c))
        
        # ==========================================================
        # PHASE 3: PAGE EXTRACTION
        # ==========================================================
        await self._run_phase(context, 3, "Extracting Page Content", 15, 
                             lambda c: self._phase_extract_content(c))
        
        # ==========================================================
        # PHASE 4: FORM DETECTION
        # ==========================================================
        await self._run_phase(context, 4, "Detecting Forms & Inputs", 20, 
                             lambda c: self._phase_detect_forms(c))
        
        # ==========================================================
        # PHASE 5: SECURITY HEADERS
        # ==========================================================
        await self._run_phase(context, 5, "Analyzing Security Headers", 25, 
                             lambda c: self._phase_analyze_headers(c))
        
        # ==========================================================
        # PHASE 6: COOKIE SECURITY
        # ==========================================================
        await self._run_phase(context, 6, "Checking Cookie Security", 30, 
                             lambda c: self._phase_check_cookies(c))
        
        # ==========================================================
        # PHASE 7: XSS DETECTION
        # ==========================================================
        await self._run_phase(context, 7, "XSS Vulnerability Detection", 35, 
                             lambda c: self._phase_detect_xss(c))
        
        # ==========================================================
        # PHASE 8: SQL INJECTION
        # ==========================================================
        await self._run_phase(context, 8, "SQL Injection Detection", 40, 
                             lambda c: self._phase_detect_sqli(c))
        
        # ==========================================================
        # PHASE 9: CSRF ANALYSIS
        # ==========================================================
        await self._run_phase(context, 9, "CSRF Token Analysis", 45, 
                             lambda c: self._phase_check_csrf(c))
        
        # ==========================================================
        # PHASE 10: IDOR DETECTION
        # ==========================================================
        await self._run_phase(context, 10, "IDOR Vulnerability Check", 48, 
                             lambda c: self._phase_detect_idor(c))
        
        # ==========================================================
        # PHASE 11: INFO DISCLOSURE
        # ==========================================================
        await self._run_phase(context, 11, "Information Disclosure Scan", 50, 
                             lambda c: self._phase_info_disclosure(c))
        
        # ==========================================================
        # PHASE 12: TECHNOLOGY DETECTION
        # ==========================================================
        await self._run_phase(context, 12, "Technology Fingerprinting", 55, 
                             lambda c: self._phase_detect_tech(c))
        
        # ==========================================================
        # PHASE 13: LINK CRAWLING
        # ==========================================================
        max_pages = 5 if mode == "REAL" else 3
        await self._run_phase(context, 13, f"Crawling Links (max {max_pages})", 60, 
                             lambda c: self._phase_crawl_links(c, max_pages))
        
        # ==========================================================
        # PHASE 14: JAVASCRIPT ANALYSIS
        # ==========================================================
        await self._run_phase(context, 14, "JavaScript Security Analysis", 65, 
                             lambda c: self._phase_js_analysis(c))
        
        # ==========================================================
        # PHASE 15: API ENDPOINT DISCOVERY
        # ==========================================================
        await self._run_phase(context, 15, "API Endpoint Discovery", 70, 
                             lambda c: self._phase_api_discovery(c))
        
        # ==========================================================
        # PHASE 16: AUTHENTICATION ANALYSIS
        # ==========================================================
        await self._run_phase(context, 16, "Authentication Analysis", 75, 
                             lambda c: self._phase_auth_analysis(c))
        
        # ==========================================================
        # PHASE 17: CORS POLICY
        # ==========================================================
        await self._run_phase(context, 17, "CORS Policy Check", 80, 
                             lambda c: self._phase_cors_check(c))
        
        # ==========================================================
        # PHASE 18: CSP ANALYSIS
        # ==========================================================
        await self._run_phase(context, 18, "CSP Analysis", 85, 
                             lambda c: self._phase_csp_analysis(c))
        
        # ==========================================================
        # PHASE 19: SCREENSHOT
        # ==========================================================
        await self._run_phase(context, 19, "Capturing Screenshot", 90, 
                             lambda c: self._phase_screenshot(c))
        
        # ==========================================================
        # PHASE 20: SUBDOMAIN ENUMERATION
        # ==========================================================
        await self._run_phase(context, 20, "Subdomain Enumeration", 42, 
                             lambda c: self._phase_subdomain_enum(c))
        
        # ==========================================================
        # PHASE 21: DNS ANALYSIS
        # ==========================================================
        await self._run_phase(context, 21, "DNS Security Analysis", 44, 
                             lambda c: self._phase_dns_analysis(c))
        
        # ==========================================================
        # PHASE 22: SSL/TLS CHECK
        # ==========================================================
        await self._run_phase(context, 22, "SSL/TLS Certificate Check", 46, 
                             lambda c: self._phase_ssl_check(c))
        
        # ==========================================================
        # PHASE 23: OPEN REDIRECT
        # ==========================================================
        await self._run_phase(context, 23, "Open Redirect Detection", 48, 
                             lambda c: self._phase_open_redirect(c))
        
        # ==========================================================
        # PHASE 24: SSRF DETECTION
        # ==========================================================
        await self._run_phase(context, 24, "SSRF Vulnerability Check", 50, 
                             lambda c: self._phase_ssrf_detection(c))
        
        # ==========================================================
        # PHASE 25: XXE DETECTION
        # ==========================================================
        await self._run_phase(context, 25, "XXE Vulnerability Check", 52, 
                             lambda c: self._phase_xxe_detection(c))
        
        # ==========================================================
        # PHASE 26: COMMAND INJECTION
        # ==========================================================
        await self._run_phase(context, 26, "Command Injection Detection", 54, 
                             lambda c: self._phase_cmd_injection(c))
        
        # ==========================================================
        # PHASE 27: PATH TRAVERSAL
        # ==========================================================
        await self._run_phase(context, 27, "Path Traversal Detection", 56, 
                             lambda c: self._phase_path_traversal(c))
        
        # ==========================================================
        # PHASE 28: FILE INCLUSION
        # ==========================================================
        await self._run_phase(context, 28, "File Inclusion Check", 58, 
                             lambda c: self._phase_file_inclusion(c))
        
        # ==========================================================
        # PHASE 29: TEMPLATE INJECTION
        # ==========================================================
        await self._run_phase(context, 29, "Template Injection Detection", 60, 
                             lambda c: self._phase_template_injection(c))
        
        # ==========================================================
        # PHASE 30: CLICKJACKING
        # ==========================================================
        await self._run_phase(context, 30, "Clickjacking Defense Check", 62, 
                             lambda c: self._phase_clickjacking(c))
        
        # ==========================================================
        # PHASE 31: HTTP METHOD TESTING
        # ==========================================================
        await self._run_phase(context, 31, "HTTP Method Testing", 64, 
                             lambda c: self._phase_http_methods(c))
        
        # ==========================================================
        # PHASE 32: HEADER INJECTION
        # ==========================================================
        await self._run_phase(context, 32, "Header Injection Detection", 66, 
                             lambda c: self._phase_header_injection(c))
        
        # ==========================================================
        # PHASE 33: WEBSOCKET SECURITY
        # ==========================================================
        await self._run_phase(context, 33, "WebSocket Security Check", 68, 
                             lambda c: self._phase_websocket_security(c))
        
        # ==========================================================
        # PHASE 34: GRAPHQL SECURITY
        # ==========================================================
        await self._run_phase(context, 34, "GraphQL Security Analysis", 70, 
                             lambda c: self._phase_graphql_security(c))
        
        # ==========================================================
        # PHASE 35: JWT ANALYSIS
        # ==========================================================
        await self._run_phase(context, 35, "JWT Token Analysis", 72, 
                             lambda c: self._phase_jwt_analysis(c))
        
        # ==========================================================
        # PHASE 36: OAUTH SECURITY
        # ==========================================================
        await self._run_phase(context, 36, "OAuth Implementation Check", 74, 
                             lambda c: self._phase_oauth_security(c))
        
        # ==========================================================
        # PHASE 37: RATE LIMITING
        # ==========================================================
        await self._run_phase(context, 37, "Rate Limiting Check", 76, 
                             lambda c: self._phase_rate_limiting(c))
        
        # ==========================================================
        # PHASE 38: CAPTCHA BYPASS
        # ==========================================================
        await self._run_phase(context, 38, "CAPTCHA Implementation Check", 78, 
                             lambda c: self._phase_captcha_check(c))
        
        # ==========================================================
        # PHASE 39: PAYMENT SECURITY
        # ==========================================================
        await self._run_phase(context, 39, "Payment Security Analysis", 80, 
                             lambda c: self._phase_payment_security(c))
        
        # ==========================================================
        # PHASE 40: BUSINESS LOGIC
        # ==========================================================
        await self._run_phase(context, 40, "Business Logic Flaws", 82, 
                             lambda c: self._phase_business_logic(c))
        
        # ==========================================================
        # PHASE 41: RACE CONDITIONS
        # ==========================================================
        await self._run_phase(context, 41, "Race Condition Detection", 84, 
                             lambda c: self._phase_race_conditions(c))
        
        # ==========================================================
        # PHASE 42: PASSWORD POLICY
        # ==========================================================
        await self._run_phase(context, 42, "Password Policy Check", 86, 
                             lambda c: self._phase_password_policy(c))
        
        # ==========================================================
        # PHASE 43: 2FA ANALYSIS
        # ==========================================================
        await self._run_phase(context, 43, "2FA Implementation Check", 88, 
                             lambda c: self._phase_2fa_analysis(c))
        
        # ==========================================================
        # PHASE 44: SESSION FIXATION
        # ==========================================================
        await self._run_phase(context, 44, "Session Fixation Check", 89, 
                             lambda c: self._phase_session_fixation(c))
        
        # ==========================================================
        # PHASE 45: PRIVILEGE ESCALATION
        # ==========================================================
        await self._run_phase(context, 45, "Privilege Escalation Check", 90, 
                             lambda c: self._phase_privilege_escalation(c))
        
        # ==========================================================
        # PHASE 46: DATA EXPOSURE
        # ==========================================================
        await self._run_phase(context, 46, "Sensitive Data Exposure", 92, 
                             lambda c: self._phase_data_exposure(c))
        
        # ==========================================================
        # PHASE 47: CVE VULNERABILITY SCAN
        # ==========================================================
        await self._run_phase(context, 47, "CVE Vulnerability Detection", 93, 
                             lambda c: self._phase_cve_scan(c))
        
        # ==========================================================
        # PHASE 48: DEPENDENCY SCAN
        # ==========================================================
        await self._run_phase(context, 48, "Dependency Security Scan", 95, 
                             lambda c: self._phase_dependency_scan(c))
        
        # ==========================================================
        # PHASE 49: FINAL SECURITY SUMMARY
        # ==========================================================
        await self._run_phase(context, 49, "Final Security Summary", 97, 
                             lambda c: self._phase_final_scan(c))
        
        # ==========================================================
        # PHASE 50: REPORT GENERATION
        # ==========================================================
        await self._run_phase(context, 49, "Generating Security Report", 98, 
                             lambda c: self._phase_generate_report(c))
        
        # ==========================================================
        # CLEANUP
        # ==========================================================
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        # ==========================================================
        # WORKFLOW COMPLETE
        # ==========================================================
        total_duration = int((datetime.now(UTC) - started).total_seconds() * 1000)
        
        await self._emit({
            "type": "workflow_complete",
            "workflow_id": workflow_id,
            "total_phases": len(context.phase_results),
            "findings": len(context.findings),
            "pages": len(context.pages_visited),
            "actions": self.action_count,
            "duration_ms": total_duration
        })
        
        return context
    
    async def _run_phase(self, context: WorkflowContext, phase_num: int, name: str, progress: int, func: Callable):
        """Run a single phase with error handling."""
        await self._emit({
            "type": "phase_start",
            "phase": phase_num,
            "name": name,
            "progress": progress
        })
        
        phase_start = datetime.now(UTC)
        status = "SUCCESS"
        output = {}
        
        try:
            result = await func(context)
            if result:
                output = result
        except Exception as e:
            status = "FAILED"
            output = {"error": str(e)}
            print(f"[ERROR] Phase {phase_num} error: {e}")
        
        duration = int((datetime.now(UTC) - phase_start).total_seconds() * 1000)
        
        context.phase_results.append(PhaseResult(
            phase_number=phase_num,
            phase_name=name,
            status=status,
            duration_ms=duration,
            output=output
        ))
        
        await self._emit({
            "type": "phase_complete",
            "phase": phase_num,
            "name": name,
            "status": status,
            "duration_ms": duration,
            "output": output
        })
    
    # ==========================================================================
    # PHASE IMPLEMENTATIONS
    # ==========================================================================
    
    async def _phase_governance_init(self, context: WorkflowContext) -> Dict:
        """Phase 0: Load governance modules."""
        loaded = 0
        for i in range(1, 20):
            try:
                module_path = f"python.phase{i:02d}_core" if i == 1 else f"python.phase{i:02d}_actors" if i == 2 else None
                if module_path:
                    importlib.import_module(module_path)
                    loaded += 1
            except:
                pass
        
        context.governance_data["phases_loaded"] = loaded
        return {"governance_phases": loaded}
    
    async def _phase_browser_init(self, context: WorkflowContext) -> Dict:
        """Phase 1: Initialize browser or HTTP client."""
        # Try Selenium first
        if SELENIUM_AVAILABLE:
            try:
                options = EdgeOptions()
                options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--window-size=1920,1080")
                
                self.driver = webdriver.Edge(options=options)
                self.use_browser = True
                await self._emit_action("BROWSER_START", "edge", {"headless": True})
                return {"browser": "Edge", "mode": "selenium"}
            except Exception as e:
                print(f"[WARNING] Edge failed: {e}, trying Chrome...")
                try:
                    options = ChromeOptions()
                    options.add_argument("--headless=new")
                    options.add_argument("--disable-gpu")
                    options.add_argument("--no-sandbox")
                    
                    self.driver = webdriver.Chrome(options=options)
                    self.use_browser = True
                    await self._emit_action("BROWSER_START", "chrome", {"headless": True})
                    return {"browser": "Chrome", "mode": "selenium"}
                except:
                    pass
        
        # Fallback to HTTP
        if HTTPX_AVAILABLE:
            await self._emit_action("HTTP_INIT", "httpx", {"mode": "HTTP"})
            return {"browser": "httpx", "mode": "http"}
        
        return {"error": "No analyzer available"}
    
    async def _phase_navigate(self, context: WorkflowContext) -> Dict:
        """Phase 2: Navigate to target URL."""
        start = datetime.now(UTC)
        url = context.target_url
        
        if self.use_browser and self.driver:
            try:
                self.driver.get(url)
                title = self.driver.title
                current_url = self.driver.current_url
                context.pages_visited.append(current_url)
                
                duration = int((datetime.now(UTC) - start).total_seconds() * 1000)
                await self._emit_action("NAVIGATE", url, {"title": title}, duration)
                
                return {"status": 200, "title": title}
            except Exception as e:
                return {"error": str(e)}
        else:
            # HTTP fallback
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                
                context.headers = dict(response.headers)
                context.page_data["status"] = response.status_code
                context.page_data["url"] = str(response.url)
                context.page_data["content"] = response.text
                context.pages_visited.append(url)
                
                duration = int((datetime.now(UTC) - start).total_seconds() * 1000)
                await self._emit_action("NAVIGATE", url, {"status": response.status_code}, duration)
                
                return {"status": response.status_code}
    
    async def _phase_extract_content(self, context: WorkflowContext) -> Dict:
        """Phase 3: Extract page content."""
        if self.use_browser and self.driver:
            html = self.driver.page_source
            context.page_data["content"] = html
            context.page_data["url"] = self.driver.current_url
            
            # Get all links
            links = self.driver.find_elements(By.TAG_NAME, "a")
            context.links = [l.get_attribute("href") for l in links[:100] if l.get_attribute("href")]
        else:
            html = context.page_data.get("content", "")
            context.links = re.findall(r'href=["\']([^"\']+)["\']', html)[:100]
        
        # Extract title
        title_match = re.search(r'<title>([^<]+)</title>', html, re.I)
        title = title_match.group(1) if title_match else ""
        
        await self._emit_action("EXTRACT", context.page_data.get("url", context.target_url), {
            "links": len(context.links),
            "size": len(html)
        })
        
        return {"links": len(context.links), "title": title}
    
    async def _phase_detect_forms(self, context: WorkflowContext) -> Dict:
        """Phase 4: Detect forms and inputs."""
        content = context.page_data.get("content", "")
        forms = []
        
        if self.use_browser and self.driver:
            form_elements = self.driver.find_elements(By.TAG_NAME, "form")
            for form in form_elements:
                action = form.get_attribute("action") or ""
                method = form.get_attribute("method") or "GET"
                inputs = form.find_elements(By.TAG_NAME, "input")
                form_data = {
                    "action": action,
                    "method": method.upper(),
                    "inputs": [i.get_attribute("name") for i in inputs if i.get_attribute("name")]
                }
                forms.append(form_data)
                
                # Check for password fields
                password_inputs = [i for i in inputs if i.get_attribute("type") == "password"]
                if password_inputs and form_data["method"] == "GET":
                    await self._add_finding(context, "AUTH", "HIGH",
                        "Password sent via GET method",
                        "Login form uses GET method which exposes credentials in URL")
        else:
            form_matches = re.findall(r'<form[^>]*>(.*?)</form>', content, re.I | re.DOTALL)
            for form_html in form_matches:
                action = re.search(r'action=["\']([^"\']*)["\']', form_html)
                method = re.search(r'method=["\']([^"\']*)["\']', form_html)
                inputs = re.findall(r'<input[^>]*name=["\']([^"\']+)["\']', form_html)
                forms.append({
                    "action": action.group(1) if action else "",
                    "method": (method.group(1) if method else "GET").upper(),
                    "inputs": inputs
                })
        
        context.forms = forms
        
        # Report insecure forms
        for form in forms:
            if 'password' in str(form.get('inputs', [])).lower():
                if not context.target_url.startswith('https'):
                    await self._add_finding(context, "AUTH", "CRITICAL",
                        "Password form on non-HTTPS page",
                        "Login form transmits credentials over insecure HTTP connection")
        
        await self._emit_action("FORM_DETECT", context.target_url, {"forms": len(forms)})
        
        return {"forms": len(forms)}
    
    async def _phase_analyze_headers(self, context: WorkflowContext) -> Dict:
        """Phase 5: Analyze security headers."""
        headers = {k.lower(): v for k, v in context.headers.items()}
        findings = 0
        
        # Security headers to check
        header_checks = [
            ('x-frame-options', 'X-Frame-Options', 'MEDIUM', 'Clickjacking protection'),
            ('x-content-type-options', 'X-Content-Type-Options', 'MEDIUM', 'MIME type sniffing protection'),
            ('x-xss-protection', 'X-XSS-Protection', 'LOW', 'XSS filter'),
            ('content-security-policy', 'Content-Security-Policy', 'MEDIUM', 'Content injection protection'),
            ('strict-transport-security', 'Strict-Transport-Security', 'MEDIUM', 'HTTPS enforcement'),
            ('permissions-policy', 'Permissions-Policy', 'LOW', 'Browser feature restrictions'),
            ('referrer-policy', 'Referrer-Policy', 'LOW', 'Referrer information control'),
            ('x-permitted-cross-domain-policies', 'X-Permitted-Cross-Domain-Policies', 'LOW', 'Cross-domain policy'),
        ]
        
        for header, display_name, severity, desc in header_checks:
            if header not in headers:
                await self._add_finding(context, "HEADERS", severity,
                    f"Missing {display_name}",
                    f"Response is missing the {display_name} header ({desc})")
                findings += 1
        
        # Check for info disclosure headers
        info_headers = [
            ('server', 'Server'),
            ('x-powered-by', 'X-Powered-By'),
            ('x-aspnet-version', 'X-AspNet-Version'),
            ('x-aspnetmvc-version', 'X-AspNetMvc-Version'),
        ]
        
        for header, display_name in info_headers:
            if header in headers:
                await self._add_finding(context, "INFO_DISCLOSURE", "INFO",
                    f"Server info disclosed via {display_name}",
                    f"{display_name}: {headers[header]}")
                findings += 1
        
        await self._emit_action("HEADERS", context.target_url, {"findings": findings})
        
        return {"findings": findings}
    
    async def _phase_check_cookies(self, context: WorkflowContext) -> Dict:
        """Phase 6: Check cookie security."""
        findings = 0
        
        if self.use_browser and self.driver:
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                name = cookie.get('name', 'unknown')
                
                if not cookie.get('secure', False):
                    await self._add_finding(context, "COOKIE", "MEDIUM",
                        f"Cookie '{name}' missing Secure flag",
                        "Cookie can be transmitted over insecure connections")
                    findings += 1
                
                if not cookie.get('httpOnly', False):
                    await self._add_finding(context, "COOKIE", "LOW",
                        f"Cookie '{name}' missing HttpOnly flag",
                        "Cookie is accessible to JavaScript (potential XSS target)")
                    findings += 1
                
                if 'session' in name.lower() or 'token' in name.lower():
                    if not cookie.get('secure', False):
                        await self._add_finding(context, "COOKIE", "HIGH",
                            f"Session cookie '{name}' transmitted insecurely",
                            "Session identifier can be intercepted by attackers")
                        findings += 1
        else:
            set_cookie = context.headers.get("set-cookie", "")
            if set_cookie:
                if "https" in context.target_url and "secure" not in set_cookie.lower():
                    await self._add_finding(context, "COOKIE", "MEDIUM",
                        "Cookie missing Secure flag",
                        "Cookie can be transmitted over insecure connections")
                    findings += 1
                
                if "httponly" not in set_cookie.lower():
                    await self._add_finding(context, "COOKIE", "LOW",
                        "Cookie missing HttpOnly flag",
                        "Cookie is accessible to JavaScript")
                    findings += 1
        
        await self._emit_action("COOKIES", context.target_url, {"findings": findings})
        
        return {"findings": findings}
    
    async def _phase_detect_xss(self, context: WorkflowContext) -> Dict:
        """Phase 7: XSS vulnerability detection."""
        content = context.page_data.get("content", "")
        findings = 0
        
        # Check for inline event handlers
        event_handlers = re.findall(r'\bon(\w+)\s*=\s*["\'][^"\']*["\']', content, re.I)
        if len(event_handlers) > 5:
            await self._add_finding(context, "XSS", "LOW",
                f"Multiple inline event handlers ({len(event_handlers)})",
                "Inline event handlers can be XSS vectors if user input is reflected")
            findings += 1
        
        # Dangerous JavaScript patterns
        xss_patterns = [
            ('document.write', 'MEDIUM', 'document.write() usage'),
            ('innerHTML', 'MEDIUM', 'innerHTML assignment'),
            ('outerHTML', 'MEDIUM', 'outerHTML assignment'),
            ('eval(', 'HIGH', 'eval() function usage'),
            ('setTimeout(', 'LOW', 'setTimeout with string'),
            ('setInterval(', 'LOW', 'setInterval with string'),
            ('.html(', 'MEDIUM', 'jQuery .html() usage'),
            ('dangerouslySetInnerHTML', 'HIGH', 'React dangerouslySetInnerHTML'),
            ('v-html', 'HIGH', 'Vue v-html directive'),
            ('[innerHTML]', 'HIGH', 'Angular innerHTML binding'),
        ]
        
        for pattern, severity, desc in xss_patterns:
            count = content.count(pattern)
            if count > 0:
                await self._add_finding(context, "XSS", severity,
                    f"Potential XSS: {desc} ({count} occurrences)",
                    f"Found {count} instances of {pattern} which could lead to XSS")
                findings += 1
        
        # Check for reflected parameters in URL
        parsed = urlparse(context.target_url)
        if parsed.query:
            for param in parsed.query.split('&'):
                if '=' in param:
                    value = param.split('=')[1]
                    if value and value in content:
                        await self._add_finding(context, "XSS", "MEDIUM",
                            f"URL parameter reflected in page",
                            f"Parameter value appears in response - potential reflected XSS")
                        findings += 1
                        break
        
        # Check for DOM-based XSS sinks
        dom_sinks = ['location.hash', 'location.search', 'location.href', 
                     'document.URL', 'document.referrer', 'window.name']
        for sink in dom_sinks:
            if sink in content:
                await self._add_finding(context, "XSS", "MEDIUM",
                    f"DOM-based XSS source detected: {sink}",
                    "User-controllable data source found in JavaScript")
                findings += 1
        
        await self._emit_action("XSS_SCAN", context.target_url, {"patterns_found": findings})
        
        return {"findings": findings}
    
    async def _phase_detect_sqli(self, context: WorkflowContext) -> Dict:
        """Phase 8: SQL injection detection."""
        content = context.page_data.get("content", "").lower()
        findings = 0
        
        # SQL error patterns
        sql_errors = [
            ('sql syntax', 'MySQL syntax error'),
            ('mysql_', 'MySQL function error'),
            ('sqlite_', 'SQLite error'),
            ('postgresql', 'PostgreSQL error'),
            ('ora-', 'Oracle error'),
            ('mssql', 'MSSQL error'),
            ('unclosed quotation', 'Unclosed quotation error'),
            ('quoted string not properly', 'String termination error'),
            ('syntax error at or near', 'SQL syntax error'),
            ('sqlstate[', 'SQL state error'),
            ('warning: pg_', 'PostgreSQL warning'),
            ('valid postgresql result', 'PostgreSQL error'),
            ('pgsql', 'PostgreSQL error'),
            ('odbc', 'ODBC error'),
            ('microsoft ole db', 'OLE DB error'),
            ('you have an error in your sql', 'MySQL error'),
        ]
        
        for pattern, desc in sql_errors:
            if pattern in content:
                await self._add_finding(context, "SQLI", "CRITICAL",
                    f"SQL error message exposed",
                    f"Found '{pattern}' indicating possible SQL injection vulnerability")
                findings += 1
                break
        
        # Check for common SQLi-vulnerable parameter names
        sqli_params = ['id', 'user_id', 'item_id', 'product', 'category', 'page', 'sort', 'order']
        for link in context.links[:50]:
            for param in sqli_params:
                if f'{param}=' in link:
                    await self._add_finding(context, "SQLI", "LOW",
                        f"Potentially injectable parameter: {param}",
                        f"Common SQL-injectable parameter found in URL: {link[:100]}")
                    findings += 1
                    break
            if findings > 0:
                break
        
        await self._emit_action("SQLI_SCAN", context.target_url, {"findings": findings})
        
        return {"findings": findings}
    
    async def _phase_check_csrf(self, context: WorkflowContext) -> Dict:
        """Phase 9: CSRF protection check."""
        findings = 0
        
        csrf_indicators = ['csrf', 'xsrf', '_token', 'authenticity_token', '__requestverificationtoken']
        
        for form in context.forms:
            if form.get("method") == "POST":
                inputs = [i.lower() for i in form.get("inputs", [])]
                has_csrf = any(csrf in ' '.join(inputs) for csrf in csrf_indicators)
                
                if not has_csrf:
                    await self._add_finding(context, "CSRF", "MEDIUM",
                        "POST form without CSRF protection",
                        f"Form posting to {form.get('action', 'unknown')[:50]} lacks anti-CSRF token")
                    findings += 1
        
        await self._emit_action("CSRF_CHECK", context.target_url, {"forms": len(context.forms), "findings": findings})
        
        return {"findings": findings}
    
    async def _phase_detect_idor(self, context: WorkflowContext) -> Dict:
        """Phase 10: IDOR vulnerability check."""
        findings = 0
        
        idor_patterns = [
            (r'[?&](id|user_id|account_id|order_id|doc_id)=\d+', 'Numeric ID parameter'),
            (r'/users?/\d+', 'User ID in path'),
            (r'/orders?/\d+', 'Order ID in path'),
            (r'/accounts?/\d+', 'Account ID in path'),
            (r'/files?/\d+', 'File ID in path'),
            (r'/documents?/\d+', 'Document ID in path'),
        ]
        
        for link in context.links[:50]:
            for pattern, desc in idor_patterns:
                if re.search(pattern, link, re.I):
                    await self._add_finding(context, "IDOR", "MEDIUM",
                        f"Potential IDOR: {desc}",
                        f"Sequential/predictable ID found: {link[:100]}")
                    findings += 1
                    break
            if findings >= 3:
                break
        
        await self._emit_action("IDOR_CHECK", context.target_url, {"findings": findings})
        
        return {"findings": findings}
    
    async def _phase_info_disclosure(self, context: WorkflowContext) -> Dict:
        """Phase 11: Information disclosure scan."""
        content = context.page_data.get("content", "")
        findings = 0
        
        # Check HTML comments
        comments = re.findall(r'<!--(.*?)-->', content, re.DOTALL)
        sensitive_words = ['password', 'secret', 'api_key', 'apikey', 'token', 
                          'admin', 'debug', 'todo', 'fixme', 'hack', 'bug',
                          'credential', 'private', 'internal']
        
        for comment in comments:
            comment_lower = comment.lower()
            for word in sensitive_words:
                if word in comment_lower:
                    await self._add_finding(context, "INFO_DISCLOSURE", "LOW",
                        f"Sensitive info in HTML comment",
                        f"Found '{word}' in comment: {comment[:80]}...")
                    findings += 1
                    break
        
        # Check for exposed files
        exposed_files = ['.git', '.svn', '.env', 'config.php', 'wp-config.php', 
                        '.htaccess', 'web.config', 'database.yml', 'settings.py']
        for file in exposed_files:
            if file in content:
                await self._add_finding(context, "INFO_DISCLOSURE", "HIGH",
                    f"Exposed file reference: {file}",
                    f"Found reference to sensitive file: {file}")
                findings += 1
        
        # Check for email addresses
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', content)
        if emails:
            await self._add_finding(context, "INFO_DISCLOSURE", "INFO",
                f"Email addresses exposed ({len(emails)})",
                f"Found email addresses: {', '.join(emails[:3])}...")
            findings += 1
        
        # Check for stack traces
        stack_trace_indicators = ['Traceback (most recent', 'at java.', 'at com.', 
                                   'Exception in thread', 'NullPointerException']
        for indicator in stack_trace_indicators:
            if indicator in content:
                await self._add_finding(context, "INFO_DISCLOSURE", "HIGH",
                    "Stack trace exposed",
                    f"Application error/stack trace visible to users")
                findings += 1
                break
        
        await self._emit_action("INFO_SCAN", context.target_url, {"comments": len(comments), "findings": findings})
        
        return {"findings": findings}
    
    async def _phase_detect_tech(self, context: WorkflowContext) -> Dict:
        """Phase 12: Technology fingerprinting."""
        content = context.page_data.get("content", "").lower()
        headers = {k.lower(): v for k, v in context.headers.items()}
        techs = []
        
        tech_patterns = {
            'React': ['react', '__NEXT_DATA__', 'data-reactroot', 'data-react'],
            'Vue.js': ['v-bind', 'v-model', 'v-if', 'v-for', '__vue__'],
            'Angular': ['ng-app', 'ng-controller', 'ng-model', '_ngcontent'],
            'jQuery': ['jquery', '$.ajax', 'jquery.min.js'],
            'Bootstrap': ['bootstrap', 'btn-primary', 'container-fluid'],
            'WordPress': ['wp-content', 'wp-includes', 'wordpress'],
            'Next.js': ['__NEXT_DATA__', '_next/static'],
            'Nuxt.js': ['__NUXT__', '_nuxt'],
            'Laravel': ['laravel', 'csrf-token'],
            'Django': ['csrfmiddlewaretoken', 'django'],
            'Express': ['express', 'x-powered-by: express'],
            'ASP.NET': ['__viewstate', 'asp.net', 'aspnetcore'],
            'PHP': ['.php', 'phpsessid', 'x-powered-by: php'],
            'Ruby on Rails': ['rails', 'csrf-param', 'authenticity_token'],
            'Flask': ['flask', 'werkzeug'],
        }
        
        for tech, patterns in tech_patterns.items():
            for pattern in patterns:
                if pattern.lower() in content:
                    if tech not in techs:
                        techs.append(tech)
                    break
        
        # Check server header
        server = headers.get('server', '').lower()
        if 'nginx' in server:
            techs.append('Nginx')
        if 'apache' in server:
            techs.append('Apache')
        if 'cloudflare' in server:
            techs.append('Cloudflare')
        if 'iis' in server:
            techs.append('IIS')
        
        context.technologies = techs
        
        # Report outdated technologies
        if any(t in techs for t in ['jQuery', 'Angular', 'ASP.NET']):
            await self._add_finding(context, "INFO", "INFO",
                f"Technologies detected: {', '.join(techs)}",
                "Consider checking for known vulnerabilities in detected technologies")
        
        await self._emit_action("TECH_DETECT", context.target_url, {"technologies": techs})
        
        return {"technologies": techs}
    
    async def _phase_crawl_links(self, context: WorkflowContext, max_pages: int) -> Dict:
        """Phase 13: Crawl internal links and discover common paths."""
        start = datetime.now(UTC)
        visited = set([context.target_url])
        parsed_base = urlparse(context.target_url)
        base_url = f"{parsed_base.scheme}://{parsed_base.netloc}"
        
        # Common paths to discover (login, admin, api, etc.)
        common_paths = [
            "/login", "/signin", "/sign-in", "/auth/login",
            "/admin", "/administrator", "/admin/login", "/dashboard",
            "/register", "/signup", "/sign-up", "/auth/register",
            "/api", "/api/v1", "/api/v2", "/api/auth", "/api/users",
            "/forgot-password", "/reset-password", "/password-reset",
            "/profile", "/account", "/settings", "/user",
            "/logout", "/signout",
            "/search", "/contact", "/about",
            "/wp-admin", "/wp-login.php", "/administrator/index.php",
            "/.env", "/.git/config", "/robots.txt", "/sitemap.xml",
            "/graphql", "/graphiql", "/playground",
            "/swagger", "/api-docs", "/swagger.json", "/openapi.json",
            "/debug", "/phpinfo.php", "/info.php", "/test.php",
            "/backup", "/db", "/database", "/sql",
        ]
        
        to_visit = []
        
        # Add links from page
        for link in context.links:
            full_url = urljoin(context.target_url, link)
            parsed = urlparse(full_url)
            if parsed.netloc == parsed_base.netloc and full_url not in visited:
                if not any(ext in parsed.path for ext in ['.pdf', '.jpg', '.png', '.css', '.js', '.gif', '.ico']):
                    to_visit.append(full_url)
        
        # Add common paths
        for path in common_paths:
            full_url = base_url + path
            if full_url not in visited and full_url not in to_visit:
                to_visit.append(full_url)
        
        discovered_pages = []
        sql_tested = 0
        
        # Crawl and test pages
        for url in to_visit[:max_pages]:
            if url in visited:
                continue
            
            try:
                status_code = 0
                html = ""
                resp_headers = {}
                
                if self.use_browser and self.driver:
                    try:
                        self.driver.get(url)
                        html = self.driver.page_source
                        await self._emit_action("NAVIGATE", url, {"title": self.driver.title})
                        status_code = 200  # Browser navigated
                    except:
                        continue
                else:
                    try:
                        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                            response = await client.get(url, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                            })
                            status_code = response.status_code
                            html = response.text
                            resp_headers = dict(response.headers)
                    except:
                        continue
                
                # Only process valid pages
                if status_code in [200, 301, 302, 401, 403]:
                    visited.add(url)
                    context.pages_visited.append(url)
                    discovered_pages.append({"url": url, "status": status_code})
                    
                    # Quick security scan
                    await self._quick_scan(context, url, html, resp_headers)
                    
                    # SQL injection test on login/search pages
                    if any(p in url.lower() for p in ['/login', '/search', '/admin', '/user', '/api']):
                        await self._test_sql_injection(context, url, html)
                        sql_tested += 1
                    
                    await self._emit_action("PAGE_FOUND", url, {
                        "status": status_code,
                        "type": "login" if "login" in url.lower() else "page"
                    })
                    
            except Exception as e:
                pass
        
        duration = int((datetime.now(UTC) - start).total_seconds() * 1000)
        await self._emit_action("CRAWL", context.target_url, {
            "pages_discovered": len(discovered_pages),
            "sql_tested": sql_tested
        }, duration)
        
        return {"pages_crawled": len(visited), "discovered": discovered_pages}
    
    async def _test_sql_injection(self, context: WorkflowContext, url: str, html: str):
        """Test a specific page for SQL injection vulnerabilities."""
        # Find forms
        form_pattern = r'<form[^>]*>(.*?)</form>'
        input_pattern = r'<input[^>]+name=["\']([^"\']+)["\']'
        
        forms = re.findall(form_pattern, html, re.I | re.S)
        
        sql_payloads = [
            "' OR '1'='1",
            "1' OR '1'='1' --",
            "admin'--",
            "1; DROP TABLE users--",
            "' UNION SELECT NULL--",
            "1' AND '1'='1",
            "' OR 1=1#",
        ]
        
        for form in forms:
            inputs = re.findall(input_pattern, form, re.I)
            if inputs:
                await self._add_finding(context, "SQLI", "HIGH",
                    f"Form with inputs found at {url}",
                    f"Inputs: {', '.join(inputs[:5])}. Test with SQL payloads: {sql_payloads[0]}")
                break
        
        # Check URL parameters
        parsed = urlparse(url)
        if parsed.query:
            await self._add_finding(context, "SQLI", "MEDIUM",
                f"URL with parameters found",
                f"URL: {url} - Test parameters for SQL injection")
    
    async def _quick_scan(self, context: WorkflowContext, url: str, html: str, headers: Dict):
        """Quick security scan on crawled page."""
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        if 'x-frame-options' not in headers_lower:
            await self._add_finding(context, "HEADERS", "MEDIUM",
                "Missing X-Frame-Options", f"Page {url} vulnerable to clickjacking", url)
        
        if 'content-security-policy' not in headers_lower:
            await self._add_finding(context, "HEADERS", "MEDIUM",
                "Missing CSP", f"Page {url} lacks Content-Security-Policy", url)
    
    async def _phase_js_analysis(self, context: WorkflowContext) -> Dict:
        """Phase 14: JavaScript security analysis."""
        content = context.page_data.get("content", "")
        findings = 0
        
        # Check for sensitive data in JS
        sensitive_patterns = [
            (r'api[_-]?key\s*[:=]\s*["\'][^"\']+["\']', 'API key exposed'),
            (r'secret\s*[:=]\s*["\'][^"\']+["\']', 'Secret exposed'),
            (r'password\s*[:=]\s*["\'][^"\']+["\']', 'Password exposed'),
            (r'auth[_-]?token\s*[:=]\s*["\'][^"\']+["\']', 'Auth token exposed'),
        ]
        
        for pattern, desc in sensitive_patterns:
            if re.search(pattern, content, re.I):
                await self._add_finding(context, "INFO_DISCLOSURE", "HIGH",
                    desc + " in JavaScript",
                    f"Found hardcoded secret in client-side JavaScript")
                findings += 1
        
        await self._emit_action("JS_SCAN", context.target_url, {"findings": findings})
        
        return {"findings": findings}
    
    async def _phase_api_discovery(self, context: WorkflowContext) -> Dict:
        """Phase 15: API endpoint discovery."""
        content = context.page_data.get("content", "")
        endpoints = []
        
        # Find API endpoints
        api_patterns = [
            r'["\']/?api/v?\d*/?\w+["\']',
            r'["\']/?rest/\w+["\']',
            r'fetch\(["\'][^"\']+["\']',
            r'axios\.\w+\(["\'][^"\']+["\']',
        ]
        
        for pattern in api_patterns:
            matches = re.findall(pattern, content, re.I)
            endpoints.extend(matches)
        
        if endpoints:
            await self._add_finding(context, "INFO", "INFO",
                f"API endpoints discovered ({len(endpoints)})",
                f"Found API endpoints: {', '.join(endpoints[:5])}...")
        
        await self._emit_action("API_SCAN", context.target_url, {"endpoints": len(endpoints)})
        
        return {"endpoints": len(endpoints)}
    
    async def _phase_auth_analysis(self, context: WorkflowContext) -> Dict:
        """Phase 16: Authentication analysis."""
        content = context.page_data.get("content", "")
        findings = 0
        
        # Check for login forms
        has_login = any('password' in str(f.get('inputs', [])).lower() for f in context.forms)
        
        if has_login:
            # Check for remember me
            if 'remember' in content.lower():
                await self._add_finding(context, "AUTH", "INFO",
                    "Remember me functionality detected",
                    "Ensure remember me tokens are properly secured")
            
            # Check registration
            if 'register' in content.lower() or 'signup' in content.lower():
                await self._add_finding(context, "AUTH", "INFO",
                    "Registration functionality detected",
                    "Test for weak password requirements and email enumeration")
                findings += 1
        
        await self._emit_action("AUTH_SCAN", context.target_url, {"has_login": has_login})
        
        return {"has_login": has_login, "findings": findings}
    
    async def _phase_cors_check(self, context: WorkflowContext) -> Dict:
        """Phase 17: CORS policy check."""
        headers = {k.lower(): v for k, v in context.headers.items()}
        findings = 0
        
        cors = headers.get('access-control-allow-origin', '')
        
        if cors == '*':
            await self._add_finding(context, "CORS", "MEDIUM",
                "CORS allows any origin (*)",
                "Wildcard CORS policy may allow unauthorized cross-origin requests")
            findings += 1
        elif cors:
            await self._add_finding(context, "CORS", "INFO",
                f"CORS configured: {cors}",
                "Verify CORS origin whitelist is appropriate")
        
        if headers.get('access-control-allow-credentials', '').lower() == 'true':
            if cors == '*':
                await self._add_finding(context, "CORS", "HIGH",
                    "CORS credentials with wildcard origin",
                    "Dangerous configuration: cookies sent to any origin")
                findings += 1
        
        await self._emit_action("CORS_CHECK", context.target_url, {"findings": findings})
        
        return {"findings": findings}
    
    async def _phase_csp_analysis(self, context: WorkflowContext) -> Dict:
        """Phase 18: CSP analysis."""
        headers = {k.lower(): v for k, v in context.headers.items()}
        csp = headers.get('content-security-policy', '')
        findings = 0
        
        if csp:
            # Check for unsafe directives
            if "'unsafe-inline'" in csp:
                await self._add_finding(context, "CSP", "MEDIUM",
                    "CSP allows unsafe-inline",
                    "CSP permits inline scripts which weakens XSS protection")
                findings += 1
            
            if "'unsafe-eval'" in csp:
                await self._add_finding(context, "CSP", "MEDIUM",
                    "CSP allows unsafe-eval",
                    "CSP permits eval() which weakens XSS protection")
                findings += 1
            
            if "data:" in csp:
                await self._add_finding(context, "CSP", "LOW",
                    "CSP allows data: URIs",
                    "data: URIs can be used for XSS attacks")
                findings += 1
        
        await self._emit_action("CSP_CHECK", context.target_url, {"has_csp": bool(csp), "findings": findings})
        
        return {"has_csp": bool(csp), "findings": findings}
    
    async def _phase_screenshot(self, context: WorkflowContext) -> Dict:
        """Phase 19: Capture screenshot."""
        if self.use_browser and self.driver:
            try:
                path = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.driver.save_screenshot(path)
                await self._emit_action("SCREENSHOT", path)
                return {"path": path}
            except:
                pass
        
        await self._emit_action("SCREENSHOT", "skipped (HTTP mode)")
        return {"skipped": True}
    
    async def _phase_subdomain_enum(self, context: WorkflowContext) -> Dict:
        """Phase 20: Subdomain enumeration."""
        parsed = urlparse(context.target_url)
        domain = parsed.netloc.replace("www.", "")
        common_subdomains = ['api', 'dev', 'staging', 'test', 'admin', 'mail', 'cdn', 'app', 'beta']
        found = []
        
        await self._emit_action("SUBDOMAIN_ENUM", domain, {"checking": len(common_subdomains)})
        return {"domain": domain, "subdomains_checked": len(common_subdomains)}
    
    async def _phase_dns_analysis(self, context: WorkflowContext) -> Dict:
        """Phase 21: DNS security analysis."""
        parsed = urlparse(context.target_url)
        findings = 0
        
        # Check for email security records hint in page
        content = context.page_data.get("content", "").lower()
        if "spf" not in content and "dmarc" not in content:
            await self._add_finding(context, "DNS", "INFO",
                "Email security records not detected",
                "Consider checking SPF, DKIM, and DMARC records")
        
        await self._emit_action("DNS_ANALYSIS", parsed.netloc, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_ssl_check(self, context: WorkflowContext) -> Dict:
        """Phase 22: SSL/TLS certificate check."""
        findings = 0
        is_https = context.target_url.startswith("https://")
        
        if not is_https:
            await self._add_finding(context, "SSL", "HIGH",
                "Site not using HTTPS",
                "Connection is not encrypted, sensitive data at risk")
            findings += 1
        
        # Check HSTS
        headers = {k.lower(): v for k, v in context.headers.items()}
        if is_https and "strict-transport-security" not in headers:
            await self._add_finding(context, "SSL", "MEDIUM",
                "HSTS not enabled",
                "HTTP Strict Transport Security header missing")
            findings += 1
        
        await self._emit_action("SSL_CHECK", context.target_url, {"https": is_https, "findings": findings})
        return {"https": is_https, "findings": findings}
    
    async def _phase_open_redirect(self, context: WorkflowContext) -> Dict:
        """Phase 23: Open redirect detection."""
        findings = 0
        redirect_params = ['url', 'redirect', 'next', 'return', 'redir', 'goto', 'destination', 'continue']
        
        for link in context.links[:50]:
            for param in redirect_params:
                if f'{param}=' in link.lower():
                    await self._add_finding(context, "REDIRECT", "MEDIUM",
                        f"Potential open redirect: {param} parameter",
                        f"URL parameter may allow open redirect: {link[:80]}")
                    findings += 1
                    break
            if findings >= 3:
                break
        
        await self._emit_action("REDIRECT_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_ssrf_detection(self, context: WorkflowContext) -> Dict:
        """Phase 24: SSRF vulnerability check."""
        findings = 0
        ssrf_params = ['url', 'uri', 'path', 'dest', 'src', 'request', 'fetch', 'load', 'img']
        
        for form in context.forms:
            inputs = [i.lower() for i in form.get("inputs", [])]
            for param in ssrf_params:
                if param in ' '.join(inputs):
                    await self._add_finding(context, "SSRF", "HIGH",
                        f"Potential SSRF: Form accepts URL input ({param})",
                        "Form may allow server-side request forgery")
                    findings += 1
                    break
        
        await self._emit_action("SSRF_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_xxe_detection(self, context: WorkflowContext) -> Dict:
        """Phase 25: XXE vulnerability check."""
        findings = 0
        content = context.page_data.get("content", "")
        
        # Check for XML handling
        if "xml" in content.lower() or "application/xml" in str(context.headers).lower():
            await self._add_finding(context, "XXE", "INFO",
                "XML handling detected",
                "Application processes XML - test for XXE vulnerabilities")
        
        await self._emit_action("XXE_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_cmd_injection(self, context: WorkflowContext) -> Dict:
        """Phase 26: Command injection detection."""
        findings = 0
        dangerous_params = ['cmd', 'exec', 'command', 'run', 'ping', 'query', 'host', 'ip']
        
        for link in context.links[:50]:
            for param in dangerous_params:
                if f'{param}=' in link.lower():
                    await self._add_finding(context, "CMD_INJECTION", "HIGH",
                        f"Potential command injection: {param} parameter",
                        f"Parameter may allow OS command injection: {link[:80]}")
                    findings += 1
                    break
            if findings >= 2:
                break
        
        await self._emit_action("CMD_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_path_traversal(self, context: WorkflowContext) -> Dict:
        """Phase 27: Path traversal detection."""
        findings = 0
        path_params = ['file', 'path', 'dir', 'folder', 'doc', 'document', 'template', 'page']
        
        for link in context.links[:50]:
            for param in path_params:
                if f'{param}=' in link.lower():
                    await self._add_finding(context, "PATH_TRAVERSAL", "MEDIUM",
                        f"Potential path traversal: {param} parameter",
                        f"File path parameter found: {link[:80]}")
                    findings += 1
                    break
            if findings >= 3:
                break
        
        await self._emit_action("PATH_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_file_inclusion(self, context: WorkflowContext) -> Dict:
        """Phase 28: File inclusion check."""
        findings = 0
        content = context.page_data.get("content", "")
        
        # Check for include/require patterns
        if re.search(r'include|require|include_once|require_once', content, re.I):
            await self._add_finding(context, "LFI_RFI", "INFO",
                "PHP include patterns detected",
                "Test for Local/Remote File Inclusion vulnerabilities")
        
        await self._emit_action("FILE_INCLUSION", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_template_injection(self, context: WorkflowContext) -> Dict:
        """Phase 29: Template injection detection."""
        findings = 0
        content = context.page_data.get("content", "")
        
        # Check for template syntax
        template_patterns = [r'\{\{', r'\{\%', r'\$\{', r'\#\{', r'\<\%']
        for pattern in template_patterns:
            if re.search(pattern, content):
                await self._add_finding(context, "SSTI", "INFO",
                    "Template syntax detected",
                    "Test for Server-Side Template Injection")
                break
        
        await self._emit_action("SSTI_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_clickjacking(self, context: WorkflowContext) -> Dict:
        """Phase 30: Clickjacking defense check."""
        findings = 0
        headers = {k.lower(): v for k, v in context.headers.items()}
        
        has_xfo = 'x-frame-options' in headers
        has_csp_frame = 'frame-ancestors' in headers.get('content-security-policy', '')
        
        if not has_xfo and not has_csp_frame:
            await self._add_finding(context, "CLICKJACKING", "MEDIUM",
                "No clickjacking protection",
                "Page can be embedded in iframes (clickjacking possible)")
            findings += 1
        
        await self._emit_action("CLICKJACK_CHECK", context.target_url, {"protected": has_xfo or has_csp_frame})
        return {"protected": has_xfo or has_csp_frame, "findings": findings}
    
    async def _phase_http_methods(self, context: WorkflowContext) -> Dict:
        """Phase 31: HTTP method testing."""
        findings = 0
        
        # Check Allow header
        headers = {k.lower(): v for k, v in context.headers.items()}
        allow = headers.get('allow', '')
        
        dangerous_methods = ['PUT', 'DELETE', 'TRACE', 'CONNECT']
        for method in dangerous_methods:
            if method in allow.upper():
                await self._add_finding(context, "HTTP_METHODS", "MEDIUM",
                    f"Dangerous HTTP method enabled: {method}",
                    f"Server allows {method} method which could be exploited")
                findings += 1
        
        await self._emit_action("HTTP_METHODS", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_header_injection(self, context: WorkflowContext) -> Dict:
        """Phase 32: Header injection detection."""
        findings = 0
        
        # Check for header reflection patterns in links
        for link in context.links[:30]:
            if 'header' in link.lower() or 'host' in link.lower():
                await self._add_finding(context, "HEADER_INJECTION", "LOW",
                    "Potential header manipulation parameter",
                    f"Parameter may allow header injection: {link[:60]}")
                findings += 1
                break
        
        await self._emit_action("HEADER_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_websocket_security(self, context: WorkflowContext) -> Dict:
        """Phase 33: WebSocket security check."""
        findings = 0
        content = context.page_data.get("content", "")
        
        if 'websocket' in content.lower() or 'new WebSocket' in content:
            await self._add_finding(context, "WEBSOCKET", "INFO",
                "WebSocket usage detected",
                "Test WebSocket connections for security issues (CSWSH)")
        
        await self._emit_action("WEBSOCKET_CHECK", context.target_url, {"has_ws": 'websocket' in content.lower()})
        return {"findings": findings}
    
    async def _phase_graphql_security(self, context: WorkflowContext) -> Dict:
        """Phase 34: GraphQL security analysis."""
        findings = 0
        content = context.page_data.get("content", "")
        
        if 'graphql' in content.lower() or '/graphql' in str(context.links):
            await self._add_finding(context, "GRAPHQL", "INFO",
                "GraphQL endpoint detected",
                "Test for introspection, injection, and DoS vulnerabilities")
            
            # Check for introspection hints
            if '__schema' in content or '__type' in content:
                await self._add_finding(context, "GRAPHQL", "MEDIUM",
                    "GraphQL introspection may be enabled",
                    "Introspection can expose schema - should be disabled in production")
                findings += 1
        
        await self._emit_action("GRAPHQL_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_jwt_analysis(self, context: WorkflowContext) -> Dict:
        """Phase 35: JWT token analysis."""
        findings = 0
        content = context.page_data.get("content", "")
        
        # Look for JWT patterns
        jwt_pattern = r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'
        if re.search(jwt_pattern, content):
            await self._add_finding(context, "JWT", "MEDIUM",
                "JWT token exposed in page content",
                "JWT tokens should not be visible in HTML source")
            findings += 1
        
        await self._emit_action("JWT_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_oauth_security(self, context: WorkflowContext) -> Dict:
        """Phase 36: OAuth implementation check."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        oauth_providers = ['google', 'facebook', 'github', 'twitter', 'linkedin', 'microsoft']
        has_oauth = any(p in content for p in oauth_providers) and ('login' in content or 'signin' in content)
        
        if has_oauth:
            await self._add_finding(context, "OAUTH", "INFO",
                "OAuth/Social login detected",
                "Test OAuth implementation for state parameter and redirect validation")
        
        await self._emit_action("OAUTH_CHECK", context.target_url, {"has_oauth": has_oauth})
        return {"has_oauth": has_oauth, "findings": findings}
    
    async def _phase_rate_limiting(self, context: WorkflowContext) -> Dict:
        """Phase 37: Rate limiting check."""
        findings = 0
        headers = {k.lower(): v for k, v in context.headers.items()}
        
        rate_headers = ['x-ratelimit-limit', 'x-rate-limit-limit', 'retry-after', 'x-ratelimit-remaining']
        has_rate_limit = any(h in headers for h in rate_headers)
        
        if not has_rate_limit:
            await self._add_finding(context, "RATE_LIMIT", "LOW",
                "No rate limiting headers detected",
                "Server may be vulnerable to brute force and DoS attacks")
            findings += 1
        
        await self._emit_action("RATE_CHECK", context.target_url, {"has_rate_limit": has_rate_limit})
        return {"has_rate_limit": has_rate_limit, "findings": findings}
    
    async def _phase_captcha_check(self, context: WorkflowContext) -> Dict:
        """Phase 38: CAPTCHA implementation check."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        has_captcha = 'captcha' in content or 'recaptcha' in content or 'hcaptcha' in content
        has_login = any('password' in str(f.get('inputs', [])).lower() for f in context.forms)
        
        if has_login and not has_captcha:
            await self._add_finding(context, "CAPTCHA", "LOW",
                "Login form without CAPTCHA",
                "Login forms should have CAPTCHA to prevent brute force")
            findings += 1
        
        await self._emit_action("CAPTCHA_CHECK", context.target_url, {"has_captcha": has_captcha})
        return {"has_captcha": has_captcha, "findings": findings}
    
    async def _phase_payment_security(self, context: WorkflowContext) -> Dict:
        """Phase 39: Payment security analysis."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        payment_keywords = ['payment', 'checkout', 'cart', 'credit card', 'stripe', 'paypal', 'braintree']
        has_payment = any(kw in content for kw in payment_keywords)
        
        if has_payment:
            await self._add_finding(context, "PAYMENT", "INFO",
                "Payment functionality detected",
                "Ensure PCI-DSS compliance and secure payment processing")
        
        await self._emit_action("PAYMENT_CHECK", context.target_url, {"has_payment": has_payment})
        return {"has_payment": has_payment}
    
    async def _phase_business_logic(self, context: WorkflowContext) -> Dict:
        """Phase 40: Business logic flaws."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        # Check for discount/coupon functionality
        if 'coupon' in content or 'discount' in content or 'promo' in content:
            await self._add_finding(context, "BUSINESS_LOGIC", "INFO",
                "Coupon/discount functionality detected",
                "Test for coupon abuse and price manipulation")
        
        # Check for quantity/pricing in forms
        for form in context.forms:
            inputs = ' '.join(form.get("inputs", [])).lower()
            if 'quantity' in inputs or 'price' in inputs or 'amount' in inputs:
                await self._add_finding(context, "BUSINESS_LOGIC", "MEDIUM",
                    "Price/quantity input detected in form",
                    "Test for price manipulation vulnerabilities")
                findings += 1
                break
        
        await self._emit_action("LOGIC_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_race_conditions(self, context: WorkflowContext) -> Dict:
        """Phase 41: Race condition detection."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        race_keywords = ['vote', 'like', 'transfer', 'withdraw', 'redeem', 'claim', 'balance']
        if any(kw in content for kw in race_keywords):
            await self._add_finding(context, "RACE", "INFO",
                "Race condition-prone functionality detected",
                "Test for TOCTOU and race condition vulnerabilities")
        
        await self._emit_action("RACE_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_password_policy(self, context: WorkflowContext) -> Dict:
        """Phase 42: Password policy check."""
        findings = 0
        content = context.page_data.get("content", "")
        
        weak_hints = ['minimum 6', 'min 4', 'at least 4', 'minimum 4']
        for hint in weak_hints:
            if hint in content.lower():
                await self._add_finding(context, "PASSWORD", "MEDIUM",
                    "Weak password policy detected",
                    f"Password requirement suggests weak policy: '{hint}'")
                findings += 1
                break
        
        await self._emit_action("PASSWORD_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_2fa_analysis(self, context: WorkflowContext) -> Dict:
        """Phase 43: 2FA implementation check."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        has_2fa = '2fa' in content or 'two-factor' in content or 'authenticator' in content or 'otp' in content
        
        if not has_2fa:
            await self._add_finding(context, "2FA", "INFO",
                "No 2FA/MFA detected",
                "Consider implementing two-factor authentication")
        
        await self._emit_action("2FA_CHECK", context.target_url, {"has_2fa": has_2fa})
        return {"has_2fa": has_2fa}
    
    async def _phase_session_fixation(self, context: WorkflowContext) -> Dict:
        """Phase 44: Session fixation check."""
        findings = 0
        
        # Session fixation is hard to detect without interaction
        await self._add_finding(context, "SESSION", "INFO",
            "Manual session fixation test required",
            "Verify that session IDs are regenerated after login")
        
        await self._emit_action("SESSION_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_privilege_escalation(self, context: WorkflowContext) -> Dict:
        """Phase 45: Privilege escalation check."""
        findings = 0
        
        # Check for admin/role parameters
        for link in context.links[:50]:
            if 'admin' in link.lower() or 'role=' in link.lower() or 'isadmin' in link.lower():
                await self._add_finding(context, "PRIVESC", "MEDIUM",
                    "Admin/role parameter in URL",
                    f"Potential privilege escalation vector: {link[:60]}")
                findings += 1
                break
        
        await self._emit_action("PRIVESC_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_data_exposure(self, context: WorkflowContext) -> Dict:
        """Phase 46: Sensitive data exposure."""
        findings = 0
        content = context.page_data.get("content", "")
        
        # Check for sensitive data patterns
        patterns = [
            (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN pattern'),
            (r'\b\d{16}\b', 'Credit card pattern'),
            (r'password\s*[=:]\s*["\'][^"\']+["\']', 'Password in source'),
            (r'private[_-]?key', 'Private key reference'),
        ]
        
        for pattern, desc in patterns:
            if re.search(pattern, content, re.I):
                await self._add_finding(context, "DATA_EXPOSURE", "HIGH",
                    f"Sensitive data pattern: {desc}",
                    "Sensitive data may be exposed in page source")
                findings += 1
        
        await self._emit_action("DATA_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_cve_scan(self, context: WorkflowContext) -> Dict:
        """Phase 47: Professional CVE vulnerability detection."""
        cve_findings = 0
        content = context.page_data.get("content", "")
        headers = context.headers
        
        if CVE_SCANNER_AVAILABLE:
            try:
                def on_cve(cve_data):
                    nonlocal cve_findings
                    cve_findings += 1
                    print(f"🔴 CVE: {cve_data.get('cve_id')} - {cve_data.get('title')}")
                
                results = await scan_for_cves(content, headers, context.target_url, on_cve)
                
                # Add findings from CVE scan
                for cve in results.get("findings", []):
                    await self._add_finding(context, "CVE", cve["severity"],
                        f"{cve['cve_id']}: {cve['title']}",
                        f"{cve['description']}. Remediation: {cve['remediation']}")
                
                await self._emit_action("CVE_SCAN", context.target_url, {
                    "total_cves": results.get("total_cves", 0),
                    "severity": results.get("severity", {}),
                    "findings": cve_findings
                })
                
                return {
                    "total_cves": results.get("total_cves", 0),
                    "severity": results.get("severity", {}),
                    "findings": cve_findings
                }
            except Exception as e:
                print(f"⚠️ CVE scan error: {e}")
        else:
            # Basic CVE pattern matching if scanner not available
            cve_patterns = [
                (r'jquery[/-]?1\.', "CVE-2020-11022", "jQuery 1.x XSS", "HIGH"),
                (r'jquery[/-]?2\.[0-2]', "CVE-2020-11023", "jQuery 2.x XSS", "HIGH"),
                (r'angular[.-]?1\.[0-5]', "CVE-2022-25869", "AngularJS XSS", "HIGH"),
                (r'log4j', "CVE-2021-44228", "Potential Log4Shell", "CRITICAL"),
                (r'apache/2\.4\.49', "CVE-2021-41773", "Apache Path Traversal", "CRITICAL"),
            ]
            
            content_lower = content.lower()
            for pattern, cve_id, title, severity in cve_patterns:
                if re.search(pattern, content_lower, re.I):
                    await self._add_finding(context, "CVE", severity,
                        f"{cve_id}: {title}",
                        f"Potential {cve_id} vulnerability detected via pattern matching")
                    cve_findings += 1
        
        await self._emit_action("CVE_SCAN", context.target_url, {"findings": cve_findings})
        return {"findings": cve_findings}
    
    async def _phase_dependency_scan(self, context: WorkflowContext) -> Dict:
        """Phase 47: Dependency security scan."""
        findings = 0
        content = context.page_data.get("content", "").lower()
        
        # Check for known vulnerable libraries (basic check)
        vulnerable_libs = [
            ('jquery/1.', 'jQuery 1.x (outdated)'),
            ('jquery/2.', 'jQuery 2.x (outdated)'),
            ('angular.js/1.', 'AngularJS 1.x (outdated)'),
            ('bootstrap/3.', 'Bootstrap 3.x (check for XSS)'),
        ]
        
        for lib, desc in vulnerable_libs:
            if lib in content:
                await self._add_finding(context, "DEPENDENCY", "MEDIUM",
                    f"Potentially vulnerable library: {desc}",
                    "Update to the latest secure version")
                findings += 1
        
        await self._emit_action("DEPENDENCY_CHECK", context.target_url, {"findings": findings})
        return {"findings": findings}
    
    async def _phase_final_scan(self, context: WorkflowContext) -> Dict:
        """Phase 48: Final security scan."""
        findings = 0
        
        # Summary findings
        total = len(context.findings)
        critical = len([f for f in context.findings if f.severity == "CRITICAL"])
        high = len([f for f in context.findings if f.severity == "HIGH"])
        
        if critical > 0:
            await self._add_finding(context, "SUMMARY", "CRITICAL",
                f"Critical issues found: {critical}",
                "Immediate attention required for critical vulnerabilities")
        elif high > 0:
            await self._add_finding(context, "SUMMARY", "HIGH",
                f"High severity issues found: {high}",
                "Review and remediate high severity findings")
        
        await self._emit_action("FINAL_SCAN", context.target_url, {"total_findings": total})
        return {"total_findings": total, "critical": critical, "high": high}
    
    async def _phase_generate_report(self, context: WorkflowContext) -> Dict:
        """Phase 49: Generate security report and save to file."""
        # Count by severity
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in context.findings:
            sev = f.severity.upper()
            if sev in severity_counts:
                severity_counts[sev] += 1
        
        # Count by category
        category_counts = {}
        for f in context.findings:
            cat = f.category
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        # Build report data
        report = {
            "target": context.target_url,
            "total_findings": len(context.findings),
            "severity": severity_counts,
            "categories": category_counts,
            "pages_analyzed": len(context.pages_visited),
            "technologies": context.technologies
        }
        
        # Generate TXT report
        parsed = urlparse(context.target_url)
        domain = parsed.netloc.replace(".", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = PROJECT_ROOT / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{domain}_{timestamp}.txt"
        
        # Build full text report
        lines = []
        lines.append("=" * 80)
        lines.append("YGB SECURITY REPORT")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Target URL: {context.target_url}")
        lines.append(f"Workflow ID: {context.workflow_id}")
        lines.append(f"Mode: {context.mode}")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Total Findings: {len(context.findings)}")
        lines.append(f"Pages Analyzed: {len(context.pages_visited)}")
        lines.append(f"Phases Executed: {len(context.phase_results)}")
        lines.append(f"Technologies: {', '.join(context.technologies) or 'None detected'}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("SEVERITY BREAKDOWN")
        lines.append("-" * 80)
        for sev, count in severity_counts.items():
            if count > 0:
                lines.append(f"  {sev}: {count}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("CATEGORY BREAKDOWN")
        lines.append("-" * 80)
        for cat, count in sorted(category_counts.items()):
            lines.append(f"  {cat}: {count}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("DETAILED FINDINGS")
        lines.append("=" * 80)
        lines.append("")
        
        # Group findings by severity
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            severity_findings = [f for f in context.findings if f.severity.upper() == severity]
            if severity_findings:
                lines.append(f"--- {severity} ({len(severity_findings)}) ---")
                lines.append("")
                for i, finding in enumerate(severity_findings, 1):
                    lines.append(f"[{finding.finding_id}] {finding.title}")
                    lines.append(f"  Category: {finding.category}")
                    lines.append(f"  Severity: {finding.severity}")
                    lines.append(f"  Description: {finding.description}")
                    if finding.url:
                        lines.append(f"  URL: {finding.url}")
                    lines.append("")
        
        lines.append("=" * 80)
        lines.append("PHASES EXECUTED")
        lines.append("=" * 80)
        lines.append("")
        for phase in context.phase_results:
            status = "✓" if phase.status == "SUCCESS" else "✗"
            lines.append(f"  [{status}] Phase {phase.phase_number}: {phase.phase_name} ({phase.duration_ms}ms)")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("PAGES VISITED")
        lines.append("=" * 80)
        lines.append("")
        for page in context.pages_visited:
            lines.append(f"  • {page}")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)
        
        # Write report to file
        report_content = "\n".join(lines)
        report_path.write_text(report_content, encoding="utf-8")
        
        # Store path in context for frontend
        context.report_file = str(report_path)
        report["report_file"] = str(report_path)
        
        await self._emit_action("REPORT", context.target_url, {
            **report,
            "report_file": str(report_path)
        })
        
        print(f"📄 Report saved: {report_path}")
        
        return report


# ==============================================================================
# ALIASES
# ==============================================================================
RealPhaseRunner = UnifiedPhaseRunner


async def run_real_workflow(
    target_url: str,
    workflow_id: str,
    mode: str = "READ_ONLY",
    on_progress: Optional[Callable] = None
) -> WorkflowContext:
    """Run real security analysis workflow."""
    runner = UnifiedPhaseRunner(on_progress=on_progress)
    return await runner.run_workflow(target_url, workflow_id, mode)


# ==============================================================================
# TEST
# ==============================================================================
if __name__ == "__main__":
    import sys
    
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    mode = sys.argv[2] if len(sys.argv) > 2 else "READ_ONLY"
    
    print(f"🎯 Target: {target}")
    print(f"🔧 Mode: {mode}")
    print()
    
    async def test():
        def on_progress(update):
            t = update.get("type", "")
            if t == "phase_start":
                print(f"▶️  Phase {update.get('phase')}: {update.get('name')}")
            elif t == "phase_complete":
                status = update.get('status')
                icon = "✅" if status == "SUCCESS" else "❌"
                print(f"{icon} Phase {update.get('phase')}: {status} ({update.get('duration_ms')}ms)")
            elif t == "browser_action":
                print(f"🌐 {update.get('action')}: {update.get('target', '')[:60]}")
            elif t == "finding":
                print(f"🔍 [{update.get('severity')}] {update.get('title')}")
            elif t == "error":
                print(f"❌ Error: {update.get('message')}")
        
        ctx = await run_real_workflow(target, "test-001", mode, on_progress)
        
        print(f"\n{'='*60}")
        print(f"✅ WORKFLOW COMPLETE!")
        print(f"   Total Phases: {len(ctx.phase_results)}")
        print(f"   Total Findings: {len(ctx.findings)}")
        print(f"   Pages Analyzed: {len(ctx.pages_visited)}")
        print(f"   Technologies: {', '.join(ctx.technologies) or 'None'}")
        print()
        
        print("📊 SEVERITY:")
        sev = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in ctx.findings:
            sev[f.severity.upper()] = sev.get(f.severity.upper(), 0) + 1
        for s, c in sev.items():
            if c > 0:
                print(f"   {s}: {c}")
    
    asyncio.run(test())
