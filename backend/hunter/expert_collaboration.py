"""Expert Collaboration Router.
During hunting, multiple experts collaborate:
Web XSS expert finds reflection → routes to SSTI expert → routes to RCE expert
IDOR expert finds access → routes to privilege escalation expert
SSRF expert finds internal → routes to Cloud expert
No human needed between experts — they collaborate automatically.
Uses ProMoE routing for intelligent expert selection."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ygb.hunter.collaboration")


@dataclass
class ExpertSignal:
    from_expert: str  # which expert is signaling
    signal_type: str  # what they found
    confidence: float
    context: dict  # details to pass to next expert
    suggests_next: list[str]  # expert fields that should continue


COLLABORATION_GRAPH = {
    # When web_xss expert signals → also check:
    "web_xss": ["web_sqli", "web_csrf", "web_ssrf"],
    # SQLi finding → check for auth bypass
    "web_sqli": ["web_auth_bypass", "web_idor"],
    # SSRF finding → check cloud metadata
    "web_ssrf": ["cloud_aws", "cloud_azure", "cloud_gcp"],
    # Auth bypass → privilege escalation
    "web_auth_bypass": ["web_idor", "network_rce"],
    # IDOR → check API endpoints
    "web_idor": ["api_rest", "api_broken_auth"],
    # API broken auth → check graphql
    "api_broken_auth": ["api_graphql", "api_rest"],
    # RCE found → check for command injection paths
    "network_rce": ["network_overflow", "iot_firmware"],
    # Cloud findings → check all cloud providers
    "cloud_aws": ["cloud_azure", "cloud_gcp"],
    # Blockchain finding → check access control
    "blockchain_sc": [],
    # Mobile findings → check storage issues
    "mobile_android": ["mobile_apk"],
    "mobile_ios": [],
    # Crypto weakness → check auth
    "crypto_weak": ["web_auth_bypass"],
}


class ExpertCollaborationRouter:
    """Routes findings between experts.
    When expert A finds something, determines which other experts
    should investigate the same target/endpoint."""

    def __init__(self):
        self._active_experts: dict[str, float] = {}  # expert → confidence
        self._signals: list[ExpertSignal] = []

    def receive_signal(self, signal: ExpertSignal):
        """Expert sends a finding signal to the collaboration network."""
        self._signals.append(signal)
        logger.info(
            "Expert signal: %s found %s (confidence=%.2f)",
            signal.from_expert,
            signal.signal_type,
            signal.confidence,
        )

        # Determine which experts should be activated
        next_experts = COLLABORATION_GRAPH.get(signal.from_expert, [])
        for expert_field in next_experts:
            # Boost confidence for related experts
            existing = self._active_experts.get(expert_field, 0.0)
            new_conf = max(existing, signal.confidence * 0.7)
            self._active_experts[expert_field] = new_conf
            logger.debug("Activating expert %s (confidence=%.2f)", expert_field, new_conf)

    def get_next_expert(self) -> Optional[str]:
        """Get the next expert to activate based on signals."""
        if not self._active_experts:
            return None
        return max(self._active_experts, key=self._active_experts.get)

    def deactivate(self, expert_field: str):
        self._active_experts.pop(expert_field, None)

    def get_active_experts(self) -> dict:
        return dict(sorted(self._active_experts.items(), key=lambda x: x[1], reverse=True))

    def get_attack_chains(self) -> list[list[str]]:
        """Find potential attack chains from signals."""
        chains = []
        for sig in self._signals:
            chain = [sig.from_expert]
            related = COLLABORATION_GRAPH.get(sig.from_expert, [])
            if related:
                chain.extend(related[:2])
            chains.append(chain)
        return chains


class ProMoEHuntingClassifier:
    """Uses ProMoE model to classify what type of vulnerability
    an endpoint/response combination suggests.
    Drives expert selection."""

    def __init__(self, model=None):
        self._model = model
        self._pattern_engine = None

    def _get_pattern_engine(self):
        if self._pattern_engine is None:
            from backend.intelligence.vuln_detector import VulnerabilityPatternEngine

            self._pattern_engine = VulnerabilityPatternEngine()
        return self._pattern_engine

    def classify_endpoint(
        self, url: str, response_body: str, tech_stack: list[str]
    ) -> list[str]:
        """Given an endpoint + response, determine which vulnerability
        types are most likely. Returns ordered list of vuln types."""
        engine = self._get_pattern_engine()
        text = f"{url} {response_body[:500]}"
        signals = engine.analyze(text)

        # Pattern-based
        vuln_types = [s.vuln_type for s in signals if s.confidence > 0.2]

        # Tech stack based
        tech_lower = " ".join(tech_stack).lower()
        if "php" in tech_lower:
            vuln_types.extend(["sqli", "path_traversal", "rce"])
        if "graphql" in tech_lower:
            vuln_types.append("api_graphql")
        if "wordpress" in tech_lower:
            vuln_types.extend(["sqli", "xss", "path_traversal"])
        if "aws" in tech_lower:
            vuln_types.append("ssrf")
        if "jwt" in tech_lower:
            vuln_types.append("auth_bypass")

        # URL-based hints
        url_lower = url.lower()
        if any(p in url_lower for p in ["/api/", "/v1/", "/v2/"]):
            vuln_types.extend(["idor", "api_broken_auth"])
        if "redirect" in url_lower or "url=" in url_lower:
            vuln_types.append("open_redirect")
        if "file" in url_lower or "path" in url_lower or "include" in url_lower:
            vuln_types.append("path_traversal")

        # Deduplicate, preserve order
        seen = set()
        result = []
        for v in vuln_types:
            if v not in seen:
                seen.add(v)
                result.append(v)
        return result
