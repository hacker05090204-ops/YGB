"""Structured feature extraction for G38 incremental training."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from pathlib import Path

import torch

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.models import IngestedSample

logger = logging.getLogger("ygb.training.feature_extractor")

SEVERITY_MAP = {
    "CRITICAL": 1.0,
    "HIGH": 0.75,
    "MEDIUM": 0.5,
    "LOW": 0.25,
    "INFO": 0.1,
    "INFORMATIONAL": 0.1,
    "UNKNOWN": 0.0,
}

SOURCE_WEIGHT = {
    "hackerone": 1.0,
    "cisa_kev": 1.0,
    "nvd": 0.9,
    "github_advisory": 0.85,
    "exploitdb": 0.8,
    "bugcrowd": 0.75,
}

RAW_DATA_ROOT = Path("data/raw")
VOCAB_ROOT = Path("data/vocab")
VOCAB_PATH = VOCAB_ROOT / "vocab_508.json"
CVE_VOCAB_PATH = VOCAB_ROOT / "vocab_256.json"
BRIDGE_SAMPLE_PATH = Path("secure_data/bridge_samples.jsonl.gz")
LEGACY_VOCAB_SIZE = 508


def _tokenize(text: str) -> list[str]:
    return [
        token.strip(".,:;!?()[]{}<>\"'").lower()
        for token in text.split()
        if token.strip(".,:;!?()[]{}<>\"'")
    ]


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _resolve_vocab_path(vocabulary_size: int, vocab_path: Path | None = None) -> Path:
    if vocab_path is not None:
        return Path(vocab_path)
    if int(vocabulary_size) == LEGACY_VOCAB_SIZE:
        return VOCAB_PATH
    return VOCAB_ROOT / f"vocab_{int(vocabulary_size)}.json"


def _collect_token_counts(
    *,
    raw_data_root: Path,
    bridge_sample_path: Path,
    limit: int,
    seed_text: str = "",
) -> Counter[str]:
    token_counts: Counter[str] = Counter()
    seen = 0

    if raw_data_root.exists():
        for sample_path in raw_data_root.rglob("*.json"):
            if sample_path.name == "dedup_index.json":
                continue
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
            token_counts.update(_tokenize(str(payload.get("raw_text", ""))))
            seen += 1
            if seen >= limit:
                return token_counts

    if seen == 0 and bridge_sample_path.exists():
        import gzip

        with gzip.open(bridge_sample_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                text = " ".join(
                    str(payload.get(field, ""))
                    for field in ("endpoint", "parameters", "exploit_vector", "impact")
                ).strip()
                token_counts.update(_tokenize(text))
                seen += 1
                if seen >= limit:
                    return token_counts

    if seen == 0 and seed_text.strip():
        token_counts.update(_tokenize(seed_text))

    return token_counts


def build_vocabulary(
    limit: int = 10_000,
    *,
    vocabulary_size: int = LEGACY_VOCAB_SIZE,
    raw_data_root: Path | None = None,
    bridge_sample_path: Path | None = None,
    vocab_path: Path | None = None,
    seed_text: str = "",
) -> list[str]:
    token_counts = _collect_token_counts(
        raw_data_root=Path(raw_data_root or RAW_DATA_ROOT),
        bridge_sample_path=Path(bridge_sample_path or BRIDGE_SAMPLE_PATH),
        limit=limit,
        seed_text=seed_text,
    )
    target_size = max(int(vocabulary_size), 1)
    vocabulary = [token for token, _ in token_counts.most_common(target_size)]
    while len(vocabulary) < target_size:
        vocabulary.append(f"__pad_{len(vocabulary)}")
    resolved_path = _resolve_vocab_path(target_size, vocab_path=vocab_path)
    _atomic_write_json(resolved_path, vocabulary[:target_size])
    return vocabulary[:target_size]


def load_vocabulary(
    *,
    vocabulary_size: int = LEGACY_VOCAB_SIZE,
    vocab_path: Path | None = None,
    raw_data_root: Path | None = None,
    bridge_sample_path: Path | None = None,
    seed_text: str = "",
) -> list[str]:
    target_size = max(int(vocabulary_size), 1)
    resolved_path = _resolve_vocab_path(target_size, vocab_path=vocab_path)
    if resolved_path.exists():
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        vocabulary = [str(token) for token in payload][:target_size]
        while len(vocabulary) < target_size:
            vocabulary.append(f"__pad_{len(vocabulary)}")
        return vocabulary[:target_size]
    return build_vocabulary(
        limit=10_000,
        vocabulary_size=target_size,
        raw_data_root=raw_data_root,
        bridge_sample_path=bridge_sample_path,
        vocab_path=resolved_path,
        seed_text=seed_text,
    )


def get_text_embedding(
    text: str,
    *,
    vocabulary_size: int = LEGACY_VOCAB_SIZE,
    vocab_path: Path | None = None,
    raw_data_root: Path | None = None,
    bridge_sample_path: Path | None = None,
) -> torch.Tensor:
    vocabulary = load_vocabulary(
        vocabulary_size=vocabulary_size,
        vocab_path=vocab_path,
        raw_data_root=raw_data_root,
        bridge_sample_path=bridge_sample_path,
        seed_text=text,
    )
    token_index = {token: index for index, token in enumerate(vocabulary)}
    counts = Counter(_tokenize(text))
    embedding = torch.zeros(len(vocabulary), dtype=torch.float32)
    total_tokens = max(sum(counts.values()), 1)
    for token, count in counts.items():
        index = token_index.get(token)
        if index is not None:
            embedding[index] = float(count) / float(total_tokens)
    return embedding


class CVEFeatureEngineer:
    """Real-text CVE feature engineer with 256 base features + 11 domain signals."""

    BASE_FEATURE_DIM = 256
    DOMAIN_SIGNAL_NAMES = (
        "critical_severity_cue",
        "high_severity_cue",
        "medium_severity_cue",
        "low_or_info_severity_cue",
        "cvss_score_normalized",
        "exploit_cue",
        "rce_cue",
        "memory_corruption_cue",
        "auth_or_privilege_cue",
        "network_remote_cue",
        "known_exploited_or_patch_urgency_cue",
    )
    DOMAIN_SIGNAL_DIM = len(DOMAIN_SIGNAL_NAMES)
    FEATURE_DIM = BASE_FEATURE_DIM + DOMAIN_SIGNAL_DIM
    CVSS_SCORE_RE = re.compile(
        r"\bcvss(?:\s*v\d(?:\.\d)?)?\D{0,6}(?P<score>10(?:\.0)?|[0-9](?:\.[0-9])?)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        raw_data_root: Path | str | None = None,
        bridge_sample_path: Path | str | None = None,
        vocab_path: Path | str | None = None,
    ) -> None:
        self.raw_data_root = Path(raw_data_root or RAW_DATA_ROOT)
        self.bridge_sample_path = Path(bridge_sample_path or BRIDGE_SAMPLE_PATH)
        self.vocab_path = Path(vocab_path or CVE_VOCAB_PATH)
        self._vocabulary: list[str] | None = None
        self._token_index: dict[str, int] | None = None

    @property
    def output_dim(self) -> int:
        return self.FEATURE_DIM

    def signal_index(self, signal_name: str) -> int:
        return self.BASE_FEATURE_DIM + self.DOMAIN_SIGNAL_NAMES.index(signal_name)

    @staticmethod
    def _compose_analysis_text(sample: IngestedSample) -> str:
        real_fields = [
            str(sample.raw_text or "").strip(),
            str(sample.severity or "").strip(),
            str(sample.cve_id or "").strip(),
            str(sample.source or "").strip(),
            " ".join(str(tag).strip() for tag in sample.tags if str(tag).strip()),
        ]
        return " ".join(part for part in real_fields if part).strip().lower()

    def load_vocabulary(self, *, seed_text: str = "") -> list[str]:
        if self._vocabulary is None:
            self._vocabulary = load_vocabulary(
                vocabulary_size=self.BASE_FEATURE_DIM,
                vocab_path=self.vocab_path,
                raw_data_root=self.raw_data_root,
                bridge_sample_path=self.bridge_sample_path,
                seed_text=seed_text,
            )
            self._token_index = {
                token: index for index, token in enumerate(self._vocabulary)
            }
        return list(self._vocabulary)

    def _base_embedding(self, text: str) -> torch.Tensor:
        vocabulary = self.load_vocabulary(seed_text=text)
        token_index = self._token_index or {
            token: index for index, token in enumerate(vocabulary)
        }
        counts = Counter(_tokenize(text))
        embedding = torch.zeros(self.BASE_FEATURE_DIM, dtype=torch.float32)
        total_tokens = max(sum(counts.values()), 1)
        for token, count in counts.items():
            index = token_index.get(token)
            if index is not None and index < self.BASE_FEATURE_DIM:
                embedding[index] = float(count) / float(total_tokens)
        return embedding

    @staticmethod
    def _keyword_signal(text: str, keywords: tuple[str, ...]) -> float:
        return 1.0 if any(keyword in text for keyword in keywords) else 0.0

    def _domain_signals(self, sample: IngestedSample, text: str) -> torch.Tensor:
        severity = str(sample.severity or "").strip().upper()
        cvss_match = self.CVSS_SCORE_RE.search(text)
        cvss_score = (
            min(float(cvss_match.group("score")) / 10.0, 1.0)
            if cvss_match is not None
            else 0.0
        )
        signals = torch.tensor(
            [
                1.0 if severity == "CRITICAL" or "critical" in text else 0.0,
                1.0 if severity == "HIGH" or "high severity" in text else 0.0,
                1.0 if severity == "MEDIUM" or "medium severity" in text else 0.0,
                1.0 if severity in {"LOW", "INFO", "INFORMATIONAL"} or "low severity" in text or "informational" in text else 0.0,
                cvss_score,
                self._keyword_signal(
                    text,
                    (
                        "exploit",
                        "proof of concept",
                        "poc",
                        "weaponized",
                        "metasploit",
                        "exploitdb",
                        "actively exploited",
                    ),
                ),
                self._keyword_signal(
                    text,
                    (
                        "remote code execution",
                        "rce",
                        "code execution",
                        "command injection",
                        "deserialization",
                    ),
                ),
                self._keyword_signal(
                    text,
                    (
                        "buffer overflow",
                        "use-after-free",
                        "out-of-bounds",
                        "memory corruption",
                        "heap overflow",
                        "stack overflow",
                    ),
                ),
                self._keyword_signal(
                    text,
                    (
                        "authentication bypass",
                        "auth bypass",
                        "privilege escalation",
                        "local privilege escalation",
                        "sandbox escape",
                    ),
                ),
                self._keyword_signal(
                    text,
                    (
                        "remote",
                        "unauthenticated",
                        "network",
                        "internet-facing",
                        "public endpoint",
                    ),
                ),
                self._keyword_signal(
                    text,
                    (
                        "in the wild",
                        "kev",
                        "known exploited",
                        "actively exploited",
                        "patch immediately",
                        "emergency update",
                    ),
                ),
            ],
            dtype=torch.float32,
        )
        return signals

    def extract(self, sample: IngestedSample) -> torch.Tensor:
        analysis_text = self._compose_analysis_text(sample)
        base_embedding = self._base_embedding(analysis_text)
        domain_signals = self._domain_signals(sample, analysis_text)
        return torch.cat([base_embedding, domain_signals], dim=0)


def extract(sample: IngestedSample) -> torch.Tensor:
    """Legacy 512-dimensional extractor retained for non-Phase-8A callers."""

    structured = torch.tensor(
        [
            SEVERITY_MAP.get(str(sample.severity or "UNKNOWN").upper(), 0.0),
            1.0 if sample.cve_id else 0.0,
            SOURCE_WEIGHT.get(sample.source, 0.5),
            min(sample.token_count / 512.0, 1.0),
        ],
        dtype=torch.float32,
    )
    text_embedding = get_text_embedding(sample.raw_text)
    return torch.cat([text_embedding, structured], dim=0)


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
