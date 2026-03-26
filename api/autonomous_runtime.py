"""Reasoning-first autonomous runtime helpers.

This module upgrades the backend from simple task dispatch into a structured,
reasoning-oriented system with MoE-style routing, verification planning,
duplicate suppression, active-learning suggestions, and response generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from impl_v1.phase49.governors.g32_reasoning_scope_engine import (
    DuplicateCheckResult,
    ReasoningExplanation,
    ScopeIntelligenceResult,
    TestSelectionResult,
    check_duplicates,
    detect_context_indicators,
    generate_reasoning_explanation,
    parse_scope_text,
    select_tests_for_context,
)
from impl_v1.training.data.autonomous_data_pipeline import (
    AutonomousDataPipeline,
    DataQualityAssessment,
)
from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    StrategyFeedbackStore,
    token_overlap,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class AgentRoute:
    agent_name: str
    score: float
    rationale: str
    specialties: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 4)
        return payload


@dataclass(slots=True)
class ReasoningStep:
    name: str
    summary: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationBlueprint:
    level: str
    methods: list[str]
    blind_checks: list[str]
    stop_conditions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LearningCandidate:
    candidate_id: str
    focus_area: str
    reason: str
    suggested_strategy: str
    uncertainty: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["uncertainty"] = round(self.uncertainty, 4)
        return payload


@dataclass(slots=True)
class ReasonedResponse:
    answer: str
    reasoning: list[str]
    recommendations: list[str]
    confidence: float
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(self.confidence, 4)
        return payload


class AutonomousCoordinator:
    """Composes thinking, routing, data quality, and response behavior."""

    def __init__(
        self,
        accuracy_feedback: AccuracyFeedbackStore,
        strategy_feedback: StrategyFeedbackStore,
        data_pipeline: Optional[AutonomousDataPipeline] = None,
    ) -> None:
        self.accuracy_feedback = accuracy_feedback
        self.strategy_feedback = strategy_feedback
        self.data_pipeline = data_pipeline or AutonomousDataPipeline()

    def route_agents(
        self,
        task_type: str,
        context: Optional[dict[str, Any]],
        agents: Sequence[Any],
    ) -> list[AgentRoute]:
        context = context or {}
        query = " ".join(
            str(context.get(key) or "")
            for key in ("query", "text", "target", "target_url", "goal")
        ).lower()
        dom_excerpt = str(context.get("dom_excerpt") or "")
        meta_content = str(context.get("meta_content") or "")
        indicators = detect_context_indicators(dom_excerpt, meta_content + " " + query)
        routes: list[AgentRoute] = []

        for agent in agents:
            specialties = [
                str(item).lower() for item in getattr(agent, "specialties", ())
            ]
            score = 0.15
            reasons: list[str] = []
            if task_type.lower() in specialties:
                score += 0.45
                reasons.append("Direct specialty match")
            if any(
                keyword in query for keyword in ("why", "reason", "explain", "answer")
            ) and ("voice" in specialties or "request" in specialties):
                score += 0.2
                reasons.append("Reasoning/query response workload")
            if any(
                keyword in query
                for keyword in ("verify", "proof", "time-based", "oob", "blind")
            ) and ("workflow" in specialties or "bounty" in specialties):
                score += 0.2
                reasons.append("Verification-heavy target")
            if any(
                keyword in query for keyword in ("learn", "train", "improve", "dataset")
            ) and ("training" in specialties or "ml" in specialties):
                score += 0.2
                reasons.append("Learning/data objective")
            if any(
                keyword in query for keyword in ("duplicate", "repeat", "same finding")
            ) and ("workflow" in specialties or "request" in specialties):
                score += 0.12
                reasons.append("Duplicate-sensitive request")
            if any(
                ind.value in {"API_ENDPOINT", "DATABASE_INTERACTION", "LOGIN_FORM"}
                for ind in indicators
            ):
                if "crawl" in specialties or "workflow" in specialties:
                    score += 0.08
                    reasons.append("Context indicators favor deeper technical routing")

            history = self.strategy_feedback.get(
                strategy_name=getattr(agent, "name", "unknown"),
                task_type=task_type.lower(),
            )
            if history.runs:
                score += max(min((history.score - 0.5) * 0.3, 0.12), -0.12)
                reasons.append(f"Historical score {history.score:.2f}")

            routes.append(
                AgentRoute(
                    agent_name=getattr(agent, "name", "unknown"),
                    score=max(0.01, min(score, 0.99)),
                    rationale="; ".join(reasons) or "Baseline route",
                    specialties=[
                        str(item) for item in getattr(agent, "specialties", ())
                    ],
                )
            )

        routes.sort(key=lambda item: item.score, reverse=True)
        return routes

    def _build_duplicate_signal(
        self,
        *,
        target: str,
        current_findings: Sequence[dict[str, Any]],
        query: str,
    ) -> DuplicateCheckResult:
        duplicate_density = 0.0
        if current_findings:
            overlaps = [
                token_overlap(query, str(item.get("title") or ""))
                for item in current_findings
            ]
            duplicate_density = max(overlaps or [0.0])
        summary = self.accuracy_feedback.summary()
        acceptance_rate = 0.5
        if isinstance(summary, dict) and int(summary.get("validated_records", 0)) > 0:
            acceptance_rate = float(summary.get("precision", 0.0))
        return check_duplicates(
            target=target or "unknown-target",
            cve_overlap_count=int(query.lower().count("cve-")),
            historical_acceptance_rate=float(acceptance_rate),
            program_age_days=int(len(target) * 3) if target else 30,
            platform_duplicate_density=min(duplicate_density, 1.0),
        )

    def build_reasoning_trace(
        self,
        task_type: str,
        context: Optional[dict[str, Any]],
        agents: Sequence[Any],
    ) -> dict[str, Any]:
        context = context or {}
        target = str(context.get("target") or context.get("target_url") or "")
        query = str(context.get("query") or context.get("text") or target)
        scope_text = str(context.get("scope_text") or "")
        dom_excerpt = str(context.get("dom_excerpt") or "")
        meta_content = str(context.get("meta_content") or "")
        severity = str(context.get("severity") or "MEDIUM")
        category = str(context.get("category") or "AUTH")
        evidence = dict(context.get("evidence") or {})
        current_findings = list(context.get("current_findings") or [])

        scope_result = (
            parse_scope_text(scope_text, context.get("program_name", ""))
            if scope_text
            else None
        )
        indicators = detect_context_indicators(dom_excerpt, meta_content + " " + query)
        selection = select_tests_for_context(indicators)
        routes = self.route_agents(task_type, context, agents)
        duplicate_signal = self._build_duplicate_signal(
            target=target,
            current_findings=current_findings,
            query=query,
        )
        data_quality = self.data_pipeline.assess_candidate(
            category=category,
            severity=severity,
            title=str(context.get("title") or query[:80]),
            description=str(context.get("description") or query),
            url=target,
            evidence=evidence,
            verification_status=str(context.get("verification_status") or "UNVERIFIED"),
            duplicate=not duplicate_signal.should_proceed,
            confidence=float(context.get("confidence") or 0.0),
        )

        primary_test = selection.enabled_tests[0] if selection.enabled_tests else None
        explanation: Optional[ReasoningExplanation] = None
        if primary_test is not None:
            explanation = generate_reasoning_explanation(
                primary_test,
                severity.upper(),
                target or "request",
                ", ".join(ind.value for ind in indicators) or "general web context",
            )

        verification_methods = [
            "response-validation",
            "proof-verification",
            "duplicate-suppression",
        ]
        blind_checks: list[str] = []
        if any(
            test.value in {"SQLI", "SSRF", "RCE", "AUTH"}
            for test in selection.enabled_tests
        ):
            blind_checks.append("time-based-blind-check")
        if any(
            word in query.lower() for word in ("callback", "dns", "oob", "webhook")
        ) or category.upper() in {"SSRF", "XXE", "RCE"}:
            blind_checks.append("oob-callback-check")
        stop_conditions = [
            "stop-on-duplicate-signal",
            "stop-on-low-data-quality",
            "stop-on-verification-failure",
        ]
        blueprint = VerificationBlueprint(
            level="strict"
            if duplicate_signal.should_proceed is False or data_quality.score < 0.55
            else "standard",
            methods=verification_methods,
            blind_checks=blind_checks,
            stop_conditions=stop_conditions,
        )

        steps = [
            ReasoningStep(
                name="analyze-input",
                summary="Parsed target, mode, and contextual indicators before choosing actions",
                evidence=[
                    target or query,
                    ", ".join(ind.value for ind in indicators)
                    or "no explicit indicators",
                ],
            ),
            ReasoningStep(
                name="route-experts",
                summary=f"MoE router ranked {routes[0].agent_name if routes else 'workflow-orchestrator'} as primary expert",
                evidence=[route.rationale for route in routes[:3]],
            ),
            ReasoningStep(
                name="verification-plan",
                summary="Prepared verification-first execution blueprint before any action",
                evidence=blueprint.methods + blueprint.blind_checks,
            ),
            ReasoningStep(
                name="data-quality",
                summary=f"Candidate quality score {data_quality.score:.2f} routed to {data_quality.destination}",
                evidence=data_quality.reasons or ["High-quality candidate"],
            ),
        ]

        learning_candidate: Optional[LearningCandidate] = None
        uncertainty = 1.0 - min(max(data_quality.score, 0.0), 1.0)
        if data_quality.destination == "quarantine" or uncertainty >= 0.35:
            learning_candidate = LearningCandidate(
                candidate_id=f"ALN-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                focus_area=category.upper(),
                reason="Needs additional evidence or exploration to improve future routing",
                suggested_strategy=routes[0].agent_name
                if routes
                else "workflow-orchestrator",
                uncertainty=uncertainty,
            )

        return {
            "generated_at": _now_iso(),
            "scope": self._serialize_scope(scope_result),
            "context_indicators": [ind.value for ind in indicators],
            "selected_tests": self._serialize_test_selection(selection),
            "expert_routes": [route.to_dict() for route in routes[:5]],
            "duplicate_signal": self._serialize_duplicate_signal(duplicate_signal),
            "verification_blueprint": blueprint.to_dict(),
            "data_quality": data_quality.to_dict(),
            "learning_candidate": learning_candidate.to_dict()
            if learning_candidate
            else None,
            "explanation": self._serialize_explanation(explanation),
            "steps": [step.to_dict() for step in steps],
        }

    def build_reasoned_response(
        self,
        *,
        query: str,
        task_type: str,
        context: Optional[dict[str, Any]],
        agents: Sequence[Any],
        similar_experiences: Optional[Sequence[dict[str, Any]]] = None,
    ) -> ReasonedResponse:
        trace = self.build_reasoning_trace(
            task_type, {**(context or {}), "query": query}, agents
        )
        routes = trace.get("expert_routes", [])
        selected_tests = trace.get("selected_tests", {})
        enabled_tests = selected_tests.get("enabled_tests", [])
        blueprint = trace.get("verification_blueprint", {})
        top_agent = routes[0]["agent_name"] if routes else "workflow-orchestrator"
        target = str(
            (context or {}).get("target")
            or (context or {}).get("target_url")
            or "this target"
        )

        answer = (
            f"I would reason about {target} before acting: route through {top_agent}, prioritize "
            f"{', '.join(enabled_tests[:3]) or 'safe baseline checks'}, and verify with "
            f"{', '.join(blueprint.get('methods', [])[:3]) or 'response validation'} before keeping any finding."
        )
        reasoning = [
            step.get("summary", "")
            for step in trace.get("steps", [])
            if step.get("summary")
        ]
        recommendations = [
            f"Use {blueprint.get('level', 'standard')} verification for this request",
            f"Enable blind checks: {', '.join(blueprint.get('blind_checks', [])) or 'none required'}",
            f"Reject or quarantine low-quality data below score {trace.get('data_quality', {}).get('score', 0.0):.2f} when evidence is incomplete",
        ]
        if similar_experiences:
            recommendations.append(
                f"Reuse {min(len(similar_experiences), 3)} similar experiences before exploring a new strategy"
            )
        citations = [
            "api/orchestrator.py",
            "api/autonomous_runtime.py",
            "impl_v1/phase49/governors/g32_reasoning_scope_engine.py",
        ]
        confidence = 0.65
        if trace.get("data_quality", {}).get("accepted"):
            confidence += 0.15
        if trace.get("duplicate_signal", {}).get("should_proceed"):
            confidence += 0.1
        if routes:
            confidence += min(float(routes[0].get("score", 0.0)) * 0.15, 0.1)

        return ReasonedResponse(
            answer=answer,
            reasoning=reasoning,
            recommendations=recommendations,
            confidence=min(confidence, 0.95),
            citations=citations,
        )

    def recommend_idle_learning(self) -> list[dict[str, Any]]:
        summary = self.accuracy_feedback.summary()
        by_category = (
            summary.get("by_category", {}) if isinstance(summary, dict) else {}
        )
        recommendations: list[dict[str, Any]] = []
        for category, metrics in sorted(by_category.items()):
            if not isinstance(metrics, dict):
                continue
            validated = int(metrics.get("validated_records", 0))
            false_positive_rate = float(metrics.get("false_positive_rate", 0.0))
            if validated < 3:
                recommendations.append(
                    {
                        "focus_area": category,
                        "reason": "Underrepresented category in verified feedback",
                        "strategy": "collect-more-validated-samples",
                    }
                )
            elif false_positive_rate >= 0.15:
                recommendations.append(
                    {
                        "focus_area": category,
                        "reason": f"False-positive rate {false_positive_rate:.2%} is high",
                        "strategy": "tighten-verification-and-review-edge-cases",
                    }
                )
        if not recommendations:
            recommendations.append(
                {
                    "focus_area": "generalization",
                    "reason": "No weak categories found; explore new but governed strategies during idle time",
                    "strategy": "review-quarantine-queue-and-refresh-holdout",
                }
            )
        return recommendations[:5]

    def snapshot(self, agents: Sequence[Any]) -> dict[str, Any]:
        return {
            "data_pipeline": self.data_pipeline.summary(),
            "idle_learning": self.recommend_idle_learning(),
            "agent_routes": [
                route.to_dict()
                for route in self.route_agents("workflow", {}, agents)[:5]
            ],
        }

    def _serialize_scope(
        self, scope_result: Optional[ScopeIntelligenceResult]
    ) -> Optional[dict[str, Any]]:
        if scope_result is None:
            return None
        return {
            "allowed_assets": [item.asset for item in scope_result.allowed_assets],
            "conditional_assets": [
                item.asset for item in scope_result.conditional_assets
            ],
            "forbidden_assets": [item.asset for item in scope_result.forbidden_assets],
            "read_only_assets": [item.asset for item in scope_result.read_only_assets],
            "notes": list(scope_result.notes),
            "determinism_hash": scope_result.determinism_hash,
        }

    def _serialize_test_selection(
        self, selection: TestSelectionResult
    ) -> dict[str, Any]:
        return {
            "enabled_tests": [item.value for item in selection.enabled_tests],
            "disabled_tests": [item.value for item in selection.disabled_tests],
            "reasoning": [
                {
                    "category": item.category.value,
                    "enabled": item.enabled,
                    "reason": item.reason,
                }
                for item in selection.reasoning
            ],
            "determinism_hash": selection.determinism_hash,
        }

    def _serialize_duplicate_signal(
        self, signal: DuplicateCheckResult
    ) -> dict[str, Any]:
        return {
            "should_proceed": signal.should_proceed,
            "suppression_reason": signal.suppression_reason.value,
            "duplicate_density_score": round(signal.duplicate_density_score, 4),
            "reasoning": signal.reasoning,
        }

    def _serialize_explanation(
        self, explanation: Optional[ReasoningExplanation]
    ) -> Optional[dict[str, Any]]:
        if explanation is None:
            return None
        return {
            "why_this_matters": explanation.why_this_matters,
            "why_likely_accepted": explanation.why_likely_accepted,
            "business_impact": explanation.business_impact,
            "risk_framing": explanation.risk_framing,
            "determinism_hash": explanation.determinism_hash,
        }
