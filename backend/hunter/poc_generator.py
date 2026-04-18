"""Professional PoC (Proof of Concept) Generator.
Generates bug bounty reports with:
- CVSS scoring
- Impact assessment
- Reproduction steps
- cURL commands
- Python verification scripts
- Remediation advice
Exports to Markdown for submission."""

import hashlib
import json
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ygb.hunter.poc")


CVSS_SCORES = {
    "xss": {"base": 6.1, "severity": "MEDIUM"},
    "sqli": {"base": 9.1, "severity": "CRITICAL"},
    "ssrf": {"base": 8.6, "severity": "HIGH"},
    "idor": {"base": 7.5, "severity": "HIGH"},
    "path_traversal": {"base": 7.5, "severity": "HIGH"},
    "rce": {"base": 9.8, "severity": "CRITICAL"},
    "ssti": {"base": 9.0, "severity": "CRITICAL"},
    "auth_bypass": {"base": 9.1, "severity": "CRITICAL"},
    "open_redirect": {"base": 4.3, "severity": "MEDIUM"},
    "crlf": {"base": 5.3, "severity": "MEDIUM"},
    "csrf": {"base": 6.5, "severity": "MEDIUM"},
}


IMPACTS = {
    "xss": "Cross-Site Scripting allows attackers to inject malicious scripts into web pages viewed by other users. This can lead to session hijacking, credential theft, defacement, or malware distribution.",
    "sqli": "SQL Injection allows attackers to interfere with database queries. Attackers can read, modify, or delete sensitive data, bypass authentication, or execute administrative operations on the database.",
    "ssrf": "Server-Side Request Forgery allows attackers to make the server perform requests to arbitrary destinations. This can expose internal services, cloud metadata, or enable port scanning of internal networks.",
    "idor": "Insecure Direct Object Reference allows attackers to access resources belonging to other users by manipulating object identifiers. This can lead to unauthorized data access or privilege escalation.",
    "path_traversal": "Path Traversal allows attackers to access files and directories outside the intended directory. This can expose sensitive configuration files, source code, or system files.",
    "rce": "Remote Code Execution allows attackers to execute arbitrary code on the server. This is the most severe vulnerability, potentially leading to complete system compromise.",
    "ssti": "Server-Side Template Injection allows attackers to inject malicious template directives. This can lead to remote code execution, information disclosure, or denial of service.",
    "auth_bypass": "Authentication Bypass allows attackers to circumvent authentication mechanisms and gain unauthorized access to protected resources or functionality.",
    "open_redirect": "Open Redirect allows attackers to redirect users to malicious websites. This can be used in phishing attacks or to bypass security filters.",
    "crlf": "CRLF Injection allows attackers to inject HTTP headers. This can lead to response splitting, cache poisoning, or cross-site scripting.",
}


REMEDIATION = {
    "xss": "1. Implement proper output encoding/escaping for all user input\n2. Use Content Security Policy (CSP) headers\n3. Validate and sanitize all input on the server side\n4. Use modern frameworks with built-in XSS protection",
    "sqli": "1. Use parameterized queries or prepared statements exclusively\n2. Implement input validation with whitelisting\n3. Apply principle of least privilege to database accounts\n4. Use ORM frameworks with proper escaping",
    "ssrf": "1. Implement strict URL validation and whitelisting\n2. Disable unnecessary URL schemas (file://, gopher://, etc.)\n3. Use network segmentation to isolate internal services\n4. Validate and sanitize all user-supplied URLs",
    "idor": "1. Implement proper access control checks for all resources\n2. Use indirect references (random tokens) instead of direct IDs\n3. Validate user authorization for every request\n4. Implement session-based access controls",
    "path_traversal": "1. Validate and sanitize all file paths\n2. Use whitelisting for allowed files/directories\n3. Implement proper access controls\n4. Avoid using user input in file operations",
    "rce": "1. Never execute user-supplied input as code\n2. Use safe APIs that don't invoke shell commands\n3. Implement strict input validation\n4. Run applications with minimal privileges",
    "ssti": "1. Avoid using user input in template rendering\n2. Use logic-less template engines\n3. Implement strict input validation\n4. Sandbox template execution environment",
    "auth_bypass": "1. Implement robust authentication mechanisms\n2. Use established authentication libraries\n3. Enforce proper session management\n4. Implement multi-factor authentication",
    "open_redirect": "1. Validate all redirect URLs against a whitelist\n2. Use relative URLs for redirects when possible\n3. Implement proper URL validation\n4. Warn users before external redirects",
    "crlf": "1. Validate and sanitize all user input used in HTTP headers\n2. Remove or encode CRLF characters (\\r\\n)\n3. Use framework functions for header manipulation\n4. Implement strict input validation",
}


@dataclass
class Finding:
    finding_id: str
    vuln_type: str
    severity: str
    cvss_score: float
    title: str
    target_url: str
    vulnerable_param: str
    payload_used: str
    evidence: dict
    discovered_at: str
    confidence: float


class PoCGenerator:
    """Generates professional bug bounty reports."""

    def __init__(self, output_dir: Path = None):
        self._output_dir = output_dir or Path("data/ssd/reports")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_finding_id(self, vuln_type: str, target: str) -> str:
        """Generate unique finding ID: YGB-YYYYMMDD-HASH"""
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        hash_input = f"{vuln_type}{target}{datetime.now(UTC).isoformat()}"
        hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:6].upper()
        return f"YGB-{date_str}-{hash_suffix}"

    def create_finding(
        self,
        vuln_type: str,
        target_url: str,
        vulnerable_param: str,
        payload_used: str,
        evidence: dict,
        confidence: float,
    ) -> Finding:
        """Create a finding object from test results."""
        cvss_data = CVSS_SCORES.get(vuln_type, {"base": 5.0, "severity": "MEDIUM"})

        # Adjust CVSS based on confidence
        adjusted_score = cvss_data["base"] * confidence

        title = self._generate_title(vuln_type, vulnerable_param, target_url)

        return Finding(
            finding_id=self.generate_finding_id(vuln_type, target_url),
            vuln_type=vuln_type,
            severity=cvss_data["severity"],
            cvss_score=round(adjusted_score, 1),
            title=title,
            target_url=target_url,
            vulnerable_param=vulnerable_param,
            payload_used=payload_used,
            evidence=evidence,
            discovered_at=datetime.now(UTC).isoformat(),
            confidence=confidence,
        )

    def _generate_title(self, vuln_type: str, param: str, url: str) -> str:
        """Generate descriptive title."""
        vuln_names = {
            "xss": "Cross-Site Scripting (XSS)",
            "sqli": "SQL Injection",
            "ssrf": "Server-Side Request Forgery (SSRF)",
            "idor": "Insecure Direct Object Reference (IDOR)",
            "path_traversal": "Path Traversal",
            "rce": "Remote Code Execution (RCE)",
            "ssti": "Server-Side Template Injection (SSTI)",
            "auth_bypass": "Authentication Bypass",
            "open_redirect": "Open Redirect",
            "crlf": "CRLF Injection",
        }

        vuln_name = vuln_names.get(vuln_type, vuln_type.upper())
        domain = urllib.parse.urlparse(url).netloc
        return f"{vuln_name} in '{param}' parameter on {domain}"

    def generate_curl_command(self, finding: Finding) -> str:
        """Generate cURL command to reproduce the finding."""
        parsed = urllib.parse.urlparse(finding.target_url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        params[finding.vulnerable_param] = finding.payload_used

        new_query = urllib.parse.urlencode(params)
        full_url = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
        )

        curl_cmd = f"""curl -sk '{full_url}' \\
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' \\
  -H 'Accept: text/html,application/json,*/*'"""

        return curl_cmd

    def generate_python_script(self, finding: Finding) -> str:
        """Generate Python verification script."""
        script = f'''#!/usr/bin/env python3
"""
Verification script for {finding.finding_id}
{finding.title}
"""

import requests

def verify_vulnerability():
    """Verify the {finding.vuln_type.upper()} vulnerability."""
    
    target_url = "{finding.target_url}"
    vulnerable_param = "{finding.vulnerable_param}"
    payload = "{finding.payload_used}"
    
    # Build request
    params = {{vulnerable_param: payload}}
    
    try:
        response = requests.get(
            target_url,
            params=params,
            timeout=10,
            verify=True
        )
        
        print(f"Status Code: {{response.status_code}}")
        print(f"Response Length: {{len(response.text)}} bytes")
        
        # Check for vulnerability indicators
        if "{finding.payload_used[:20]}" in response.text:
            print("\\n[+] VULNERABLE: Payload reflected in response")
            return True
        else:
            print("\\n[-] Not vulnerable or payload filtered")
            return False
            
    except Exception as e:
        print(f"Error: {{e}}")
        return False

if __name__ == "__main__":
    verify_vulnerability()
'''
        return script

    def generate_markdown_report(self, finding: Finding) -> str:
        """Generate complete Markdown report."""
        impact = IMPACTS.get(finding.vuln_type, "Security vulnerability detected.")
        remediation = REMEDIATION.get(
            finding.vuln_type, "Implement proper input validation and security controls."
        )

        curl_cmd = self.generate_curl_command(finding)

        report = f"""# {finding.finding_id}: {finding.title}

**Severity:** {finding.severity} (CVSS {finding.cvss_score})  
**Type:** {finding.vuln_type.upper()}  
**Discovered:** {finding.discovered_at}  
**Confidence:** {finding.confidence:.0%}

---

## Summary

A {finding.vuln_type.upper()} vulnerability was discovered in the `{finding.vulnerable_param}` parameter on `{finding.target_url}`.

## Impact

{impact}

## Vulnerability Details

- **Vulnerable URL:** `{finding.target_url}`
- **Vulnerable Parameter:** `{finding.vulnerable_param}`
- **Attack Vector:** Network
- **Attack Complexity:** Low
- **Privileges Required:** None
- **User Interaction:** None (for most cases)

## Steps to Reproduce

1. Navigate to the target URL: `{finding.target_url}`
2. Identify the vulnerable parameter: `{finding.vulnerable_param}`
3. Replace the parameter value with the following payload:
   ```
   {finding.payload_used}
   ```
4. Observe the response for vulnerability indicators

## Proof of Concept

### cURL Command

```bash
{curl_cmd}
```

### Evidence

```json
{json.dumps(finding.evidence, indent=2)}
```

## Remediation

{remediation}

## References

- OWASP Top 10
- CWE Database
- CVSS v3.1 Calculator

---

**Report Generated:** {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Generated By:** YGB Pure AI Hunter Agent  
**Finding ID:** {finding.finding_id}
"""

        return report

    def save_report(self, finding: Finding) -> Path:
        """Save complete report to disk."""
        # Save Markdown report
        md_path = self._output_dir / f"{finding.finding_id}.md"
        md_path.write_text(self.generate_markdown_report(finding))

        # Save Python verification script
        py_path = self._output_dir / f"{finding.finding_id}_verify.py"
        py_path.write_text(self.generate_python_script(finding))

        # Save JSON data
        json_path = self._output_dir / f"{finding.finding_id}.json"
        json_data = {
            "finding_id": finding.finding_id,
            "vuln_type": finding.vuln_type,
            "severity": finding.severity,
            "cvss_score": finding.cvss_score,
            "title": finding.title,
            "target_url": finding.target_url,
            "vulnerable_param": finding.vulnerable_param,
            "payload_used": finding.payload_used,
            "evidence": finding.evidence,
            "discovered_at": finding.discovered_at,
            "confidence": finding.confidence,
        }
        json_path.write_text(json.dumps(json_data, indent=2))

        logger.info("Report saved: %s", md_path)
        return md_path

    def generate_summary_report(self, findings: list[Finding]) -> str:
        """Generate summary report for multiple findings."""
        if not findings:
            return "# Hunt Summary\n\nNo vulnerabilities found."

        by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
        for f in findings:
            by_severity[f.severity].append(f)

        summary = f"""# Bug Bounty Hunt Summary

**Total Findings:** {len(findings)}  
**Generated:** {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}

## Findings by Severity

- **CRITICAL:** {len(by_severity['CRITICAL'])}
- **HIGH:** {len(by_severity['HIGH'])}
- **MEDIUM:** {len(by_severity['MEDIUM'])}
- **LOW:** {len(by_severity['LOW'])}

---

"""

        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if by_severity[severity]:
                summary += f"\n## {severity} Severity\n\n"
                for finding in by_severity[severity]:
                    summary += f"### {finding.finding_id}: {finding.title}\n"
                    summary += f"- **CVSS:** {finding.cvss_score}\n"
                    summary += f"- **URL:** `{finding.target_url}`\n"
                    summary += f"- **Parameter:** `{finding.vulnerable_param}`\n"
                    summary += f"- **Confidence:** {finding.confidence:.0%}\n\n"

        return summary
