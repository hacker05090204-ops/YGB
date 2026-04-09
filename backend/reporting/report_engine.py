"""Deterministic vulnerability report generation from real finding data only."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.ingestion.models import normalize_severity

logger = logging.getLogger("ygb.reporting.report_engine")

REPORT_ENGINE_VERSION = "1.0"
MIN_DESCRIPTION_LENGTH = 50
SEVERITY_PRIORITY = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
    "INFO": 1,
    "UNKNOWN": 0,
}

_ENGINE_SINGLETON: "ReportEngine | None" = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_timestamp(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError:
            logger.warning("invalid_report_timestamp value=%s", value)
    return _utc_now()


def _coerce_text_list(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return tuple()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else tuple()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
        return tuple(items)
    raise ValueError("finding list fields must be strings or sequences of strings")


def _coerce_optional_cvss(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("cvss_score must be numeric")
    try:
        cvss_score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("cvss_score must be numeric") from exc
    if not math.isfinite(cvss_score) or not 0.0 <= cvss_score <= 10.0:
        raise ValueError("cvss_score must be between 0.0 and 10.0")
    return round(cvss_score, 1)


def _coerce_optional_confidence(value: Any, *, is_percent_field: bool) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("model confidence must be numeric")
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("model confidence must be numeric") from exc
    if not math.isfinite(confidence):
        raise ValueError("model confidence must be finite")
    if not is_percent_field and 0.0 <= confidence <= 1.0:
        confidence *= 100.0
    if not 0.0 <= confidence <= 100.0:
        raise ValueError("model confidence must be between 0.0 and 100.0")
    return round(confidence, 2)


@dataclass
class VulnerabilityFinding:
    finding_id: str
    title: str
    description: str
    severity: str
    cvss_score: float | None = None
    model_confidence: float | None = None
    cve_id: str = ""
    cwe_id: str = ""
    affected_asset: str = ""
    source_url: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)
    references: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "cvss_score": self.cvss_score,
            "model_confidence": self.model_confidence,
            "cve_id": self.cve_id,
            "cwe_id": self.cwe_id,
            "affected_asset": self.affected_asset,
            "source_url": self.source_url,
            "evidence": list(self.evidence),
            "references": list(self.references),
        }


@dataclass
class ReportSection:
    key: str
    title: str
    content: str
    order: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "content": self.content,
            "order": self.order,
        }


@dataclass
class VulnerabilityReport:
    report_id: str
    title: str
    description: str
    report_type: str
    generated_at: str
    findings: list[VulnerabilityFinding]
    sections: list[ReportSection]
    executive_summary: str
    summary_counts: dict[str, int]
    average_model_confidence: float | None
    sha256: str
    storage_path: str
    source_context: dict[str, Any] = field(default_factory=dict)
    generator_version: str = REPORT_ENGINE_VERSION

    def to_content_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "generator_version": self.generator_version,
            "executive_summary": self.executive_summary,
            "summary_counts": dict(self.summary_counts),
            "average_model_confidence": self.average_model_confidence,
            "source_context": dict(self.source_context),
            "findings": [finding.to_dict() for finding in self.findings],
            "sections": [section.to_dict() for section in self.sections],
            "sha256": self.sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "description": self.description,
            "report_type": self.report_type,
            "generated_at": self.generated_at,
            "generator_version": self.generator_version,
            "sha256": self.sha256,
            "storage_path": self.storage_path,
            "content": self.to_content_dict(),
        }


class ReportEngine:
    """Builds high-quality vulnerability reports from validated finding data."""

    def __init__(self, output_dir: str | os.PathLike[str] | None = None) -> None:
        configured_dir = os.environ.get("YGB_REPORT_OUTPUT_DIR")
        self.output_dir = Path(output_dir or configured_dir or "reports/generated_reports")

    def build_report(
        self,
        *,
        report_id: str,
        title: str,
        description: str,
        report_type: str,
        findings: Sequence[Mapping[str, Any] | VulnerabilityFinding],
        source_context: Mapping[str, Any] | None = None,
        generated_at: str | None = None,
    ) -> VulnerabilityReport:
        normalized_findings = [self._coerce_finding(finding) for finding in findings]
        if not normalized_findings:
            raise ValueError("build_report() requires at least one finding")

        sorted_findings = sorted(
            normalized_findings,
            key=lambda finding: (
                -SEVERITY_PRIORITY.get(finding.severity, 0),
                -(finding.cvss_score if finding.cvss_score is not None else -1.0),
                finding.finding_id,
            ),
        )
        report_generated_at = _normalize_timestamp(generated_at)
        context = dict(source_context) if isinstance(source_context, Mapping) else {}
        summary_counts = self._summary_counts(sorted_findings)
        average_confidence = self._average_model_confidence(sorted_findings)
        sections = self._build_sections(
            findings=sorted_findings,
            summary_counts=summary_counts,
            average_confidence=average_confidence,
        )
        executive_summary = sections[0].content

        sha256 = self._hash_payload(
            self._build_hash_payload(
                title=title,
                description=description,
                report_type=report_type,
                summary_counts=summary_counts,
                average_confidence=average_confidence,
                source_context=context,
                findings=sorted_findings,
                sections=sections,
            )
        )

        report = VulnerabilityReport(
            report_id=report_id,
            title=title,
            description=description,
            report_type=report_type,
            generated_at=report_generated_at,
            findings=sorted_findings,
            sections=sections,
            executive_summary=executive_summary,
            summary_counts=summary_counts,
            average_model_confidence=average_confidence,
            sha256=sha256,
            storage_path="",
            source_context=context,
        )
        report.storage_path = self._save_report(report)
        return report

    def _build_hash_payload(
        self,
        *,
        title: str,
        description: str,
        report_type: str,
        summary_counts: Mapping[str, int],
        average_confidence: float | None,
        source_context: Mapping[str, Any],
        findings: Sequence[VulnerabilityFinding],
        sections: Sequence[ReportSection],
    ) -> dict[str, Any]:
        return {
            "title": title,
            "description": description,
            "report_type": report_type,
            "generator_version": REPORT_ENGINE_VERSION,
            "summary_counts": dict(summary_counts),
            "average_model_confidence": average_confidence,
            "source_context": dict(source_context),
            "findings": [finding.to_dict() for finding in findings],
            "sections": [section.to_dict() for section in sections],
        }

    def _coerce_finding(
        self, finding: Mapping[str, Any] | VulnerabilityFinding
    ) -> VulnerabilityFinding:
        if isinstance(finding, VulnerabilityFinding):
            candidate = finding
        elif isinstance(finding, Mapping):
            payload = dict(finding)
            finding_id = str(
                payload.get("finding_id")
                or payload.get("id")
                or payload.get("cve_id")
                or ""
            ).strip()
            if not finding_id:
                raise ValueError("finding is missing finding_id/id/cve_id")

            title = str(
                payload.get("title")
                or payload.get("name")
                or payload.get("cve_id")
                or finding_id
            ).strip()
            if not title:
                raise ValueError(f"finding {finding_id} is missing title")

            description = str(
                payload.get("description")
                or payload.get("summary")
                or payload.get("details")
                or ""
            ).strip()
            if len(description) < MIN_DESCRIPTION_LENGTH:
                raise ValueError(f"finding {finding_id} description_too_short")

            severity = normalize_severity(
                str(payload.get("severity") or payload.get("base_severity") or "UNKNOWN")
            )

            cvss_score = _coerce_optional_cvss(
                payload.get("cvss_score", payload.get("cvss"))
            )

            confidence_key = None
            confidence_value = None
            for candidate_key in ("model_confidence", "confidence_pct", "confidence"):
                if candidate_key in payload:
                    confidence_key = candidate_key
                    confidence_value = payload.get(candidate_key)
                    break
            model_confidence = _coerce_optional_confidence(
                confidence_value,
                is_percent_field=bool(confidence_key and confidence_key.endswith("pct")),
            )

            candidate = VulnerabilityFinding(
                finding_id=finding_id,
                title=title,
                description=description,
                severity=severity,
                cvss_score=cvss_score,
                model_confidence=model_confidence,
                cve_id=str(payload.get("cve_id") or "").strip().upper(),
                cwe_id=str(payload.get("cwe_id") or payload.get("cwe") or "").strip().upper(),
                affected_asset=str(
                    payload.get("affected_asset")
                    or payload.get("target")
                    or payload.get("asset")
                    or ""
                ).strip(),
                source_url=str(payload.get("source_url") or payload.get("url") or "").strip(),
                evidence=_coerce_text_list(payload.get("evidence", ())),
                references=_coerce_text_list(payload.get("references", ())),
            )
        else:
            raise ValueError("findings must be mappings or VulnerabilityFinding instances")

        if len(candidate.description.strip()) < MIN_DESCRIPTION_LENGTH:
            raise ValueError(f"finding {candidate.finding_id} description_too_short")
        return candidate

    def _summary_counts(self, findings: Sequence[VulnerabilityFinding]) -> dict[str, int]:
        counts = {severity: 0 for severity in SEVERITY_PRIORITY}
        counts["total_findings"] = len(findings)
        counts["scored_findings"] = 0
        for finding in findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
            if finding.model_confidence is not None:
                counts["scored_findings"] += 1
        return counts

    def _average_model_confidence(
        self, findings: Sequence[VulnerabilityFinding]
    ) -> float | None:
        confidences = [
            finding.model_confidence
            for finding in findings
            if finding.model_confidence is not None
        ]
        if not confidences:
            return None
        return round(sum(confidences) / len(confidences), 2)

    def _build_sections(
        self,
        *,
        findings: Sequence[VulnerabilityFinding],
        summary_counts: Mapping[str, int],
        average_confidence: float | None,
    ) -> list[ReportSection]:
        ordered_sections = [
            ("executive_summary", "Executive Summary"),
            ("findings_overview", "Findings Overview"),
            ("detailed_findings", "Detailed Findings"),
        ]
        return [
            ReportSection(
                key=section_key,
                title=section_title,
                content=self._derive_section_content(
                    section_key,
                    findings=findings,
                    summary_counts=summary_counts,
                    average_confidence=average_confidence,
                ),
                order=index,
            )
            for index, (section_key, section_title) in enumerate(ordered_sections, start=1)
        ]

    def _derive_section_content(
        self,
        section_key: str,
        *,
        findings: Sequence[VulnerabilityFinding],
        summary_counts: Mapping[str, int],
        average_confidence: float | None,
    ) -> str:
        if section_key == "executive_summary":
            summary_parts = [
                f"Validated {summary_counts.get('total_findings', len(findings))} finding(s)."
            ]
            severity_counts: list[str] = []
            for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"):
                count = summary_counts.get(severity, 0)
                if count:
                    severity_counts.append(f"{count} {severity.lower()}")
            if severity_counts:
                summary_parts.append(
                    "Severity distribution: " + ", ".join(severity_counts) + "."
                )
            scored_findings = summary_counts.get("scored_findings", 0)
            if average_confidence is not None and scored_findings:
                summary_parts.append(
                    "Average model confidence across "
                    f"{scored_findings} scored finding(s): {average_confidence:.2f}%."
                )
            return " ".join(summary_parts)

        if section_key == "findings_overview":
            overview_lines: list[str] = []
            for finding in findings:
                line = f"{finding.finding_id}: {finding.title} [{finding.severity}"
                if finding.cvss_score is not None:
                    line += f" | CVSS {finding.cvss_score:.1f}"
                if finding.model_confidence is not None:
                    line += f" | Model confidence {finding.model_confidence:.2f}%"
                line += "]"
                overview_lines.append(line)
            return "\n".join(overview_lines)

        if section_key == "detailed_findings":
            detail_blocks: list[str] = []
            for finding in findings:
                block_lines = [
                    f"{finding.finding_id} — {finding.title}",
                    f"Severity: {finding.severity}",
                ]
                if finding.cvss_score is not None:
                    block_lines.append(f"CVSS: {finding.cvss_score:.1f}")
                if finding.model_confidence is not None:
                    block_lines.append(
                        f"Model confidence: {finding.model_confidence:.2f}%"
                    )
                if finding.cve_id:
                    block_lines.append(f"CVE: {finding.cve_id}")
                if finding.cwe_id:
                    block_lines.append(f"CWE: {finding.cwe_id}")
                if finding.affected_asset:
                    block_lines.append(f"Affected asset: {finding.affected_asset}")
                if finding.source_url:
                    block_lines.append(f"Source URL: {finding.source_url}")
                if finding.evidence:
                    block_lines.append("Evidence: " + "; ".join(finding.evidence))
                if finding.references:
                    block_lines.append("References: " + "; ".join(finding.references))
                block_lines.append(finding.description)
                detail_blocks.append("\n".join(block_lines))
            return "\n\n".join(detail_blocks)

        raise ValueError(f"unsupported report section: {section_key}")

    def _hash_payload(self, payload: Mapping[str, Any]) -> str:
        serialized_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()

    def _save_report(self, report: VulnerabilityReport) -> str:
        report_path = self.output_dir / f"{report.report_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report.storage_path = str(report_path)
        serialized_report = json.dumps(
            report.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        report_path.write_text(serialized_report, encoding="utf-8")
        logger.info(
            "report_engine_saved_report report_id=%s path=%s sha256=%s",
            report.report_id,
            report.storage_path,
            report.sha256,
        )
        return str(report_path)

    def _report_from_mapping(self, report: Mapping[str, Any]) -> VulnerabilityReport:
        content = report.get("content", report)
        if not isinstance(content, Mapping):
            raise ValueError("saved report content must be an object")

        findings_raw = content.get("findings")
        if not isinstance(findings_raw, Sequence) or isinstance(findings_raw, (str, bytes, bytearray)):
            raise ValueError("saved report content must contain findings")

        findings = [self._coerce_finding(finding) for finding in findings_raw]
        if not findings:
            raise ValueError("saved report content must contain at least one finding")

        findings = sorted(
            findings,
            key=lambda finding: (
                -SEVERITY_PRIORITY.get(finding.severity, 0),
                -(finding.cvss_score if finding.cvss_score is not None else -1.0),
                finding.finding_id,
            ),
        )
        summary_counts = self._summary_counts(findings)
        average_confidence = self._average_model_confidence(findings)
        sections = self._build_sections(
            findings=findings,
            summary_counts=summary_counts,
            average_confidence=average_confidence,
        )
        source_context = content.get("source_context", {})
        if not isinstance(source_context, Mapping):
            source_context = {}

        sha256 = self._hash_payload(
            self._build_hash_payload(
                title=str(report.get("title") or "").strip(),
                description=str(report.get("description") or "").strip(),
                report_type=str(report.get("report_type") or "general").strip() or "general",
                summary_counts=summary_counts,
                average_confidence=average_confidence,
                source_context=source_context,
                findings=findings,
                sections=sections,
            )
        )

        return VulnerabilityReport(
            report_id=str(report.get("id") or report.get("report_id") or "").strip(),
            title=str(report.get("title") or "").strip(),
            description=str(report.get("description") or "").strip(),
            report_type=str(report.get("report_type") or "general").strip() or "general",
            generated_at=_normalize_timestamp(report.get("generated_at") or content.get("generated_at")),
            findings=findings,
            sections=sections,
            executive_summary=sections[0].content,
            summary_counts=summary_counts,
            average_model_confidence=average_confidence,
            sha256=sha256,
            storage_path=str(report.get("storage_path") or "").strip(),
            source_context=dict(source_context),
            generator_version=str(
                report.get("generator_version")
                or content.get("generator_version")
                or REPORT_ENGINE_VERSION
            ),
        )

    def export_markdown(
        self, report: VulnerabilityReport | Mapping[str, Any]
    ) -> str:
        normalized_report = (
            report if isinstance(report, VulnerabilityReport) else self._report_from_mapping(report)
        )
        lines = [
            f"# {normalized_report.title}",
            "",
            f"- Report ID: {normalized_report.report_id}",
            f"- Report Type: {normalized_report.report_type}",
            f"- Generated At: {normalized_report.generated_at}",
            f"- SHA256: {normalized_report.sha256}",
            "",
            "## Executive Summary",
            "",
            normalized_report.executive_summary,
            "",
        ]

        if normalized_report.source_context:
            lines.extend(["## Source Context", ""])
            for key, value in sorted(normalized_report.source_context.items()):
                lines.append(f"- {key}: {json.dumps(value, sort_keys=True, ensure_ascii=False)}")
            lines.append("")

        lines.extend(["## Findings Overview", ""])
        for finding in normalized_report.findings:
            overview = f"- {finding.finding_id}: {finding.title} ({finding.severity}"
            if finding.cvss_score is not None:
                overview += f", CVSS {finding.cvss_score:.1f}"
            if finding.model_confidence is not None:
                overview += f", model confidence {finding.model_confidence:.2f}%"
            overview += ")"
            lines.append(overview)
        lines.append("")

        lines.extend(["## Detailed Findings", ""])
        for finding in normalized_report.findings:
            lines.extend([f"### {finding.finding_id} — {finding.title}", ""])
            lines.append(f"- Severity: {finding.severity}")
            if finding.cvss_score is not None:
                lines.append(f"- CVSS: {finding.cvss_score:.1f}")
            if finding.model_confidence is not None:
                lines.append(f"- Model Confidence: {finding.model_confidence:.2f}%")
            if finding.cve_id:
                lines.append(f"- CVE: {finding.cve_id}")
            if finding.cwe_id:
                lines.append(f"- CWE: {finding.cwe_id}")
            if finding.affected_asset:
                lines.append(f"- Affected Asset: {finding.affected_asset}")
            if finding.source_url:
                lines.append(f"- Source URL: {finding.source_url}")
            lines.extend(["", finding.description, ""])
            if finding.evidence:
                lines.append("Evidence:")
                lines.extend(f"- {entry}" for entry in finding.evidence)
                lines.append("")
            if finding.references:
                lines.append("References:")
                lines.extend(f"- {entry}" for entry in finding.references)
                lines.append("")

        return "\n".join(lines).strip() + "\n"


def get_report_engine() -> ReportEngine:
    global _ENGINE_SINGLETON
    if _ENGINE_SINGLETON is None:
        _ENGINE_SINGLETON = ReportEngine()
    return _ENGINE_SINGLETON
