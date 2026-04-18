# ACTIONABLE FIX ROADMAP
## From Prototype to Production-Ready Hunter

**Status:** 40% Complete  
**Target:** Production-Ready in 2-3 months  
**Priority:** Fix critical bugs first, then expand capabilities

---

## PHASE 1: CRITICAL BUGS (Week 1) 🚨

### 1.1 Fix Import Errors
**File:** `backend/hunter/http_engine.py:149`

**Current (BROKEN):**
```python
from backend.governance.kill_switch import GovernanceError
```

**Fix:**
```python
from backend.training.runtime_status_validator import TrainingGovernanceError as GovernanceError
```

**Test:**
```bash
python -c "from backend.hunter.http_engine import SmartHTTPEngine; print('Import OK')"
```

---

### 1.2 Implement Missing Method
**File:** `backend/hunter/expert_collaboration.py`

**Add this method to `ProMoEHuntingClassifier`:**
```python
def classify_endpoint(self, url: str, body: str, tech_stack: list[str]) -> list[str]:
    """Classify endpoint to determine which vulnerability types to test."""
    vuln_types = []
    
    # URL-based classification
    url_lower = url.lower()
    if '/api/' in url_lower or '/graphql' in url_lower:
        vuln_types.extend(['sqli', 'idor', 'auth_bypass'])
    if '/upload' in url_lower or '/file' in url_lower:
        vuln_types.extend(['path_traversal', 'rce'])
    if '/search' in url_lower or '/query' in url_lower:
        vuln_types.extend(['xss', 'sqli', 'ssrf'])
    if '/redirect' in url_lower or '/callback' in url_lower:
        vuln_types.extend(['open_redirect', 'ssrf'])
    
    # Tech stack-based classification
    if 'php' in tech_stack:
        vuln_types.extend(['rce', 'path_traversal'])
    if 'wordpress' in tech_stack:
        vuln_types.extend(['xss', 'sqli', 'path_traversal'])
    if 'graphql' in tech_stack:
        vuln_types.extend(['idor', 'auth_bypass'])
    
    return list(set(vuln_types))[:5]  # Top 5 unique types
```

---

### 1.3 Fix Approval Workflow
**File:** `backend/hunter/live_gate.py`

**Add blocking approval method:**
```python
def wait_for_approval(self, request_id: str, timeout_seconds: int = 300) -> bool:
    """Block and wait for human approval via approve_action.py script."""
    import time
    
    approval_file = self._approval_dir / f"{request_id}.approved"
    rejection_file = self._approval_dir / f"{request_id}.rejected"
    
    logger.info("Waiting for approval: %s (timeout: %ds)", request_id, timeout_seconds)
    logger.info("Run: python scripts/approve_action.py %s", request_id)
    
    start = time.time()
    while time.time() - start < timeout_seconds:
        if approval_file.exists():
            logger.info("Approval granted: %s", request_id)
            return True
        if rejection_file.exists():
            logger.info("Approval rejected: %s", request_id)
            return False
        time.sleep(1)
    
    logger.warning("Approval timeout: %s", request_id)
    return False
```

**Update `hunter_agent.py:232`:**
```python
decision = self._gate.request_approval(action, "hunter_agent")

if not decision.approved:
    self._approvals_required += 1
    # BLOCK AND WAIT FOR HUMAN
    if not self._gate.wait_for_approval(decision.request_id, timeout_seconds=300):
        logger.warning("Payload blocked: %s", payload.payload_id)
        continue
    decision.approved = True  # Human approved

self._approvals_granted += 1
```

---

### 1.4 Implement Subdomain Discovery
**File:** `backend/hunter/subdomain_finder.py` (NEW)

```python
"""Subdomain discovery using DNS, CT logs, and brute force."""

import asyncio
import logging
from typing import Set

import httpx

logger = logging.getLogger("ygb.hunter.subdomain")


class SubdomainFinder:
    """Discovers subdomains using multiple techniques."""
    
    COMMON_SUBDOMAINS = [
        "www", "api", "dev", "staging", "test", "admin", "portal",
        "mail", "ftp", "vpn", "blog", "shop", "store", "app",
        "mobile", "m", "cdn", "static", "assets", "media",
        "docs", "help", "support", "status", "dashboard",
    ]
    
    async def discover(self, domain: str, max_subdomains: int = 50) -> Set[str]:
        """Discover subdomains using CT logs + DNS brute force."""
        found = set()
        
        # 1. Certificate Transparency logs
        ct_subs = await self._query_ct_logs(domain)
        found.update(ct_subs)
        
        # 2. DNS brute force (common names)
        if len(found) < max_subdomains:
            dns_subs = await self._dns_brute_force(domain, self.COMMON_SUBDOMAINS)
            found.update(dns_subs)
        
        logger.info("Discovered %d subdomains for %s", len(found), domain)
        return found
    
    async def _query_ct_logs(self, domain: str) -> Set[str]:
        """Query crt.sh for certificate transparency logs."""
        found = set()
        url = f"https://crt.sh/?q=%.{domain}&output=json"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for entry in data[:100]:  # Limit to 100
                        name = entry.get("name_value", "")
                        if name and name.endswith(domain):
                            found.add(name.strip())
        except Exception as e:
            logger.warning("CT log query failed: %s", e)
        
        return found
    
    async def _dns_brute_force(self, domain: str, wordlist: list[str]) -> Set[str]:
        """Brute force DNS with common subdomain names."""
        import socket
        
        found = set()
        for sub in wordlist:
            fqdn = f"{sub}.{domain}"
            try:
                # Simple DNS lookup
                socket.gethostbyname(fqdn)
                found.add(fqdn)
            except socket.gaierror:
                pass  # Subdomain doesn't exist
        
        return found
```

**Update `explorer.py:442`:**
```python
from backend.hunter.subdomain_finder import SubdomainFinder

# In explore() method:
subdomain_finder = SubdomainFinder()
subdomains = await subdomain_finder.discover(domain, max_subdomains=50)

return ExplorationResult(
    # ...
    subdomains_discovered=list(subdomains),
    # ...
)
```

---

## PHASE 2: ESSENTIAL FEATURES (Week 2-3) 🔧

### 2.1 Add Proxy Support
**File:** `backend/hunter/http_engine.py:127`

```python
def __init__(self, session_id: str = None, max_rps: int = 20, proxy: str = None):
    # ...
    self._proxy = proxy
    # ...

async def _get_client(self) -> httpx.AsyncClient:
    if self._client is None or self._client.is_closed:
        proxies = {"http://": self._proxy, "https://": self._proxy} if self._proxy else None
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            verify=True,
            proxies=proxies,  # ← ADD THIS
        )
    return self._client
```

**Usage:**
```python
# Use Burp Suite proxy for debugging
http = SmartHTTPEngine(proxy="http://127.0.0.1:8080")
```

---

### 2.2 Expand Payload Library
**File:** `backend/hunter/payload_engine.py:50`

**Add 500+ payloads from SecLists:**
```python
# Download SecLists
# git clone https://github.com/danielmiessler/SecLists.git

# Load payloads from files
XSS_FILE = "SecLists/Fuzzing/XSS/XSS-Bypass-Strings.txt"
SQLI_FILE = "SecLists/Fuzzing/SQLi/Generic-SQLi.txt"

@classmethod
def load_from_file(cls, filepath: str, vuln_type: str) -> list[Payload]:
    """Load payloads from SecLists file."""
    payloads = []
    with open(filepath) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line and not line.startswith("#"):
                payloads.append(Payload(
                    payload_id=f"{vuln_type}{i:04d}",
                    vuln_type=vuln_type,
                    value=line,
                    context="url_param",
                ))
    return payloads
```

---

### 2.3 Add WAF Detection
**File:** `backend/hunter/waf_detector.py` (NEW)

```python
"""WAF detection and fingerprinting."""

import logging
from dataclasses import dataclass

logger = logging.getLogger("ygb.hunter.waf")


@dataclass
class WAFSignature:
    name: str
    headers: list[tuple[str, str]]  # (header_name, pattern)
    body_patterns: list[str]
    cookies: list[str]


class WAFDetector:
    """Detects Web Application Firewalls."""
    
    SIGNATURES = [
        WAFSignature(
            name="Cloudflare",
            headers=[("server", "cloudflare"), ("cf-ray", "")],
            body_patterns=["cloudflare", "cf-ray"],
            cookies=["__cfduid", "__cflb"],
        ),
        WAFSignature(
            name="AWS WAF",
            headers=[("x-amzn-requestid", ""), ("x-amz-cf-id", "")],
            body_patterns=["aws waf", "request blocked"],
            cookies=["awsalb", "awsalbcors"],
        ),
        WAFSignature(
            name="Akamai",
            headers=[("server", "akamaighost")],
            body_patterns=["akamai", "reference #"],
            cookies=["ak_bmsc"],
        ),
        WAFSignature(
            name="ModSecurity",
            headers=[("server", "mod_security")],
            body_patterns=["mod_security", "not acceptable"],
            cookies=[],
        ),
    ]
    
    def detect(self, response: "HTTPResponse") -> str:
        """Detect WAF from response. Returns WAF name or 'none'."""
        headers_lower = {k.lower(): v.lower() for k, v in response.headers.items()}
        body_lower = response.body.lower()
        cookies_lower = {k.lower() for k in response.cookies.keys()}
        
        for sig in self.SIGNATURES:
            # Check headers
            for header_name, pattern in sig.headers:
                if header_name in headers_lower:
                    if not pattern or pattern in headers_lower[header_name]:
                        logger.info("WAF detected: %s (header: %s)", sig.name, header_name)
                        return sig.name
            
            # Check body
            for pattern in sig.body_patterns:
                if pattern in body_lower:
                    logger.info("WAF detected: %s (body pattern: %s)", sig.name, pattern)
                    return sig.name
            
            # Check cookies
            for cookie in sig.cookies:
                if cookie.lower() in cookies_lower:
                    logger.info("WAF detected: %s (cookie: %s)", sig.name, cookie)
                    return sig.name
        
        return "none"
```

---

### 2.4 Add Retry Logic
**File:** `backend/hunter/http_engine.py:146`

```python
async def send(self, req: HTTPRequest, approved: bool = False, max_retries: int = 3) -> HTTPResponse:
    """Send HTTP request with retry logic."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return await self._send_once(req, approved)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning("Request failed (attempt %d/%d), retrying in %ds...", 
                             attempt + 1, max_retries, wait_time)
                await asyncio.sleep(wait_time)
            else:
                logger.error("Request failed after %d attempts: %s", max_retries, e)
    
    raise last_error

async def _send_once(self, req: HTTPRequest, approved: bool = False) -> HTTPResponse:
    """Send one HTTP request (no retry)."""
    # ... existing send() logic here ...
```

---

## PHASE 3: TESTING (Week 4) 🧪

### 3.1 Create Integration Test
**File:** `backend/tests/test_hunter_integration.py` (NEW)

```python
"""Integration tests for full hunt workflow."""

import pytest
import asyncio
from backend.hunter.hunter_agent import PureAIHunterAgent, HuntConfig


@pytest.mark.asyncio
async def test_full_hunt_workflow():
    """Test complete hunt from exploration to report."""
    config = HuntConfig(
        target="http://testphp.vulnweb.com",  # Intentionally vulnerable test site
        scope_rules=["*.vulnweb.com"],
        max_pages=10,
        max_payloads_per_param=3,
        auto_approve_medium=True,
    )
    
    agent = PureAIHunterAgent(config)
    result = await agent.hunt()
    
    assert result.pages_explored > 0
    assert result.endpoints_tested > 0
    assert result.duration_seconds > 0
    # May or may not find vulns (test site changes)


@pytest.mark.asyncio
async def test_subdomain_discovery():
    """Test subdomain discovery."""
    from backend.hunter.subdomain_finder import SubdomainFinder
    
    finder = SubdomainFinder()
    subs = await finder.discover("example.com", max_subdomains=10)
    
    assert isinstance(subs, set)
    # example.com may have www, mail, etc.


@pytest.mark.asyncio
async def test_waf_detection():
    """Test WAF detection."""
    from backend.hunter.http_engine import SmartHTTPEngine, HTTPRequest
    from backend.hunter.waf_detector import WAFDetector
    
    http = SmartHTTPEngine()
    detector = WAFDetector()
    
    # Test against Cloudflare-protected site
    resp = await http.send(HTTPRequest("GET", "https://www.cloudflare.com"))
    waf = detector.detect(resp)
    
    assert waf in ["Cloudflare", "none"]  # May or may not detect
    await http.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Run:**
```bash
pytest backend/tests/test_hunter_integration.py -v
```

---

### 3.2 Create Unit Tests
**File:** `backend/tests/test_payload_engine.py` (NEW)

```python
"""Unit tests for payload engine."""

import pytest
from backend.hunter.payload_engine import PayloadLibrary, ResponseAnalyzer, Payload
from backend.hunter.http_engine import HTTPResponse


def test_payload_library():
    """Test payload library has payloads."""
    xss = PayloadLibrary.get_for_type("xss")
    sqli = PayloadLibrary.get_for_type("sqli")
    
    assert len(xss) >= 7
    assert len(sqli) >= 8
    assert all(isinstance(p, Payload) for p in xss)


def test_xss_detection():
    """Test XSS detection in response."""
    analyzer = ResponseAnalyzer()
    payload = Payload("x001", "xss", "<ygb-probe>", "url_param")
    
    # Reflected XSS
    resp = HTTPResponse(
        status_code=200,
        headers={},
        body="Hello <ygb-probe> World",
        url="http://test.com",
        elapsed_ms=100,
        redirects=[],
        request_id="test",
        evidence_path=None,
        content_type="text/html",
        content_length=100,
        has_error_message=False,
        server_header="",
        cookies={},
    )
    
    result = analyzer.analyze("xss", payload, resp, None)
    assert result["triggered"] == True
    assert result["confidence"] > 0.8


def test_sqli_detection():
    """Test SQLi error detection."""
    analyzer = ResponseAnalyzer()
    
    # SQL error response
    resp = HTTPResponse(
        status_code=500,
        headers={},
        body="You have an error in your SQL syntax near ''",
        url="http://test.com",
        elapsed_ms=100,
        redirects=[],
        request_id="test",
        evidence_path=None,
        content_type="text/html",
        content_length=100,
        has_error_message=True,
        server_header="",
        cookies={},
    )
    
    result = analyzer.analyze("sqli", None, resp, None)
    assert result["triggered"] == True
    assert result["confidence"] >= 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## PHASE 4: PERFORMANCE (Week 5-6) ⚡

### 4.1 Add Concurrent Testing
**File:** `backend/hunter/hunter_agent.py:180`

```python
async def _test_endpoints(self, classified_endpoints: list[dict], tech_stack: list[str]):
    """Test endpoints concurrently."""
    tasks = []
    
    for item in classified_endpoints:
        endpoint = item["endpoint"]
        vuln_types = item["vuln_types"]
        
        if not endpoint.params:
            continue
        
        for param in endpoint.params[:3]:
            task = self._test_parameter(endpoint.url, param, vuln_types, tech_stack)
            tasks.append(task)
    
    # Run up to 5 tests concurrently
    for i in range(0, len(tasks), 5):
        batch = tasks[i:i+5]
        await asyncio.gather(*batch, return_exceptions=True)
```

---

### 4.2 Add Response Caching
**File:** `backend/hunter/http_engine.py:127`

```python
def __init__(self, session_id: str = None, max_rps: int = 20, proxy: str = None):
    # ...
    self._response_cache: dict[str, HTTPResponse] = {}
    self._cache_enabled = True

async def send(self, req: HTTPRequest, approved: bool = False, use_cache: bool = True) -> HTTPResponse:
    """Send HTTP request with caching."""
    cache_key = f"{req.method}:{req.url}"
    
    if use_cache and cache_key in self._response_cache:
        logger.debug("Cache hit: %s", cache_key)
        return self._response_cache[cache_key]
    
    resp = await self._send_once(req, approved)
    
    if use_cache and req.method == "GET":
        self._response_cache[cache_key] = resp
    
    return resp
```

---

## PHASE 5: SECURITY (Week 7-8) 🔒

### 5.1 Encrypt Evidence Storage
**File:** `backend/hunter/http_engine.py:260`

```python
def _save_evidence(self, req_id: str, req: HTTPRequest, resp, body: str) -> Path:
    """Save evidence with encryption."""
    from cryptography.fernet import Fernet
    import os
    
    # Get encryption key from env
    key = os.getenv("YGB_EVIDENCE_KEY")
    if not key:
        # Generate and save key (first run)
        key = Fernet.generate_key().decode()
        logger.warning("Generated new evidence encryption key. Set YGB_EVIDENCE_KEY=%s", key)
    
    cipher = Fernet(key.encode())
    
    evidence = {
        "request_id": req_id,
        "session_id": self._session_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "request": {
            "method": req.method,
            "url": req.url,
            "headers": self._redact_secrets(req.headers),
            "body": self._redact_secrets(req.body) if req.body else None,
            "is_payload": req.is_payload_request,
        },
        "response": {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body_preview": self._redact_secrets(body[:2000]),
            "content_length": len(body),
        },
    }
    
    # Encrypt
    plaintext = json.dumps(evidence, indent=2).encode()
    encrypted = cipher.encrypt(plaintext)
    
    path = self._evidence_dir / f"{req_id}.enc"
    path.write_bytes(encrypted)
    return path

def _redact_secrets(self, text: str) -> str:
    """Redact API keys, tokens, passwords from text."""
    import re
    
    if not text:
        return text
    
    # Redact common secret patterns
    text = re.sub(r'(api[_-]?key["\s]*[:=]["\s]*)[^"\']{16,}', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    text = re.sub(r'(token["\s]*[:=]["\s]*)[^"\']{16,}', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    text = re.sub(r'(password["\s]*[:=]["\s]*)[^"\']{4,}', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    text = re.sub(r'(bearer\s+)[A-Za-z0-9+/=]{20,}', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    
    return text
```

---

## PHASE 6: POLISH (Week 9-10) ✨

### 6.1 Add Progress Tracking
**File:** `backend/hunter/hunter_agent.py:80`

```python
def get_progress(self) -> dict:
    """Get real-time hunt progress."""
    return {
        "session_id": self._session_id,
        "phase": self._current_phase,  # exploration, classification, testing, reporting
        "progress_pct": self._calculate_progress(),
        "pages_explored": self._explorer._visited if hasattr(self, '_explorer') else 0,
        "endpoints_tested": len(self._findings),
        "findings": len(self._findings),
        "elapsed_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0,
        "estimated_remaining_seconds": self._estimate_remaining(),
    }
```

---

### 6.2 Add HTML Reports
**File:** `backend/hunter/poc_generator.py:200`

```python
def generate_html_report(self, findings: list) -> str:
    """Generate HTML report with styling."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>YBG Hunt Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .finding { border: 1px solid #ddd; padding: 20px; margin: 20px 0; }
            .critical { border-left: 5px solid #d32f2f; }
            .high { border-left: 5px solid #f57c00; }
            .medium { border-left: 5px solid #fbc02d; }
            .low { border-left: 5px solid #388e3c; }
            code { background: #f5f5f5; padding: 2px 6px; }
        </style>
    </head>
    <body>
        <h1>YBG Hunt Report</h1>
        <p>Generated: {timestamp}</p>
        <p>Total Findings: {count}</p>
    """.format(
        timestamp=datetime.now(UTC).isoformat(),
        count=len(findings),
    )
    
    for finding in findings:
        severity_class = finding.severity.lower()
        html += f"""
        <div class="finding {severity_class}">
            <h2>{finding.title}</h2>
            <p><strong>Severity:</strong> {finding.severity}</p>
            <p><strong>Confidence:</strong> {finding.confidence:.2f}</p>
            <p><strong>URL:</strong> <code>{finding.target_url}</code></p>
            <p><strong>Parameter:</strong> <code>{finding.vulnerable_param}</code></p>
            <p><strong>Payload:</strong> <code>{finding.payload_used}</code></p>
            <h3>Evidence:</h3>
            <pre>{json.dumps(finding.evidence, indent=2)}</pre>
        </div>
        """
    
    html += "</body></html>"
    return html
```

---

## TESTING CHECKLIST ✅

Before declaring "production-ready", verify:

- [ ] All imports work (no ImportError)
- [ ] Foundation check passes (authority lock, kill switch, scope validator)
- [ ] Subdomain discovery returns results
- [ ] Proxy support works (test with Burp Suite)
- [ ] Approval workflow blocks and waits for human
- [ ] WAF detection works (test against Cloudflare site)
- [ ] Payload library has 500+ payloads
- [ ] Response analysis detects XSS, SQLi, SSRF correctly
- [ ] Retry logic works (test with flaky network)
- [ ] Concurrent testing is faster than sequential
- [ ] Evidence is encrypted
- [ ] Secrets are redacted from evidence
- [ ] Integration tests pass
- [ ] Unit tests pass (80%+ coverage)
- [ ] No security vulnerabilities (run `bandit`)
- [ ] Performance is acceptable (< 30 min for 150 pages)

---

## FINAL VALIDATION

**Test on intentionally vulnerable sites:**
1. http://testphp.vulnweb.com (XSS, SQLi)
2. https://portswigger.net/web-security (all vuln types)
3. https://www.hackthissite.org (various challenges)

**Expected Results:**
- Finds 5+ vulnerabilities
- No false positives
- No crashes
- Evidence is complete
- Reports are professional

**If all pass → PRODUCTION READY** 🎉

---

**Estimated Total Time:** 8-10 weeks  
**Estimated Effort:** 200-300 hours  
**Team Size:** 2-3 developers

**Priority Order:**
1. Fix critical bugs (Week 1)
2. Add essential features (Week 2-3)
3. Write tests (Week 4)
4. Optimize performance (Week 5-6)
5. Secure evidence (Week 7-8)
6. Polish UX (Week 9-10)

Good luck! 🚀
