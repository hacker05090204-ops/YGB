from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from backend.ingest.normalize.canonicalize import CanonicalRecord


_EXPERT_KEYWORDS: Dict[str, Iterable[str]] = {
    "web_vulns": ("web", "http", "browser"),
    "api_testing": ("api", "rest", "http"),
    "mobile_apk": ("mobile", "android", "ios", "apk"),
    "cloud_misconfig": ("cloud", "aws", "gcp", "azure"),
    "blockchain": ("blockchain", "smart contract", "web3"),
    "iot": ("iot", "device", "embedded"),
    "hardware": ("hardware", "chip", "board"),
    "firmware": ("firmware", "bootloader"),
    "ssrf": ("ssrf",),
    "rce": ("rce", "remote code execution"),
    "xss": ("xss", "cross site scripting"),
    "sqli": ("sqli", "sql injection"),
    "auth_bypass": ("auth bypass", "authentication", "authorization"),
    "idor": ("idor", "insecure direct object reference"),
    "graphql_abuse": ("graphql",),
    "rest_attacks": ("rest", "endpoint"),
    "csrf": ("csrf",),
    "file_upload": ("file upload", "multipart"),
    "deserialization": ("deserialize", "pickle", "serialization"),
    "privilege_escalation": ("privilege escalation", "sudo", "admin"),
    "cryptography": ("crypto", "cipher", "signature"),
    "subdomain_takeover": ("subdomain", "dns"),
    "race_condition": ("race", "concurrency"),
}


@dataclass
class RoutingDecision:
    expert_name: str
    route: str
    queue_kind: str
    reasons: List[str] = field(default_factory=list)


def route_record(record: CanonicalRecord) -> RoutingDecision:
    haystack = " ".join(
        [
            record.normalized_text.lower(),
            record.source_name.lower(),
            record.source_type.lower(),
            " ".join(tag.lower() for tag in record.tags),
        ]
    )
    best_expert = "web_vulns"
    best_score = -1
    reasons: List[str] = []
    for expert_name, keywords in _EXPERT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword and keyword in haystack)
        if score > best_score:
            best_score = score
            best_expert = expert_name
            reasons = [keyword for keyword in keywords if keyword and keyword in haystack]
    return RoutingDecision(
        expert_name=best_expert,
        route="trainer",
        queue_kind="train_expert",
        reasons=reasons or ["default_web_routing"],
    )
