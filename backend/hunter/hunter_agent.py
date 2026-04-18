"""Pure AI Hunter Agent - Main Orchestrator.
Autonomous bug bounty hunter that combines all components:
- Explores targets
- Classifies endpoints with ProMoE
- Generates context-aware payloads
- Tests with governance approval
- Self-reflects on failures
- Generates professional PoCs
No external tools. Pure Python + AI reasoning."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ygb.hunter.agent")


@dataclass
class HuntConfig:
    target: str
    scope_rules: list[str]
    program_name: str = "Unknown Program"
    max_pages: int = 150
    max_payloads_per_param: int = 10
    max_rpm: int = 20  # requests per minute
    enable_reflection: bool = True
    auto_approve_medium: bool = True
    output_dir: Path = field(default_factory=lambda: Path("data/ssd/reports"))


@dataclass
class HuntResult:
    session_id: str
    target: str
    started_at: str
    completed_at: str
    duration_seconds: float
    pages_explored: int
    endpoints_tested: int
    payloads_sent: int
    findings: list
    reflection_cycles: int
    approvals_required: int
    approvals_granted: int
    tech_stack: list[str]
    summary_report_path: Optional[str]


class PureAIHunterAgent:
    """The complete autonomous hunter.
    Orchestrates all components into a full hunting loop."""

    def __init__(self, config: HuntConfig):
        self.config = config
        self._session_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self._findings = []
        self._reflection_cycles = 0
        self._approvals_required = 0
        self._approvals_granted = 0

        # Initialize components
        from backend.hunter.http_engine import SmartHTTPEngine
        from backend.hunter.explorer import AutonomousExplorer
        from backend.hunter.payload_engine import IntelligentPayloadTester, PayloadLibrary
        from backend.hunter.expert_collaboration import (
            ExpertCollaborationRouter,
            ProMoEHuntingClassifier,
        )
        from backend.hunter.hunting_reflector import HuntingReflector
        from backend.hunter.live_gate import LiveActionGate, ActionRequest
        from backend.hunter.poc_generator import PoCGenerator
        from backend.intelligence.scope_validator import ScopeValidator

        self._http = SmartHTTPEngine(session_id=self._session_id, max_rps=config.max_rpm)
        self._scope = ScopeValidator()
        self._explorer = AutonomousExplorer(self._http, self._scope)
        self._payload_tester = IntelligentPayloadTester(self._http)
        self._payload_library = PayloadLibrary()
        self._collaboration = ExpertCollaborationRouter()
        self._classifier = ProMoEHuntingClassifier()
        self._reflector = HuntingReflector()
        self._gate = LiveActionGate()
        self._poc_gen = PoCGenerator(output_dir=config.output_dir)

        logger.info("Hunter agent initialized: session=%s", self._session_id)

    async def hunt(self) -> HuntResult:
        """Execute complete autonomous hunt."""
        import time

        t_start = time.perf_counter()
        started_at = datetime.now(UTC).isoformat()

        logger.info("=" * 60)
        logger.info("STARTING HUNT: %s", self.config.target)
        logger.info("Session: %s", self._session_id)
        logger.info("=" * 60)

        # PHASE 1: Governance Check
        logger.info("Phase 1: Governance check...")
        self._check_governance()

        # PHASE 2: Exploration
        logger.info("Phase 2: Exploring target...")
        exploration = await self._explorer.explore(
            self.config.target, self.config.scope_rules, self.config.max_pages
        )
        logger.info(
            "Exploration complete: %d endpoints, %d forms, tech: %s",
            len(exploration.endpoints),
            len(exploration.forms),
            exploration.tech_stack,
        )

        # PHASE 3: Endpoint Classification
        logger.info("Phase 3: Classifying endpoints with ProMoE...")
        classified_endpoints = self._classify_endpoints(exploration)

        # PHASE 4: Payload Generation & Testing
        logger.info("Phase 4: Testing payloads...")
        await self._test_endpoints(classified_endpoints, exploration.tech_stack)

        # PHASE 5: Generate Reports
        logger.info("Phase 5: Generating reports...")
        summary_path = self._generate_reports()

        elapsed = time.perf_counter() - t_start
        completed_at = datetime.now(UTC).isoformat()

        result = HuntResult(
            session_id=self._session_id,
            target=self.config.target,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=round(elapsed, 2),
            pages_explored=exploration.total_pages_visited,
            endpoints_tested=len(classified_endpoints),
            payloads_sent=self._http.get_stats()["total_requests"],
            findings=self._findings,
            reflection_cycles=self._reflection_cycles,
            approvals_required=self._approvals_required,
            approvals_granted=self._approvals_granted,
            tech_stack=exploration.tech_stack,
            summary_report_path=str(summary_path) if summary_path else None,
        )

        logger.info("=" * 60)
        logger.info("HUNT COMPLETE")
        logger.info("Findings: %d", len(self._findings))
        logger.info("Duration: %.1fs", elapsed)
        logger.info("=" * 60)

        await self._http.close()
        return result

    def _check_governance(self):
        """Verify all governance controls are in place."""
        from backend.governance.kill_switch import check_or_raise
        from backend.governance.authority_lock import AuthorityLock

        # Kill switch check
        check_or_raise()

        # Authority lock check
        locks = AuthorityLock.verify_all_locked()
        if not locks["all_locked"]:
            raise RuntimeError(f"Authority lock violation: {locks['violations']}")

        logger.info("Governance check: PASS")

    def _classify_endpoints(self, exploration) -> list[dict]:
        """Classify endpoints by vulnerability type using ProMoE."""
        classified = []

        for endpoint in exploration.endpoints[:50]:  # Top 50 most interesting
            vuln_types = self._classifier.classify_endpoint(
                endpoint.url, "", endpoint.tech_stack
            )

            if vuln_types:
                classified.append(
                    {
                        "endpoint": endpoint,
                        "vuln_types": vuln_types[:3],  # Top 3 types
                        "priority": endpoint.interesting_score,
                    }
                )

        # Sort by priority
        classified.sort(key=lambda x: x["priority"], reverse=True)
        logger.info("Classified %d endpoints for testing", len(classified))
        return classified

    async def _test_endpoints(self, classified_endpoints: list[dict], tech_stack: list[str]):
        """Test endpoints with intelligent payloads."""
        for item in classified_endpoints:
            endpoint = item["endpoint"]
            vuln_types = item["vuln_types"]

            if not endpoint.params:
                continue

            logger.info(
                "Testing endpoint: %s (params: %s, types: %s)",
                endpoint.url,
                endpoint.params,
                vuln_types,
            )

            for param in endpoint.params[:3]:  # Test top 3 params
                await self._test_parameter(endpoint.url, param, vuln_types, tech_stack)

    async def _test_parameter(
        self, url: str, param: str, vuln_types: list[str], tech_stack: list[str]
    ):
        """Test one parameter with multiple vulnerability types."""
        # Get baseline
        baseline = await self._payload_tester.get_baseline(url, param)
        if not baseline:
            logger.warning("Could not get baseline for %s?%s", url, param)
            return

        for vuln_type in vuln_types[:2]:  # Test top 2 vuln types per param
            payloads = self._payload_library.get_for_type(vuln_type)
            if not payloads:
                continue

            for payload in payloads[: self.config.max_payloads_per_param]:
                # Request approval through gate
                from backend.hunter.live_gate import ActionRequest

                action = ActionRequest(
                    request_id=f"{self._session_id}_{param}_{payload.payload_id}",
                    action_type="payload_test",
                    target_url=url,
                    payload_value=payload.value,
                    vuln_type=vuln_type,
                    risk_level="UNKNOWN",
                    requester="hunter_agent",
                    timestamp=datetime.now(UTC).isoformat(),
                    context={"param": param, "tech_stack": tech_stack},
                )

                decision = self._gate.request_approval(action, "hunter_agent")

                if not decision.approved:
                    self._approvals_required += 1
                    logger.warning(
                        "Payload blocked by gate: %s (risk: %s)",
                        payload.payload_id,
                        decision.risk_level,
                    )
                    # In real usage, human would approve via approve_action.py
                    # For now, skip HIGH risk payloads
                    continue

                self._approvals_granted += 1

                # Test payload
                try:
                    result = await self._payload_tester.test_payload(
                        url, param, payload, decision.request_id, baseline
                    )

                    if result.triggered:
                        logger.info(
                            "VULNERABILITY FOUND: %s in %s (confidence: %.2f)",
                            vuln_type,
                            param,
                            result.confidence,
                        )
                        self._record_finding(result)

                        # Signal to expert collaboration
                        from backend.hunter.expert_collaboration import ExpertSignal

                        signal = ExpertSignal(
                            from_expert=f"web_{vuln_type}",
                            signal_type=vuln_type,
                            confidence=result.confidence,
                            context={"url": url, "param": param},
                            suggests_next=[],
                        )
                        self._collaboration.receive_signal(signal)

                        # Record success for learning
                        self._reflector.record_success(payload, vuln_type)

                    else:
                        # Payload failed — reflect and generate bypasses
                        if self.config.enable_reflection:
                            await self._reflect_on_failure(
                                payload, result.payload.vuln_type, result, baseline
                            )

                except Exception as e:
                    logger.error("Payload test failed: %s → %s", payload.payload_id, e)

    async def _reflect_on_failure(self, payload, vuln_type, result, baseline):
        """Self-reflect on why payload failed and try bypasses."""
        from backend.hunter.http_engine import HTTPResponse

        # Create HTTPResponse from result
        response = HTTPResponse(
            status_code=result.response_status,
            headers={},
            body="",
            url=result.endpoint_url,
            elapsed_ms=result.response_time_ms,
            redirects=[],
            request_id=result.request_id,
            evidence_path=None,
            content_type="",
            content_length=0,
            has_error_message=False,
            server_header="",
            cookies={},
        )

        failure = self._reflector.analyze_failure(payload, response, baseline)

        if failure.confidence > 0.5:
            logger.info(
                "Reflection: %s (confidence: %.2f) → trying %d bypasses",
                failure.failure_type,
                failure.confidence,
                len(failure.suggested_bypasses),
            )

            # Generate bypass variants
            variants = self._reflector.generate_bypass_variants(payload, failure)
            self._reflection_cycles += 1

            # Test top 2 bypass variants
            for variant in variants[:2]:
                try:
                    from backend.hunter.live_gate import ActionRequest

                    action = ActionRequest(
                        request_id=f"{self._session_id}_bypass_{variant.payload_id}",
                        action_type="payload_test",
                        target_url=result.endpoint_url,
                        payload_value=variant.value,
                        vuln_type=vuln_type,
                        risk_level="UNKNOWN",
                        requester="hunter_agent_reflector",
                        timestamp=datetime.now(UTC).isoformat(),
                        context={"bypass_attempt": True, "original": payload.payload_id},
                    )

                    decision = self._gate.request_approval(action, "hunter_agent")
                    if not decision.approved:
                        continue

                    bypass_result = await self._payload_tester.test_payload(
                        result.endpoint_url,
                        result.param_name,
                        variant,
                        decision.request_id,
                        baseline,
                    )

                    if bypass_result.triggered:
                        logger.info(
                            "BYPASS SUCCESS: %s worked! (confidence: %.2f)",
                            variant.payload_id,
                            bypass_result.confidence,
                        )
                        self._record_finding(bypass_result)
                        self._reflector.record_success(variant, vuln_type)
                        break  # Success, no need to try more

                except Exception as e:
                    logger.error("Bypass test failed: %s", e)

    def _record_finding(self, result):
        """Record a vulnerability finding."""
        finding = self._poc_gen.create_finding(
            vuln_type=result.payload.vuln_type,
            target_url=result.endpoint_url,
            vulnerable_param=result.param_name,
            payload_used=result.payload.value,
            evidence=result.evidence,
            confidence=result.confidence,
        )

        self._findings.append(finding)
        logger.info("Finding recorded: %s", finding.finding_id)

    def _generate_reports(self) -> Optional[Path]:
        """Generate PoC reports for all findings."""
        if not self._findings:
            logger.info("No findings to report")
            return None

        # Generate individual reports
        for finding in self._findings:
            self._poc_gen.save_report(finding)

        # Generate summary report
        summary = self._poc_gen.generate_summary_report(self._findings)
        summary_path = self.config.output_dir / f"hunt_summary_{self._session_id}.md"
        summary_path.write_text(summary)

        logger.info("Reports generated: %s", summary_path)
        return summary_path

    def get_status(self) -> dict:
        """Get current hunt status."""
        return {
            "session_id": self._session_id,
            "target": self.config.target,
            "findings": len(self._findings),
            "requests_sent": self._http.get_stats()["total_requests"],
            "reflection_cycles": self._reflection_cycles,
            "approvals_required": self._approvals_required,
            "approvals_granted": self._approvals_granted,
            "active_experts": self._collaboration.get_active_experts(),
            "gate_summary": self._gate.get_audit_summary(),
        }
