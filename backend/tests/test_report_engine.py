from __future__ import annotations

import json

import pytest

from backend.reporting.report_engine import ReportEngine


def _finding(
    finding_id: str,
    *,
    title: str = "SQL injection in login",
    description: str = "Union-based SQL injection in the login flow allows authentication bypass and unrestricted access to privileged application data.",
    severity: str = "HIGH",
    cvss_score: float = 8.8,
    model_confidence: float = 0.91,
    cve_id: str = "CVE-2026-2000",
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "title": title,
        "description": description,
        "severity": severity,
        "cvss_score": cvss_score,
        "model_confidence": model_confidence,
        "cve_id": cve_id,
    }


def test_build_report_zero_findings_raises_value_error(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)

    with pytest.raises(ValueError, match="at least one finding"):
        engine.build_report(
            report_id="rpt-empty",
            title="Empty findings",
            description="Empty findings payload",
            report_type="security",
            findings=[],
        )


def test_build_report_short_description_raises_value_error(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)

    with pytest.raises(ValueError, match="description_too_short"):
        engine.build_report(
            report_id="rpt-short",
            title="Short description",
            description="Short findings payload",
            report_type="security",
            findings=[
                {
                    "finding_id": "FND-SHORT",
                    "title": "Short finding",
                    "description": "too short",
                    "severity": "HIGH",
                }
            ],
        )


def test_executive_summary_is_derived_from_real_counts_and_model_confidence(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)
    report = engine.build_report(
        report_id="rpt-summary",
        title="Summary report",
        description="Executive summary derivation coverage",
        report_type="security",
        findings=[
            _finding("FND-1", severity="CRITICAL", model_confidence=0.82, cvss_score=9.8),
            _finding("FND-2", severity="MEDIUM", model_confidence=0.90, cvss_score=5.4, cve_id="CVE-2026-2001"),
        ],
    )

    summary = report.executive_summary.lower()
    assert "validated 2 finding(s)" in summary
    assert "1 critical" in summary
    assert "1 medium" in summary
    assert "86.00%" in report.executive_summary
    assert "placeholder" not in summary
    assert "template" not in summary


def test_sha256_changes_when_findings_change(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)
    report_one = engine.build_report(
        report_id="rpt-hash-1",
        title="Hash report",
        description="Hash comparison coverage",
        report_type="security",
        findings=[_finding("FND-HASH")],
    )
    report_two = engine.build_report(
        report_id="rpt-hash-2",
        title="Hash report",
        description="Hash comparison coverage",
        report_type="security",
        findings=[
            _finding(
                "FND-HASH",
                description="Union-based SQL injection in the login flow allows authentication bypass, unrestricted data access, and elevated account takeover across administrative roles.",
            )
        ],
    )

    assert report_one.sha256 != report_two.sha256


def test_sha256_is_deterministic_across_generation_metadata(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)
    report_one = engine.build_report(
        report_id="rpt-det-1",
        title="Deterministic hash report",
        description="Deterministic hash comparison coverage",
        report_type="security",
        generated_at="2026-01-01T00:00:00+00:00",
        findings=[_finding("FND-DET")],
    )
    report_two = engine.build_report(
        report_id="rpt-det-2",
        title="Deterministic hash report",
        description="Deterministic hash comparison coverage",
        report_type="security",
        generated_at="2026-02-01T00:00:00+00:00",
        findings=[_finding("FND-DET")],
    )

    assert report_one.sha256 == report_two.sha256


def test_markdown_export_contains_all_finding_ids(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)
    report = engine.build_report(
        report_id="rpt-md",
        title="Markdown report",
        description="Markdown coverage",
        report_type="security",
        findings=[
            _finding("FND-MD-1"),
            _finding("FND-MD-2", cve_id="CVE-2026-2002", severity="MEDIUM", cvss_score=5.9),
        ],
    )

    markdown = engine.export_markdown(report)

    assert "FND-MD-1" in markdown
    assert "FND-MD-2" in markdown


def test_report_contains_no_fabricated_content(tmp_path):
    engine = ReportEngine(output_dir=tmp_path)
    report = engine.build_report(
        report_id="rpt-pure",
        title="Pure report",
        description="No fabricated content coverage",
        report_type="security",
        findings=[
            _finding(
                "FND-PURE",
                cve_id="",
                model_confidence=None,
            )
        ],
    )

    payload = report.to_content_dict()
    serialized = json.dumps(payload, sort_keys=True).lower()

    assert payload["findings"][0]["cve_id"] == ""
    assert payload["findings"][0]["source_url"] == ""
    assert payload["findings"][0]["description"].startswith("Union-based SQL injection")
    assert "placeholder" not in serialized
    assert "fabricated" not in serialized
    assert "no description provided" not in serialized
