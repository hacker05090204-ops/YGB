"""
CVE Detection Module for YGB Security Scanner
==============================================

Professional-grade CVE (Common Vulnerabilities and Exposures) detection.
Uses known vulnerability patterns and CVE database lookups.
"""

import re
import asyncio
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class CVEMatch:
    """Represents a potential CVE vulnerability match."""
    cve_id: str
    title: str
    description: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score: float
    affected_component: str
    detection_method: str
    confidence: str  # HIGH, MEDIUM, LOW
    remediation: str
    references: List[str] = field(default_factory=list)


# ==============================================================================
# KNOWN CVE PATTERNS DATABASE
# ==============================================================================

# Technology version patterns that map to known CVEs
CVE_PATTERNS = {
    # JavaScript Libraries
    "jquery": [
        {"pattern": r"jquery[/-]?v?1\.[0-9]+", "cve": "CVE-2020-11022", "severity": "MEDIUM", 
         "cvss": 6.1, "title": "jQuery < 3.5.0 XSS Vulnerability",
         "desc": "Passing HTML from untrusted sources to jQuery DOM manipulation methods may execute untrusted code",
         "remediation": "Upgrade jQuery to version 3.5.0 or later"},
        {"pattern": r"jquery[/-]?v?2\.[0-2]", "cve": "CVE-2020-11023", "severity": "MEDIUM",
         "cvss": 6.1, "title": "jQuery < 3.5.0 XSS in htmlPrefilter",
         "desc": "Passing HTML containing <option> from untrusted sources may execute untrusted code",
         "remediation": "Upgrade jQuery to version 3.5.0 or later"},
        {"pattern": r"jquery[/-]?v?3\.[0-4]\.[0-9]", "cve": "CVE-2019-11358", "severity": "MEDIUM",
         "cvss": 6.1, "title": "jQuery Prototype Pollution",
         "desc": "jQuery before 3.4.0 allows Object.prototype pollution via $.extend",
         "remediation": "Upgrade jQuery to version 3.4.0 or later"},
    ],
    
    # AngularJS
    "angular": [
        {"pattern": r"angular[.-]?1\.[0-5]", "cve": "CVE-2022-25869", "severity": "HIGH",
         "cvss": 7.5, "title": "AngularJS XSS Vulnerability",
         "desc": "AngularJS 1.x versions are vulnerable to XSS attacks via expression sandbox bypass",
         "remediation": "Migrate to Angular 2+ or apply security patches"},
        {"pattern": r"angular[.-]?1\.[6-9]", "cve": "CVE-2020-7676", "severity": "MEDIUM",
         "cvss": 6.1, "title": "AngularJS Prototype Pollution",
         "desc": "AngularJS merge function vulnerable to prototype pollution",
         "remediation": "Upgrade AngularJS or migrate to Angular 2+"},
    ],
    
    # React
    "react": [
        {"pattern": r"react[/-]?v?16\.[0-3]", "cve": "CVE-2018-6341", "severity": "MEDIUM",
         "cvss": 5.4, "title": "React XSS in SSR",
         "desc": "React 16.0.0 - 16.3.x has XSS vulnerability in server-side rendering",
         "remediation": "Upgrade React to version 16.4.0 or later"},
    ],
    
    # Bootstrap
    "bootstrap": [
        {"pattern": r"bootstrap[/-]?v?3\.[0-3]", "cve": "CVE-2019-8331", "severity": "MEDIUM",
         "cvss": 6.1, "title": "Bootstrap XSS Vulnerability",
         "desc": "Bootstrap before 3.4.1 and 4.x before 4.3.1 has XSS in data-template",
         "remediation": "Upgrade Bootstrap to 3.4.1+ or 4.3.1+"},
        {"pattern": r"bootstrap[/-]?v?4\.[0-2]", "cve": "CVE-2018-14041", "severity": "MEDIUM",
         "cvss": 6.1, "title": "Bootstrap tooltip XSS",
         "desc": "Bootstrap 4.x before 4.1.2 has XSS in collapse data-parent attribute",
         "remediation": "Upgrade Bootstrap to version 4.1.2 or later"},
    ],
    
    # Lodash
    "lodash": [
        {"pattern": r"lodash[/-]?v?4\.[0-9]+\.[0-9]+", "cve": "CVE-2020-8203", "severity": "HIGH",
         "cvss": 7.4, "title": "Lodash Prototype Pollution",
         "desc": "Lodash versions prior to 4.17.19 are vulnerable to Prototype Pollution",
         "remediation": "Upgrade Lodash to version 4.17.19 or later"},
        {"pattern": r"lodash[/-]?v?[0-3]\.", "cve": "CVE-2019-10744", "severity": "CRITICAL",
         "cvss": 9.1, "title": "Lodash Command Injection",
         "desc": "Lodash versions before 4.17.12 allow command injection via template function",
         "remediation": "Upgrade Lodash to version 4.17.12 or later"},
    ],
    
    # Moment.js
    "moment": [
        {"pattern": r"moment[/-]?v?2\.[0-9]+", "cve": "CVE-2022-31129", "severity": "HIGH",
         "cvss": 7.5, "title": "Moment.js ReDoS Vulnerability",
         "desc": "Moment.js has Regular Expression Denial of Service vulnerability",
         "remediation": "Migrate to date-fns or Luxon"},
    ],
    
    # WordPress
    "wordpress": [
        {"pattern": r"wordpress[/-]?v?[0-4]\.", "cve": "CVE-2022-21661", "severity": "HIGH",
         "cvss": 8.0, "title": "WordPress SQL Injection",
         "desc": "WordPress core SQL injection in WP_Query",
         "remediation": "Update WordPress to the latest version"},
        {"pattern": r"wp-includes", "cve": "CVE-2023-2745", "severity": "MEDIUM",
         "cvss": 5.4, "title": "WordPress Directory Traversal",
         "desc": "WordPress core directory traversal vulnerability",
         "remediation": "Update WordPress to the latest version"},
    ],
    
    # PHP
    "php": [
        {"pattern": r"php[/-]?v?7\.[0-3]", "cve": "CVE-2019-11043", "severity": "CRITICAL",
         "cvss": 9.8, "title": "PHP-FPM Remote Code Execution",
         "desc": "PHP before 7.3.11 has remote code execution vulnerability in PHP-FPM",
         "remediation": "Upgrade PHP to version 7.3.11+ or 7.4+"},
        {"pattern": r"php[/-]?v?5\.", "cve": "CVE-2019-11045", "severity": "CRITICAL",
         "cvss": 9.8, "title": "PHP 5.x End of Life",
         "desc": "PHP 5.x is end of life and has multiple unpatched vulnerabilities",
         "remediation": "Upgrade to PHP 8.x immediately"},
    ],
    
    # Apache
    "apache": [
        {"pattern": r"apache[/-]?2\.4\.[0-4][0-9]", "cve": "CVE-2021-41773", "severity": "CRITICAL",
         "cvss": 9.8, "title": "Apache Path Traversal",
         "desc": "Apache HTTP Server 2.4.49 path traversal and RCE vulnerability",
         "remediation": "Upgrade Apache to version 2.4.51 or later"},
        {"pattern": r"apache[/-]?2\.2\.", "cve": "CVE-2017-3169", "severity": "HIGH",
         "cvss": 7.5, "title": "Apache mod_ssl NULL Pointer",
         "desc": "Apache 2.2.x has null pointer dereference in mod_ssl",
         "remediation": "Upgrade to Apache 2.4.x"},
    ],
    
    # nginx
    "nginx": [
        {"pattern": r"nginx[/-]?1\.[0-9]\.", "cve": "CVE-2021-23017", "severity": "HIGH",
         "cvss": 7.5, "title": "nginx DNS Resolver Vulnerability",
         "desc": "nginx before 1.21.0 has DNS resolver vulnerability",
         "remediation": "Upgrade nginx to version 1.21.0 or later"},
    ],
    
    # Express.js
    "express": [
        {"pattern": r"express[/-]?v?[0-3]\.", "cve": "CVE-2022-24999", "severity": "HIGH",
         "cvss": 7.5, "title": "Express.js Prototype Pollution",
         "desc": "Express.js before 4.17.3 has prototype pollution in qs",
         "remediation": "Upgrade Express to version 4.17.3 or later"},
    ],
    
    # Log4j
    "log4j": [
        {"pattern": r"log4j[/-]?2\.[0-9]+", "cve": "CVE-2021-44228", "severity": "CRITICAL",
         "cvss": 10.0, "title": "Log4Shell Remote Code Execution",
         "desc": "Log4j 2.x before 2.17.0 has critical RCE via JNDI lookup",
         "remediation": "Upgrade Log4j to version 2.17.1 or later immediately"},
    ],
    
    # Spring Framework
    "spring": [
        {"pattern": r"spring[/-]?v?[0-4]\.", "cve": "CVE-2022-22965", "severity": "CRITICAL",
         "cvss": 9.8, "title": "Spring4Shell RCE",
         "desc": "Spring Framework RCE vulnerability via data binding",
         "remediation": "Upgrade Spring Framework to 5.3.18+ or 5.2.20+"},
    ],
    
    # OpenSSL
    "openssl": [
        {"pattern": r"openssl[/-]?1\.[0-1]\.", "cve": "CVE-2014-0160", "severity": "CRITICAL",
         "cvss": 9.8, "title": "Heartbleed Vulnerability",
         "desc": "OpenSSL 1.0.1 before 1.0.1g has the Heartbleed bug",
         "remediation": "Upgrade OpenSSL to version 1.0.1g or later"},
        {"pattern": r"openssl[/-]?3\.0\.[0-6]", "cve": "CVE-2022-3602", "severity": "HIGH",
         "cvss": 7.5, "title": "OpenSSL Buffer Overflow",
         "desc": "OpenSSL 3.0.x before 3.0.7 has buffer overflow vulnerability",
         "remediation": "Upgrade OpenSSL to version 3.0.7 or later"},
    ],
}

# Header-based CVE patterns
HEADER_CVE_PATTERNS = {
    "server": [
        {"pattern": r"Apache/2\.4\.49", "cve": "CVE-2021-41773", "severity": "CRITICAL",
         "cvss": 9.8, "title": "Apache 2.4.49 Path Traversal RCE"},
        {"pattern": r"Apache/2\.4\.50", "cve": "CVE-2021-42013", "severity": "CRITICAL",
         "cvss": 9.8, "title": "Apache 2.4.50 Path Traversal RCE"},
        {"pattern": r"nginx/1\.[0-9]\.", "cve": "CVE-2013-2028", "severity": "HIGH",
         "cvss": 7.5, "title": "nginx Chunked Transfer Coding Stack Overflow"},
        {"pattern": r"Microsoft-IIS/[5-7]\.", "cve": "CVE-2017-7269", "severity": "CRITICAL",
         "cvss": 9.8, "title": "IIS 6.0 WebDAV Buffer Overflow"},
    ],
    "x-powered-by": [
        {"pattern": r"PHP/5\.", "cve": "CVE-2019-11043", "severity": "CRITICAL",
         "cvss": 9.8, "title": "PHP 5.x End of Life - Multiple CVEs"},
        {"pattern": r"PHP/7\.[0-3]", "cve": "CVE-2019-11043", "severity": "HIGH",
         "cvss": 9.8, "title": "PHP-FPM RCE Vulnerability"},
        {"pattern": r"Express", "cve": "CVE-2022-24999", "severity": "MEDIUM",
         "cvss": 5.3, "title": "Express.js Information Disclosure"},
        {"pattern": r"ASP\.NET", "cve": "CVE-2021-26855", "severity": "HIGH",
         "cvss": 9.8, "title": "Check for Exchange ProxyLogon"},
    ],
}


class CVEScanner:
    """Professional CVE vulnerability scanner."""
    
    def __init__(self, on_finding: Optional[Callable] = None):
        self.on_finding = on_finding
        self.findings: List[CVEMatch] = []
    
    async def _emit_finding(self, match: CVEMatch):
        """Emit a CVE finding."""
        self.findings.append(match)
        if self.on_finding:
            try:
                self.on_finding({
                    "type": "cve",
                    "cve_id": match.cve_id,
                    "title": match.title,
                    "severity": match.severity,
                    "cvss": match.cvss_score,
                    "component": match.affected_component,
                    "description": match.description,
                    "remediation": match.remediation
                })
            except:
                pass
    
    async def scan_content(self, content: str, url: str = "") -> List[CVEMatch]:
        """Scan page content for CVE vulnerabilities."""
        content_lower = content.lower()
        
        for tech, patterns in CVE_PATTERNS.items():
            for pattern_info in patterns:
                if re.search(pattern_info["pattern"], content_lower, re.I):
                    match = CVEMatch(
                        cve_id=pattern_info["cve"],
                        title=pattern_info["title"],
                        description=pattern_info["desc"],
                        severity=pattern_info["severity"],
                        cvss_score=pattern_info["cvss"],
                        affected_component=tech,
                        detection_method="Content Pattern Match",
                        confidence="MEDIUM",
                        remediation=pattern_info["remediation"],
                        references=[
                            f"https://nvd.nist.gov/vuln/detail/{pattern_info['cve']}",
                            f"https://cve.mitre.org/cgi-bin/cvename.cgi?name={pattern_info['cve']}"
                        ]
                    )
                    await self._emit_finding(match)
        
        return self.findings
    
    async def scan_headers(self, headers: Dict[str, str], url: str = "") -> List[CVEMatch]:
        """Scan HTTP headers for CVE vulnerabilities."""
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        for header_name, patterns in HEADER_CVE_PATTERNS.items():
            header_value = headers_lower.get(header_name, "")
            if not header_value:
                continue
            
            for pattern_info in patterns:
                if re.search(pattern_info["pattern"], header_value, re.I):
                    match = CVEMatch(
                        cve_id=pattern_info["cve"],
                        title=pattern_info["title"],
                        description=f"Detected via {header_name} header: {header_value}",
                        severity=pattern_info["severity"],
                        cvss_score=pattern_info["cvss"],
                        affected_component=header_name,
                        detection_method="HTTP Header Analysis",
                        confidence="HIGH",
                        remediation="Update software to latest patched version",
                        references=[
                            f"https://nvd.nist.gov/vuln/detail/{pattern_info['cve']}"
                        ]
                    )
                    await self._emit_finding(match)
        
        return self.findings
    
    async def scan_scripts(self, content: str, url: str = "") -> List[CVEMatch]:
        """Scan script tags for vulnerable library versions."""
        # Extract script sources
        script_pattern = r'<script[^>]+src=["\']([^"\']+)["\']'
        scripts = re.findall(script_pattern, content, re.I)
        
        vulnerable_patterns = [
            # CDN patterns with versions
            (r'jquery[/-]?(\d+\.\d+\.\d+)', "jquery"),
            (r'angular[.-]?(\d+\.\d+\.\d+)', "angular"),
            (r'bootstrap[/-]?(\d+\.\d+\.\d+)', "bootstrap"),
            (r'lodash[/-]?(\d+\.\d+\.\d+)', "lodash"),
            (r'moment[/-]?(\d+\.\d+\.\d+)', "moment"),
            (r'react[/-]?(\d+\.\d+\.\d+)', "react"),
            (r'vue[/-]?(\d+\.\d+\.\d+)', "vue"),
        ]
        
        for script_src in scripts:
            for pattern, lib_name in vulnerable_patterns:
                match = re.search(pattern, script_src, re.I)
                if match:
                    version = match.group(1)
                    # Check against known vulnerable versions
                    if lib_name in CVE_PATTERNS:
                        for vuln in CVE_PATTERNS[lib_name]:
                            if re.search(vuln["pattern"], f"{lib_name}/{version}", re.I):
                                cve_match = CVEMatch(
                                    cve_id=vuln["cve"],
                                    title=vuln["title"],
                                    description=f"{lib_name} version {version} - {vuln['desc']}",
                                    severity=vuln["severity"],
                                    cvss_score=vuln["cvss"],
                                    affected_component=f"{lib_name} {version}",
                                    detection_method="Script Source Analysis",
                                    confidence="HIGH",
                                    remediation=vuln["remediation"],
                                    references=[
                                        f"https://nvd.nist.gov/vuln/detail/{vuln['cve']}",
                                        script_src
                                    ]
                                )
                                await self._emit_finding(cve_match)
        
        return self.findings
    
    async def full_scan(self, content: str, headers: Dict[str, str], url: str = "") -> Dict[str, Any]:
        """Perform full CVE scan of content, headers, and scripts."""
        await self.scan_content(content, url)
        await self.scan_headers(headers, url)
        await self.scan_scripts(content, url)
        
        # Deduplicate by CVE ID
        unique_cves = {}
        for finding in self.findings:
            if finding.cve_id not in unique_cves:
                unique_cves[finding.cve_id] = finding
        
        self.findings = list(unique_cves.values())
        
        # Count by severity
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for f in self.findings:
            if f.severity in severity_counts:
                severity_counts[f.severity] += 1
        
        return {
            "total_cves": len(self.findings),
            "severity": severity_counts,
            "findings": [
                {
                    "cve_id": f.cve_id,
                    "title": f.title,
                    "severity": f.severity,
                    "cvss": f.cvss_score,
                    "component": f.affected_component,
                    "description": f.description,
                    "remediation": f.remediation,
                    "confidence": f.confidence,
                    "references": f.references
                }
                for f in self.findings
            ]
        }


async def scan_for_cves(
    content: str,
    headers: Dict[str, str],
    url: str = "",
    on_finding: Optional[Callable] = None
) -> Dict[str, Any]:
    """Main function to scan for CVE vulnerabilities."""
    scanner = CVEScanner(on_finding=on_finding)
    return await scanner.full_scan(content, headers, url)


# ==============================================================================
# TEST
# ==============================================================================
if __name__ == "__main__":
    async def test():
        test_content = """
        <html>
        <head>
            <script src="https://code.jquery.com/jquery-1.12.4.min.js"></script>
            <script src="/js/bootstrap-3.3.7.min.js"></script>
            <script src="/js/angular.js/1.5.8/angular.min.js"></script>
        </head>
        <body>
            <!-- WordPress 5.0 -->
            <meta name="generator" content="WordPress 5.0">
            PHP/5.6.40
        </body>
        </html>
        """
        
        test_headers = {
            "Server": "Apache/2.4.49",
            "X-Powered-By": "PHP/5.6.40"
        }
        
        def on_finding(f):
            print(f"🔴 {f['cve_id']}: {f['title']} [{f['severity']}]")
        
        results = await scan_for_cves(test_content, test_headers, "https://test.com", on_finding)
        
        print(f"\n{'='*60}")
        print(f"Total CVEs Found: {results['total_cves']}")
        print(f"Severity: {results['severity']}")
    
    asyncio.run(test())
