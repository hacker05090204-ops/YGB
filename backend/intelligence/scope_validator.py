from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScopeDecision:
    target: str
    in_scope: bool
    matched_rule: Optional[str]
    confidence: float
    reason: str


class ScopeValidator:
    def validate(self, target: str, scope_rules: list[str]) -> ScopeDecision:
        for rule in scope_rules:
            if rule.startswith("*."):
                domain = rule[2:]
                if target.endswith(f".{domain}") or target == domain:
                    return ScopeDecision(target, True, rule, 0.95, f"Wildcard match: {rule}")
            elif "/" in rule:
                try:
                    network = ipaddress.ip_network(rule, strict=False)
                    if ipaddress.ip_address(target) in network:
                        return ScopeDecision(target, True, rule, 1.0, f"CIDR match: {rule}")
                except ValueError:
                    continue
            elif target == rule or target.endswith(f".{rule}"):
                return ScopeDecision(target, True, rule, 1.0, f"Exact match: {rule}")
        return ScopeDecision(target, False, None, 1.0, "No scope rule matched")

