import unittest
from types import SimpleNamespace
import tempfile

from backend.approval.report_orchestrator import (
    ConfidenceBand,
    Evidence,
    ReportOrchestrator,
)
from backend.cve.verification_engine import VerificationEngine


class TestVerificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VerificationEngine()

    def test_cve_finding_is_verified_and_seeded(self):
        finding = SimpleNamespace(
            finding_id="FND-1",
            category="CVE",
            severity="CRITICAL",
            title="CVE-2021-41773: Apache Path Traversal",
            description="Apache/2.4.49 path traversal exposure confirmed",
            url="https://target.example",
            evidence={
                "detected_cve": "CVE-2021-41773",
                "references": ["https://nvd.nist.gov/vuln/detail/CVE-2021-41773"],
            },
        )

        enriched = self.engine.enrich_finding(finding)
        verification = enriched["verification"]

        self.assertEqual(verification["verification_status"], "VERIFIED")
        self.assertIn("CVE-2021-41773", enriched["identified_as"])
        self.assertGreaterEqual(len(enriched["auto_poc_steps"]), 1)
        self.assertGreaterEqual(len(enriched["mode_b_seed_candidates"]), 1)

    def test_behavioral_sqli_finding_gains_identifier_and_auto_poc(self):
        finding = SimpleNamespace(
            finding_id="FND-2",
            category="SQLI",
            severity="HIGH",
            title="Possible SQL injection in login",
            description="The application returned a SQL syntax error after a quote payload.",
            url="https://target.example/login",
            evidence={
                "error_messages": ["You have an error in your SQL syntax"],
                "request_response_pairs": [{"request": "a='", "response": "500"}],
            },
        )

        enriched = self.engine.enrich_finding(finding)
        verification = enriched["verification"]

        self.assertEqual(verification["verification_status"], "LIKELY")
        self.assertIn("CWE-89", enriched["identified_as"])
        self.assertIn("SQLI-HEURISTIC", enriched["identified_as"])
        self.assertGreaterEqual(len(enriched["auto_poc_steps"]), 3)
        self.assertGreaterEqual(len(enriched["mode_b_seed_candidates"]), 1)

    def test_path_traversal_finding_gains_cwe_and_seeded_poc(self):
        finding = SimpleNamespace(
            finding_id="FND-PT",
            category="PATH_TRAVERSAL",
            severity="MEDIUM",
            title="Potential path traversal: file parameter",
            description="File path parameter found in a request and may support directory traversal.",
            url="https://target.example/download?file=report.pdf",
            evidence={
                "request_response_pairs": [
                    {"url": "https://target.example/download?file=report.pdf", "parameter": "file"}
                ]
            },
        )

        enriched = self.engine.enrich_finding(finding)
        verification = enriched["verification"]

        self.assertEqual(verification["verification_status"], "LIKELY")
        self.assertIn("CWE-22", enriched["identified_as"])
        self.assertIn("PATH_TRAVERSAL-HEURISTIC", enriched["identified_as"])
        self.assertGreaterEqual(len(enriched["auto_poc_steps"]), 3)
        self.assertGreaterEqual(len(enriched["public_poc_refs"]), 1)

    def test_enrich_findings_returns_summary_counts(self):
        findings = [
            SimpleNamespace(
                finding_id="F1",
                category="CVE",
                severity="HIGH",
                title="CVE-2020-11022: jQuery issue",
                description="Known jQuery issue",
                url="https://a",
                evidence={"detected_cve": "CVE-2020-11022"},
            ),
            SimpleNamespace(
                finding_id="F2",
                category="XSS",
                severity="MEDIUM",
                title="Reflected XSS candidate",
                description="Reflected script marker appears in response",
                url="https://b",
                evidence={"request_response_pairs": [{"request": "xss", "response": "ok"}]},
            ),
        ]

        summary = self.engine.enrich_findings(findings)
        self.assertEqual(summary["verified_findings"], 1)
        self.assertEqual(summary["likely_findings"], 1)
        self.assertEqual(summary["mode_b_seeded_findings"], 2)


class TestReportOrchestratorVerification(unittest.TestCase):
    def test_report_carries_verification_and_auto_poc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = ReportOrchestrator(reports_dir=tmpdir)
            evidence = Evidence(
                screenshots=["one.png"],
                auto_poc_steps=["step 1", "step 2", "step 3"],
                identifiers=["SQLI-HEURISTIC"],
                verification_notes=["hybrid rule match"],
            )
            verification = {
                "verification_status": "LIKELY",
                "verification_score": 72,
            }
            report = orch.create_report(
                title="SQL injection candidate",
                vuln_type="SQLi",
                severity="High",
                target="api.example.com",
                description="Behavioral SQLi finding upgraded by verification engine",
                impact="Potential auth bypass",
                steps=["baseline request"],
                evidence=evidence,
                confidence=ConfidenceBand(confidence_pct=88.0, scope_compliant=True),
                verification=verification,
            )

            self.assertEqual(report.verification["verification_status"], "LIKELY")
            self.assertEqual(len(report.evidence.auto_poc_steps), 3)
            self.assertIn("SQLI-HEURISTIC", report.evidence.identifiers)
            self.assertNotEqual(orch.assess_quality(report).value, "insufficient")


if __name__ == "__main__":
    unittest.main()
