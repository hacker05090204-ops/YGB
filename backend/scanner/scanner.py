from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.vuln_detector import VulnerabilityPatternEngine


@dataclass(frozen=True)
class ScannerFinding:
    target: str
    finding_count: int
    top_signal: str | None


def scanner(target: str, text: str) -> ScannerFinding:
    engine = VulnerabilityPatternEngine()
    signals = engine.analyze(text)
    return ScannerFinding(
        target=target,
        finding_count=len(signals),
        top_signal=signals[0].vuln_type if signals else None,
    )
