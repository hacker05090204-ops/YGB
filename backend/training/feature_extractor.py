"""Structured feature extraction for G38 incremental training."""

from __future__ import annotations

import json
import logging
import os
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
VOCAB_PATH = Path("data/vocab/vocab_508.json")
BRIDGE_SAMPLE_PATH = Path("secure_data/bridge_samples.jsonl.gz")


def _tokenize(text: str) -> list[str]:
    return [token.strip(".,:;!?()[]{}<>\"'").lower() for token in text.split() if token.strip(".,:;!?()[]{}<>\"'")]


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


def build_vocabulary(limit: int = 10_000) -> list[str]:
    token_counts: Counter[str] = Counter()
    seen = 0
    for sample_path in RAW_DATA_ROOT.rglob("*.json"):
        if sample_path.name == "dedup_index.json":
            continue
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        token_counts.update(_tokenize(str(payload.get("raw_text", ""))))
        seen += 1
        if seen >= limit:
            break

    if seen == 0 and BRIDGE_SAMPLE_PATH.exists():
        import gzip

        with gzip.open(BRIDGE_SAMPLE_PATH, "rt", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                text = " ".join(
                    str(payload.get(field, ""))
                    for field in ("endpoint", "parameters", "exploit_vector", "impact")
                ).strip()
                token_counts.update(_tokenize(text))
                seen += 1
                if seen >= limit:
                    break

    vocabulary = [token for token, _ in token_counts.most_common(508)]
    while len(vocabulary) < 508:
        vocabulary.append(f"__pad_{len(vocabulary)}")
    _atomic_write_json(VOCAB_PATH, vocabulary[:508])
    return vocabulary[:508]


def load_vocabulary() -> list[str]:
    if VOCAB_PATH.exists():
        payload = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
        return [str(token) for token in payload][:508]
    return build_vocabulary()


def get_text_embedding(text: str) -> torch.Tensor:
    vocabulary = load_vocabulary()
    token_index = {token: index for index, token in enumerate(vocabulary)}
    counts = Counter(_tokenize(text))
    embedding = torch.zeros(508, dtype=torch.float32)
    total_tokens = max(sum(counts.values()), 1)
    for token, count in counts.items():
        index = token_index.get(token)
        if index is not None:
            embedding[index] = float(count) / float(total_tokens)
    return embedding


def extract(sample: IngestedSample) -> torch.Tensor:
    structured = torch.tensor(
        [
            SEVERITY_MAP.get(sample.severity, 0.0),
            1.0 if sample.cve_id else 0.0,
            SOURCE_WEIGHT.get(sample.source, 0.5),
            min(sample.token_count / 512.0, 1.0),
        ],
        dtype=torch.float32,
    )
    text_embedding = get_text_embedding(sample.raw_text)
    return torch.cat([text_embedding, structured], dim=0)


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
