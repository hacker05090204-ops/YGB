from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np


logger = logging.getLogger("ygb.intelligence.vulnerability_detector")


@dataclass(frozen=True)
class VulnSignal:
    vuln_type: str
    confidence: float
    evidence: list[str]
    severity_predicted: str
    cve_id: Optional[str]


class VulnerabilityPatternEngine:
    """Passive vulnerability-pattern detection using local heuristics + local model inference."""

    PATTERNS = {
        "rce": {
            "keywords": [
                "remote code execution",
                "rce",
                "arbitrary code",
                "command injection",
                "os command",
                "shell injection",
                "code execution",
                "execute arbitrary",
            ],
            "severity_floor": "HIGH",
        },
        "sqli": {
            "keywords": [
                "sql injection",
                "sqli",
                "sql query",
                "database injection",
                "blind sql",
                "union select",
                "boolean-based",
                "time-based blind",
            ],
            "severity_floor": "HIGH",
        },
        "xss": {
            "keywords": [
                "cross-site scripting",
                "xss",
                "script injection",
                "reflected xss",
                "stored xss",
                "dom-based xss",
                "javascript injection",
            ],
            "severity_floor": "MEDIUM",
        },
        "ssrf": {
            "keywords": [
                "server-side request forgery",
                "ssrf",
                "internal network",
                "metadata endpoint",
                "cloud metadata",
                "169.254",
                "imdsv1",
            ],
            "severity_floor": "HIGH",
        },
        "idor": {
            "keywords": [
                "insecure direct object",
                "idor",
                "object reference",
                "access control",
                "unauthorized access",
                "privilege escalation",
            ],
            "severity_floor": "HIGH",
        },
        "auth_bypass": {
            "keywords": [
                "authentication bypass",
                "auth bypass",
                "unauthenticated",
                "jwt bypass",
                "token forgery",
                "session fixation",
            ],
            "severity_floor": "CRITICAL",
        },
        "path_traversal": {
            "keywords": [
                "path traversal",
                "directory traversal",
                "../",
                "file inclusion",
                "lfi",
                "rfi",
                "local file",
                "remote file",
            ],
            "severity_floor": "HIGH",
        },
        "xxe": {
            "keywords": [
                "xml external entity",
                "xxe",
                "external entity",
                "dtd injection",
            ],
            "severity_floor": "HIGH",
        },
        "deserialization": {
            "keywords": [
                "insecure deserialization",
                "deserialization",
                "pickle",
                "java deserialization",
            ],
            "severity_floor": "CRITICAL",
        },
        "ssti": {
            "keywords": [
                "template injection",
                "ssti",
                "server-side template",
                "jinja2",
                "twig",
            ],
            "severity_floor": "HIGH",
        },
        "csrf": {
            "keywords": [
                "cross-site request forgery",
                "csrf",
                "cross site request",
            ],
            "severity_floor": "MEDIUM",
        },
        "information_disclosure": {
            "keywords": [
                "information disclosure",
                "sensitive data",
                "data exposure",
                "stack trace",
                "debug information",
                "configuration disclosure",
            ],
            "severity_floor": "MEDIUM",
        },
        "dos": {
            "keywords": [
                "denial of service",
                "dos",
                "resource exhaustion",
                "memory exhaustion",
                "infinite loop",
                "cpu exhaustion",
            ],
            "severity_floor": "MEDIUM",
        },
        "privilege_escalation": {
            "keywords": [
                "privilege escalation",
                "privesc",
                "root access",
                "admin access",
                "sudo",
                "setuid",
            ],
            "severity_floor": "HIGH",
        },
        "rce_memory": {
            "keywords": [
                "buffer overflow",
                "heap overflow",
                "use after free",
                "uaf",
                "memory corruption",
                "stack smashing",
                "format string",
            ],
            "severity_floor": "CRITICAL",
        },
    }

    def __init__(self, model=None):
        self._model = model
        self._compiled_patterns = {
            vuln_type: re.compile(
                "|".join(re.escape(keyword) for keyword in data["keywords"]),
                re.IGNORECASE,
            )
            for vuln_type, data in self.PATTERNS.items()
        }

    def analyze(self, description: str, title: str = "", cvss: float | None = None) -> list[VulnSignal]:
        text = f"{title} {description}".lower()
        detected: list[VulnSignal] = []

        for vuln_type, data in self.PATTERNS.items():
            matches = self._compiled_patterns[vuln_type].findall(text)
            if not matches:
                continue
            base_conf = min(0.9, 0.3 + len(set(matches)) * 0.15)
            if cvss is not None and cvss >= 9.0 and data["severity_floor"] == "CRITICAL":
                base_conf = min(0.95, base_conf + 0.1)
            detected.append(
                VulnSignal(
                    vuln_type=vuln_type,
                    confidence=round(base_conf, 3),
                    evidence=list(dict.fromkeys(matches))[:5],
                    severity_predicted=data["severity_floor"],
                    cve_id=None,
                )
            )

        detected.sort(key=lambda item: item.confidence, reverse=True)
        return detected

    def classify_with_model(self, description: str) -> str:
        if self._model is None:
            return "MEDIUM"
        from backend.training.feature_extractor import CVEFeatureEngineer

        signals = CVEFeatureEngineer.extract_signals(description)
        features = np.array(list(signals.values()) + [0.0] * 256, dtype=np.float32)
        x = np.asarray(features[:267], dtype=np.float32)
        import torch

        tensor = torch.from_numpy(x).unsqueeze(0)
        try:
            parameter = next(self._model.parameters())
            tensor = tensor.to(device=parameter.device, dtype=parameter.dtype)
        except StopIteration:
            pass
        with torch.no_grad():
            output = self._model(tensor)
            cls = int(output.argmax().item())
        return ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"][cls]

