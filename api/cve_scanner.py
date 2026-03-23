"""Governance-safe intelligence adapter for historical vulnerability patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    from api.intelligence_layer import IntelligenceLayer
except ImportError:
    from intelligence_layer import IntelligenceLayer


@dataclass(frozen=True)
class CVEMatch:
    """Represents an intelligence pattern match shaped like the legacy CVE API."""

    cve_id: str
    title: str
    description: str
    severity: str
    cvss_score: float
    affected_component: str
    detection_method: str
    confidence: str
    remediation: str
    references: List[str] = field(default_factory=list)


class CVEScanner:
    """Compatibility wrapper that surfaces intelligence-layer results."""

    def __init__(self, on_finding: Optional[Callable] = None):
        self.on_finding = on_finding
        self.layer = IntelligenceLayer()
        self.findings: List[CVEMatch] = []

    async def _emit_finding(self, match: CVEMatch) -> None:
        self.findings.append(match)
        if self.on_finding:
            self.on_finding(
                {
                    "type": "intelligence",
                    "cve_id": match.cve_id,
                    "title": match.title,
                    "severity": match.severity,
                    "cvss": match.cvss_score,
                    "component": match.affected_component,
                    "description": match.description,
                    "remediation": match.remediation,
                }
            )

    @staticmethod
    def _extract_technology_stack(content: str, headers: Dict[str, str]) -> List[str]:
        haystack = " ".join(
            [content, " ".join(f"{key}:{value}" for key, value in headers.items())]
        ).lower()
        candidates = {
            "django": ("django", "csrftoken"),
            "react": ("react", "__next_data__"),
            "next.js": ("next.js", "__next_data__", "_next/static"),
            "angular": ("angular", "ng-app", "_ngcontent"),
            "vue": ("vue", "v-html", "__vue__"),
            "jquery": ("jquery", "jquery.min.js"),
            "wordpress": ("wordpress", "wp-content", "wp-includes"),
            "php": ("php", "phpsessid"),
            "laravel": ("laravel", "csrf-token"),
            "flask": ("flask", "werkzeug"),
            "express": ("express", "x-powered-by: express"),
            "apache": ("apache",),
            "nginx": ("nginx",),
        }
        stack: List[str] = []
        for name, markers in candidates.items():
            if any(marker in haystack for marker in markers):
                stack.append(name)
        return stack

    @staticmethod
    def _build_description(content: str, headers: Dict[str, str], url: str) -> str:
        header_text = ", ".join(f"{key}: {value}" for key, value in sorted(headers.items())[:8])
        compact_content = " ".join(str(content).split())[:1200]
        parts = [
            f"Target descriptor: {url}" if url else "",
            f"Observed headers: {header_text}" if header_text else "",
            f"Observed content excerpt: {compact_content}" if compact_content else "",
        ]
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _severity_from_confidence(confidence: float) -> str:
        if confidence >= 0.9:
            return "HIGH"
        if confidence >= 0.7:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _confidence_label(confidence: float) -> str:
        if confidence >= 0.9:
            return "HIGH"
        if confidence >= 0.7:
            return "MEDIUM"
        return "LOW"

    async def _run_intelligence(
        self,
        content: str,
        headers: Dict[str, str],
        url: str,
    ) -> List[CVEMatch]:
        description = self._build_description(content, headers, url)
        technology_stack = self._extract_technology_stack(content, headers)
        result = self.layer.analyze_target_description(
            description=description,
            technology_stack=technology_stack,
            scope=url,
        )

        severity = self._severity_from_confidence(result.confidence)
        confidence = self._confidence_label(result.confidence)
        component = ", ".join(technology_stack) or "target description"
        references = result.suggested_focus_areas[:]
        descriptions = result.pattern_matches[:]
        if not descriptions and references:
            descriptions = [
                "Model suggests human review of: " + ", ".join(references[:3])
            ]

        matches: List[CVEMatch] = []
        for index, description_text in enumerate(descriptions, start=1):
            match = CVEMatch(
                cve_id=f"INTEL-{index:03d}",
                title="Historical vulnerability pattern",
                description=description_text,
                severity=severity,
                cvss_score=round(result.confidence * 10.0, 1),
                affected_component=component,
                detection_method="Historical Pattern Intelligence",
                confidence=confidence,
                remediation="Human verification required before any action.",
                references=references,
            )
            matches.append(match)
            await self._emit_finding(match)
        return matches

    async def scan_content(self, content: str, url: str = "") -> List[CVEMatch]:
        self.findings = []
        return await self._run_intelligence(content, {}, url)

    async def scan_headers(self, headers: Dict[str, str], url: str = "") -> List[CVEMatch]:
        self.findings = []
        return await self._run_intelligence("", headers, url)

    async def scan_scripts(self, content: str, url: str = "") -> List[CVEMatch]:
        self.findings = []
        return await self._run_intelligence(content, {}, url)

    async def full_scan(
        self,
        content: str,
        headers: Dict[str, str],
        url: str = "",
    ) -> Dict[str, Any]:
        self.findings = []
        await self._run_intelligence(content, headers, url)
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for finding in self.findings:
            if finding.severity in severity_counts:
                severity_counts[finding.severity] += 1
        return {
            "total_cves": len(self.findings),
            "severity": severity_counts,
            "findings": [
                {
                    "cve_id": finding.cve_id,
                    "title": finding.title,
                    "severity": finding.severity,
                    "cvss": finding.cvss_score,
                    "component": finding.affected_component,
                    "description": finding.description,
                    "remediation": finding.remediation,
                    "confidence": finding.confidence,
                    "references": finding.references,
                }
                for finding in self.findings
            ],
        }


async def scan_for_cves(
    content: str,
    headers: Dict[str, str],
    url: str = "",
    on_finding: Optional[Callable] = None,
) -> Dict[str, Any]:
    scanner = CVEScanner(on_finding=on_finding)
    return await scanner.full_scan(content, headers, url)
