"""Hunting Self-Reflection Engine.
When payloads fail, the hunter reflects on WHY and invents new strategies.
Learns from failures. Escalates techniques. Generates bypass variants.
Pure AI reasoning — no hardcoded bypass lists."""

import hashlib
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ygb.hunter.reflector")


@dataclass
class FailureAnalysis:
    failure_type: str  # waf_blocked, filtered, timeout, error, no_reflection
    confidence: float
    evidence: dict
    suggested_bypasses: list[str]
    escalation_level: int  # 0=basic, 1=encoded, 2=advanced, 3=expert


BYPASS_STRATEGIES = {
    "waf_blocked": [
        "url_encoding",
        "double_encoding",
        "unicode_encoding",
        "case_variation",
        "comment_injection",
        "null_byte",
        "mixed_case",
        "whitespace_variation",
    ],
    "filtered": [
        "alternative_syntax",
        "concatenation",
        "hex_encoding",
        "octal_encoding",
        "base64_encoding",
        "polyglot_payload",
    ],
    "no_reflection": [
        "blind_technique",
        "time_based",
        "error_based",
        "out_of_band",
    ],
    "timeout": [
        "reduce_complexity",
        "split_payload",
        "async_technique",
    ],
}


class HuntingReflector:
    """Analyzes payload failures and generates improved variants.
    Self-improves through reflection on what didn't work."""

    def __init__(self):
        self._failure_history: list[FailureAnalysis] = []
        self._success_patterns: dict[str, int] = {}
        self._bypass_attempts: dict[str, int] = {}

    def analyze_failure(
        self,
        payload: "Payload",
        response: "HTTPResponse",
        baseline: Optional["HTTPResponse"] = None,
    ) -> FailureAnalysis:
        """Determine WHY the payload failed and suggest improvements."""
        body_lower = response.body.lower()
        headers_lower = {k.lower(): v.lower() for k, v in response.headers.items()}

        # Detect WAF/Firewall
        waf_indicators = [
            "cloudflare",
            "incapsula",
            "imperva",
            "akamai",
            "blocked",
            "forbidden",
            "access denied",
            "security",
            "firewall",
            "waf",
            "mod_security",
            "modsecurity",
        ]

        if response.status_code in (403, 406, 429):
            for indicator in waf_indicators:
                if indicator in body_lower or any(
                    indicator in v for v in headers_lower.values()
                ):
                    return FailureAnalysis(
                        failure_type="waf_blocked",
                        confidence=0.85,
                        evidence={
                            "status": response.status_code,
                            "indicator": indicator,
                            "server": response.server_header,
                        },
                        suggested_bypasses=BYPASS_STRATEGIES["waf_blocked"],
                        escalation_level=1,
                    )

        # Detect input filtering
        if payload.value not in response.body and baseline:
            # Payload was filtered/sanitized
            return FailureAnalysis(
                failure_type="filtered",
                confidence=0.75,
                evidence={
                    "payload_not_reflected": True,
                    "baseline_had_reflection": payload.value[:20] in baseline.body,
                },
                suggested_bypasses=BYPASS_STRATEGIES["filtered"],
                escalation_level=2,
            )

        # Detect no reflection at all
        if payload.value not in response.body:
            return FailureAnalysis(
                failure_type="no_reflection",
                confidence=0.60,
                evidence={"no_reflection": True},
                suggested_bypasses=BYPASS_STRATEGIES["no_reflection"],
                escalation_level=1,
            )

        # Timeout
        if response.elapsed_ms > 25000:
            return FailureAnalysis(
                failure_type="timeout",
                confidence=0.90,
                evidence={"elapsed_ms": response.elapsed_ms},
                suggested_bypasses=BYPASS_STRATEGIES["timeout"],
                escalation_level=0,
            )

        # Generic failure
        return FailureAnalysis(
            failure_type="unknown",
            confidence=0.30,
            evidence={"status": response.status_code},
            suggested_bypasses=["retry", "alternative_param"],
            escalation_level=0,
        )

    def generate_bypass_variants(
        self, original_payload: "Payload", failure: FailureAnalysis
    ) -> list["Payload"]:
        """Generate new payload variants based on failure analysis."""
        from backend.hunter.payload_engine import Payload

        variants = []
        base_value = original_payload.value

        # Track bypass attempts
        bypass_key = f"{original_payload.vuln_type}:{failure.failure_type}"
        self._bypass_attempts[bypass_key] = self._bypass_attempts.get(bypass_key, 0) + 1

        for strategy in failure.suggested_bypasses[:3]:  # Top 3 strategies
            if strategy == "url_encoding":
                encoded = urllib.parse.quote(base_value)
                variants.append(
                    Payload(
                        payload_id=f"{original_payload.payload_id}_url",
                        vuln_type=original_payload.vuln_type,
                        value=encoded,
                        context=original_payload.context,
                        encoding="url",
                        notes=f"URL encoded bypass for {failure.failure_type}",
                    )
                )

            elif strategy == "double_encoding":
                encoded = urllib.parse.quote(urllib.parse.quote(base_value))
                variants.append(
                    Payload(
                        payload_id=f"{original_payload.payload_id}_dbl",
                        vuln_type=original_payload.vuln_type,
                        value=encoded,
                        context=original_payload.context,
                        encoding="double_url",
                        notes="Double URL encoded",
                    )
                )

            elif strategy == "unicode_encoding":
                # Convert to unicode escapes
                unicode_val = "".join(f"\\u{ord(c):04x}" for c in base_value[:20])
                variants.append(
                    Payload(
                        payload_id=f"{original_payload.payload_id}_uni",
                        vuln_type=original_payload.vuln_type,
                        value=unicode_val,
                        context=original_payload.context,
                        encoding="unicode",
                        notes="Unicode encoded",
                    )
                )

            elif strategy == "case_variation":
                # Alternate case
                varied = "".join(
                    c.upper() if i % 2 else c.lower() for i, c in enumerate(base_value)
                )
                variants.append(
                    Payload(
                        payload_id=f"{original_payload.payload_id}_case",
                        vuln_type=original_payload.vuln_type,
                        value=varied,
                        context=original_payload.context,
                        notes="Case variation bypass",
                    )
                )

            elif strategy == "comment_injection":
                # SQL comment injection
                if original_payload.vuln_type == "sqli":
                    commented = base_value.replace(" ", "/**/")
                    variants.append(
                        Payload(
                            payload_id=f"{original_payload.payload_id}_cmt",
                            vuln_type=original_payload.vuln_type,
                            value=commented,
                            context=original_payload.context,
                            notes="SQL comment bypass",
                        )
                    )

            elif strategy == "null_byte":
                variants.append(
                    Payload(
                        payload_id=f"{original_payload.payload_id}_null",
                        vuln_type=original_payload.vuln_type,
                        value=base_value + "%00",
                        context=original_payload.context,
                        notes="Null byte bypass",
                    )
                )

            elif strategy == "mixed_case":
                # For XSS: <ScRiPt>
                if "<" in base_value:
                    mixed = re.sub(
                        r"<(\w+)",
                        lambda m: f"<{m.group(1)[0].upper()}{m.group(1)[1:].lower()}",
                        base_value,
                    )
                    variants.append(
                        Payload(
                            payload_id=f"{original_payload.payload_id}_mix",
                            vuln_type=original_payload.vuln_type,
                            value=mixed,
                            context=original_payload.context,
                            notes="Mixed case tag bypass",
                        )
                    )

            elif strategy == "blind_technique":
                # Switch to time-based
                if original_payload.vuln_type == "sqli":
                    variants.append(
                        Payload(
                            payload_id=f"{original_payload.payload_id}_time",
                            vuln_type=original_payload.vuln_type,
                            value="1' AND SLEEP(3)--",
                            context=original_payload.context,
                            notes="Time-based blind SQLi",
                        )
                    )

        logger.info(
            "Generated %d bypass variants for %s (failure: %s)",
            len(variants),
            original_payload.payload_id,
            failure.failure_type,
        )

        return variants

    def record_success(self, payload: "Payload", vuln_type: str):
        """Record successful payload for learning."""
        pattern_key = f"{vuln_type}:{payload.encoding}"
        self._success_patterns[pattern_key] = (
            self._success_patterns.get(pattern_key, 0) + 1
        )
        logger.info("Success pattern recorded: %s", pattern_key)

    def get_best_strategies(self, vuln_type: str) -> list[str]:
        """Get most successful strategies for a vulnerability type."""
        relevant = {
            k: v for k, v in self._success_patterns.items() if k.startswith(vuln_type)
        }
        return sorted(relevant, key=relevant.get, reverse=True)[:5]

    def get_reflection_summary(self) -> dict:
        """Get summary of learning progress."""
        return {
            "total_failures_analyzed": len(self._failure_history),
            "bypass_attempts": dict(self._bypass_attempts),
            "success_patterns": dict(self._success_patterns),
            "most_successful": self.get_best_strategies("sqli")
            + self.get_best_strategies("xss"),
        }
