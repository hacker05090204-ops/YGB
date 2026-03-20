"""
Verification and enrichment engine for security findings.

Purpose:
  - Convert behavior-only findings into structured verification metadata
  - Attach likely identifiers (CVE / bug family / weakness class)
  - Generate deterministic auto-PoC steps from observed evidence
  - Seed MODE-B proof learning candidates using public PoC references only
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


PUBLIC_POC_SEEDS: Dict[str, List[Dict[str, Any]]] = {
    "CVE-2021-41773": [
        {
            "source": "public-poc",
            "title": "Apache 2.4.49 path traversal baseline",
            "reference": "https://nvd.nist.gov/vuln/detail/CVE-2021-41773",
            "steps": [
                "Send a GET request to a traversal path such as '/cgi-bin/.%2e/%2e%2e/%2e%2e/etc/passwd'.",
                "Observe whether the server returns file contents instead of a 403/404.",
                "Confirm the server banner or target version matches Apache 2.4.49.",
            ],
        }
    ],
    "CVE-2020-11022": [
        {
            "source": "public-poc",
            "title": "Legacy jQuery HTML injection baseline",
            "reference": "https://nvd.nist.gov/vuln/detail/CVE-2020-11022",
            "steps": [
                "Locate a DOM sink that passes attacker-controlled HTML into jQuery.",
                "Inject a payload that relies on legacy htmlPrefilter behavior.",
                "Verify script execution or DOM mutation in the rendered page.",
            ],
        }
    ],
    "SQLI-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic SQL injection confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/SQL_Injection",
            "steps": [
                "Replay the request with a single quote in a likely SQL-backed parameter.",
                "Compare response length, status, and error output against the baseline request.",
                "Retry with a boolean payload and confirm a deterministic application behavior change.",
            ],
        }
    ],
    "XSS-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic reflected or stored XSS confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/xss/",
            "steps": [
                "Place a harmless script marker into the reflected or stored input surface.",
                "Reload the affected page or trigger the rendering flow.",
                "Confirm the marker is rendered unsafely rather than encoded.",
            ],
        }
    ],
    "PATH_TRAVERSAL-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic path traversal confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/Path_Traversal",
            "steps": [
                "Replay the request with '../' or encoded traversal segments in the file parameter.",
                "Target a non-destructive file path that should never be web-accessible.",
                "Confirm whether the response exposes file content, path errors, or traversal normalization bypass.",
            ],
        }
    ],
    "CMDI-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic command injection confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/Command_Injection",
            "steps": [
                "Capture the request that includes the command-like parameter.",
                "Replay it with a harmless command separator payload in a controlled environment.",
                "Compare response output, timing, or side effects to confirm command execution behavior.",
            ],
        }
    ],
    "IDOR-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic IDOR confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html",
            "steps": [
                "Replay the request while swapping the object identifier with a neighboring or guessed value.",
                "Observe whether another user's or tenant's resource becomes accessible.",
                "Verify that the access change happens without an authorization check challenge.",
            ],
        }
    ],
    "CSRF-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic CSRF confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/csrf",
            "steps": [
                "Identify a state-changing action that uses ambient authentication.",
                "Trigger the action from a cross-site context without a trusted anti-CSRF token.",
                "Confirm the server accepts the forged request and changes state.",
            ],
        }
    ],
    "SSRF-HEURISTIC": [
        {
            "source": "public-poc",
            "title": "Generic SSRF confirmation flow",
            "reference": "https://owasp.org/www-community/attacks/Server_Side_Request_Forgery",
            "steps": [
                "Locate the URL-fetching parameter or webhook target.",
                "Replay the request with an internal or canary endpoint under your control.",
                "Confirm outbound reachability through response data, timing, or canary logs.",
            ],
        }
    ],
}


HYBRID_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "SQLI_ERROR_DISCLOSURE",
        "category": "SQLI",
        "match_any": ["sql syntax", "mysql", "postgres", "sqlite", "sql injection", "database error"],
        "identifiers": ["CWE-89", "SQLI-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Capture the baseline request for the affected parameter.",
            "Replay the request with a quote-based payload to test parser breakage.",
            "Replay with a boolean condition and compare response deltas.",
        ],
    },
    {
        "rule_id": "XSS_SOURCE_OR_SINK",
        "category": "XSS",
        "match_any": ["<script", "onerror=", "alert(", "reflected", "html injection"],
        "identifiers": ["CWE-79", "XSS-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Capture the input field or parameter that reflects attacker input.",
            "Inject a harmless script marker such as '<svg onload=alert(1)>' in a safe environment.",
            "Verify whether the marker is encoded or executed on render.",
        ],
    },
    {
        "rule_id": "CSRF_STATE_CHANGE",
        "category": "CSRF",
        "match_any": ["csrf", "xsrf", "request forgery", "anti-csrf", "state-changing"],
        "identifiers": ["CWE-352", "CSRF-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Identify the state-changing endpoint and capture the authenticated baseline request.",
            "Replay the request cross-site without a trusted anti-CSRF token.",
            "Confirm whether the protected action still succeeds.",
        ],
    },
    {
        "rule_id": "IDOR_OBJECT_ACCESS",
        "category": "IDOR",
        "match_any": ["idor", "object reference", "resource id", "sequential", "access another user"],
        "identifiers": ["CWE-639", "IDOR-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Capture the baseline request for the accessible object identifier.",
            "Swap the identifier with a neighboring or guessed value from a different account or tenant.",
            "Verify whether unauthorized object data is returned.",
        ],
    },
    {
        "rule_id": "SSRF_URL_FETCH",
        "category": "SSRF",
        "match_any": ["ssrf", "server-side request forgery", "metadata", "internal network", "webhook"],
        "identifiers": ["CWE-918", "SSRF-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Capture the request that instructs the server to fetch a remote URL.",
            "Replay it with a controlled canary or internal-looking endpoint.",
            "Confirm outbound server-side reachability from the observed response or canary logs.",
        ],
    },
    {
        "rule_id": "PATH_TRAVERSAL_PARAMETER",
        "category": "PATH_TRAVERSAL",
        "match_any": ["path traversal", "../", "..%2f", "file path parameter", "directory traversal"],
        "identifiers": ["CWE-22", "PATH_TRAVERSAL-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Capture the request that accepts the file or path parameter.",
            "Replay it with '../' and encoded traversal payload variants against a safe target file.",
            "Confirm whether the server returns unintended file content or path errors.",
        ],
    },
    {
        "rule_id": "COMMAND_INJECTION_PARAMETER",
        "category": "CMD_INJECTION",
        "match_any": ["command injection", "shell", "cmd", "bash", "os command"],
        "identifiers": ["CWE-78", "CMDI-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Capture the request containing the command-like parameter.",
            "Replay it with a harmless command separator payload in a controlled environment.",
            "Compare the response for timing shifts, echoed output, or execution side effects.",
        ],
    },
    {
        "category": "CVE",
        "rule_id": "CVE_TITLE_CAPTURE",
        "match_any": ["CVE-"],
        "identifier_from_title": True,
        "verification": "VERIFIED",
    },
    {
        "rule_id": "APACHE_249_BANNER",
        "category": "HEADERS",
        "match_any": ["Apache/2.4.49", "Apache/2.4.50"],
        "identifiers": ["CVE-2021-41773", "CWE-22", "PATH_TRAVERSAL-HEURISTIC"],
        "verification": "LIKELY",
        "auto_poc": [
            "Confirm the server header is stable across repeated requests.",
            "Attempt the published traversal path against a non-destructive file target.",
            "Record the returned status code and body snippet.",
        ],
    },
]


CATEGORY_SEED_KEYS: Dict[str, List[str]] = {
    "SQLI": ["SQLI-HEURISTIC"],
    "XSS": ["XSS-HEURISTIC"],
    "PATH_TRAVERSAL": ["PATH_TRAVERSAL-HEURISTIC"],
    "CMD_INJECTION": ["CMDI-HEURISTIC"],
    "IDOR": ["IDOR-HEURISTIC"],
    "CSRF": ["CSRF-HEURISTIC"],
    "SSRF": ["SSRF-HEURISTIC"],
}


@dataclass
class VerificationResult:
    finding_id: str
    verification_status: str
    evidence_strength: str
    verification_score: int
    identified_as: List[str]
    matched_rules: List[str]
    supporting_signals: List[str]
    auto_poc_steps: List[str]
    public_poc_refs: List[Dict[str, Any]]
    mode_b_seed_candidates: List[Dict[str, Any]]
    rationale: str


class VerificationEngine:
    """Deterministic verification and PoC enrichment for scanner findings."""

    def enrich_finding(self, finding: Any, context: Optional[Any] = None) -> Dict[str, Any]:
        evidence = dict(getattr(finding, "evidence", {}) or {})
        title = getattr(finding, "title", "") or ""
        description = getattr(finding, "description", "") or ""
        category = (getattr(finding, "category", "") or "").upper()
        blob = " ".join([
            category,
            title,
            description,
            " ".join(str(v) for v in evidence.values()),
        ])

        identified_as: List[str] = []
        matched_rules: List[str] = []
        supporting_signals: List[str] = []
        auto_poc_steps: List[str] = self._dedupe_strings(
            list(evidence.get("poc_steps", []) or []) +
            list(evidence.get("auto_poc_steps", []) or [])
        )
        public_poc_refs: List[Dict[str, Any]] = []
        mode_b_seed_candidates: List[Dict[str, Any]] = []
        verification_status = "UNVERIFIED"
        score = 20

        if evidence.get("references"):
            score += 15
            supporting_signals.append("references_present")
        if evidence.get("request_response_pairs"):
            score += 20
            supporting_signals.append("request_response_pairs_present")
        if evidence.get("error_messages"):
            score += 15
            supporting_signals.append("error_messages_present")
        if evidence.get("detected_cve"):
            identified_as.append(evidence["detected_cve"])
            score += 35
            verification_status = "VERIFIED"
            supporting_signals.append("explicit_cve_detection")

        for rule in HYBRID_RULES:
            if rule["category"] != category:
                continue
            if any(token.lower() in blob.lower() for token in rule.get("match_any", [])):
                matched_rules.append(rule.get("rule_id", rule["category"]))
                if rule.get("identifier_from_title"):
                    detected = self._extract_cve_tokens(title) + self._extract_cve_tokens(description)
                    identified_as.extend(detected)
                for identifier in rule.get("identifiers", []):
                    identified_as.append(identifier)
                if rule.get("identifier"):
                    identified_as.append(rule["identifier"])
                verification_status = self._max_status(
                    verification_status,
                    rule.get("verification", "UNVERIFIED"),
                )
                auto_poc_steps.extend(rule.get("auto_poc", []))
                score += 20

        if category in {"SQLI", "XSS", "PATH_TRAVERSAL", "CMD_INJECTION"}:
            score += 10
            supporting_signals.append("interactive_vuln_family")
        if getattr(finding, "severity", "").upper() in {"CRITICAL", "HIGH"}:
            score += 10
            supporting_signals.append("high_severity_signal")
        if getattr(finding, "url", ""):
            score += 5
            supporting_signals.append("target_url_present")

        deduped_ids: List[str] = []
        for identifier in identified_as:
            if identifier and identifier not in deduped_ids:
                deduped_ids.append(identifier)
        identified_as = deduped_ids

        if identified_as and verification_status == "UNVERIFIED":
            verification_status = "LIKELY"

        seed_keys = self._dedupe_strings(list(identified_as) + CATEGORY_SEED_KEYS.get(category, []))

        for key in seed_keys:
            for seed in PUBLIC_POC_SEEDS.get(key, []):
                public_poc_refs.append(seed)
                mode_b_seed_candidates.append(
                    {
                        "identifier": key,
                        "title": seed["title"],
                        "reference": seed["reference"],
                        "steps": list(seed["steps"]),
                    }
                )
                if not auto_poc_steps:
                    auto_poc_steps.extend(seed["steps"])

        auto_poc_steps = self._dedupe_strings(auto_poc_steps)
        public_poc_refs = self._dedupe_dicts(public_poc_refs, "reference")
        mode_b_seed_candidates = self._dedupe_dicts(mode_b_seed_candidates, "reference")

        if verification_status == "VERIFIED":
            score = max(score, 90)
        elif verification_status == "LIKELY":
            score = max(score, 65)
        else:
            score = min(score, 55)

        evidence_strength = (
            "STRONG" if score >= 85 else
            "MODERATE" if score >= 65 else
            "WEAK"
        )

        rationale_parts = []
        if identified_as:
            rationale_parts.append(f"identified as {', '.join(identified_as)}")
        if matched_rules:
            rationale_parts.append(f"hybrid rules matched: {', '.join(matched_rules)}")
        if public_poc_refs:
            rationale_parts.append("public PoC seeds attached for MODE-B proof learning")
        if not rationale_parts:
            rationale_parts.append("behavioral signal only; no confirmed identifier")

        result = VerificationResult(
            finding_id=getattr(finding, "finding_id", ""),
            verification_status=verification_status,
            evidence_strength=evidence_strength,
            verification_score=score,
            identified_as=identified_as,
            matched_rules=matched_rules,
            supporting_signals=supporting_signals,
            auto_poc_steps=auto_poc_steps,
            public_poc_refs=public_poc_refs,
            mode_b_seed_candidates=mode_b_seed_candidates,
            rationale="; ".join(rationale_parts),
        )

        enriched = dict(evidence)
        enriched["verification"] = asdict(result)
        enriched["identified_as"] = identified_as
        enriched["auto_poc_steps"] = auto_poc_steps
        enriched["public_poc_refs"] = public_poc_refs
        enriched["mode_b_seed_candidates"] = mode_b_seed_candidates
        return enriched

    def enrich_findings(self, findings: List[Any], context: Optional[Any] = None) -> Dict[str, Any]:
        verified = 0
        likely = 0
        seeded = 0

        for finding in findings:
            finding.evidence = self.enrich_finding(finding, context)
            verification = finding.evidence.get("verification", {})
            status = verification.get("verification_status")
            if status == "VERIFIED":
                verified += 1
            elif status == "LIKELY":
                likely += 1
            if verification.get("mode_b_seed_candidates"):
                seeded += 1

        return {
            "verified_findings": verified,
            "likely_findings": likely,
            "mode_b_seeded_findings": seeded,
            "total_findings": len(findings),
        }

    @staticmethod
    def _extract_cve_tokens(text: str) -> List[str]:
        import re
        return [match.upper() for match in re.findall(r"CVE-\d{4}-\d{4,7}", text or "", re.I)]

    @staticmethod
    def _dedupe_strings(values: List[str]) -> List[str]:
        out: List[str] = []
        for value in values:
            if value and value not in out:
                out.append(value)
        return out

    @staticmethod
    def _dedupe_dicts(values: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for value in values:
            dedupe_key = value.get(key) or str(value)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            out.append(value)
        return out

    @staticmethod
    def _max_status(left: str, right: str) -> str:
        order = {"UNVERIFIED": 0, "LIKELY": 1, "VERIFIED": 2}
        return left if order.get(left, 0) >= order.get(right, 0) else right
