from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from backend.ingestion.parallel_autograbber import route_vulnerability_text_to_expert


@dataclass(frozen=True)
class ExpertAssignment:
    expert_id: int
    expert_label: str
    reasons: tuple[str, ...]
    sample_identifier: str


class ExpertDistributor:
    """Deterministic routing of accepted ingestion samples to expert lanes."""

    def assign(self, sample: Mapping[str, object]) -> ExpertAssignment:
        text = " ".join(
            part.strip()
            for part in (
                str(sample.get("title") or ""),
                str(sample.get("description") or sample.get("raw_text") or ""),
            )
            if part.strip()
        )
        raw_tags = sample.get("tags") or ()
        tags: Sequence[str] = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, (list, tuple, set)) else ()
        route = route_vulnerability_text_to_expert(
            text,
            tags=tags,
            source=str(sample.get("source") or ""),
        )
        sample_identifier = str(sample.get("cve_id") or sample.get("id") or "")
        return ExpertAssignment(
            expert_id=int(route.expert_id),
            expert_label=str(route.expert_label),
            reasons=tuple(route.reasons),
            sample_identifier=sample_identifier,
        )

    def distribute(self, samples: Iterable[Mapping[str, object]]) -> tuple[ExpertAssignment, ...]:
        return tuple(self.assign(sample) for sample in samples)


__all__ = ["ExpertAssignment", "ExpertDistributor"]
