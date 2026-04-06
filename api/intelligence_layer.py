"""Governance-safe intelligence layer built on local historical artifacts."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import importlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from impl_v1.phase49.governors.g38_self_trained_model import (
    can_ai_execute,
    can_ai_verify_bug,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_CHECKPOINT_PATH = PROJECT_ROOT / "checkpoints" / "g38_model_checkpoint.safetensors"
THRESHOLD_PATH = PROJECT_ROOT / "checkpoints" / "optimal_threshold.json"
FEATURE_EXTRACTOR_PATH = PROJECT_ROOT / "backend" / "training" / "feature_extractor.py"
VOCAB_PATH = PROJECT_ROOT / "data" / "vocab" / "vocab_508.json"
BRIDGE_SAMPLE_PATH = PROJECT_ROOT / "secure_data" / "bridge_samples.jsonl.gz"
LAYER_NORM_EPSILON = 1e-5

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

FOCUS_KEYWORDS = {
    "admin": "Administrative surfaces and privilege separation",
    "api": "API authorization and object-level access control",
    "auth": "Authentication, session, and login flows",
    "command": "Command execution surfaces and unsafe shell invocation",
    "cookie": "Cookie flags and session lifecycle",
    "cors": "CORS policy and cross-origin trust boundaries",
    "csp": "Content Security Policy and script execution controls",
    "csrf": "CSRF protection on state-changing requests",
    "file": "File handling, download, and path validation",
    "graphql": "GraphQL introspection and authorization",
    "idor": "Authorization checks and object-level access control",
    "injection": "Injection surfaces and untrusted input handling",
    "jwt": "Token issuance, JWT handling, and session binding",
    "login": "Authentication, session, and login flows",
    "oauth": "OAuth redirect and state handling",
    "password": "Password reset and credential handling",
    "redirect": "Open redirect and URL validation",
    "session": "Authentication, session, and login flows",
    "sql": "SQL query construction and parameter handling",
    "ssrf": "Server-side request handling and outbound fetch controls",
    "template": "Template rendering and server-side injection surfaces",
    "token": "Token issuance, JWT handling, and session binding",
    "upload": "File upload validation and storage isolation",
    "xss": "Output encoding and client-side injection sinks",
}


def _guard_blocks_execution() -> bool:
    result = can_ai_execute()
    return bool(result[0] if isinstance(result, tuple) else result)


def _raise_if_execution_guarded(operation: str) -> None:
    if _guard_blocks_execution():
        raise RuntimeError(f"GUARD: AI cannot execute during {operation}")


def _verify_guard(name: str, fn) -> None:
    result = fn()
    if bool(result[0] if isinstance(result, tuple) else result):
        raise RuntimeError(f"GUARD: {name} blocked analysis")


@dataclass(frozen=True)
class AnalysisResult:
    confidence: float
    pattern_matches: List[str]
    suggested_focus_areas: List[str]
    requires_human_verification: bool
    model_version: str
    analysis_timestamp: datetime


@dataclass(frozen=True)
class _TensorData:
    shape: tuple[int, ...]
    values: array


class _FeatureExtractorCompat:
    """Pure-Python compatibility path mirroring backend.training.feature_extractor."""

    def __init__(self, vocabulary: Sequence[str]):
        self.vocabulary = [str(token) for token in vocabulary][:508]
        self.token_index = {token: idx for idx, token in enumerate(self.vocabulary)}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [
            token.strip(".,:;!?()[]{}<>\"'").lower()
            for token in str(text).split()
            if token.strip(".,:;!?()[]{}<>\"'")
        ]

    def embed_text(self, text: str) -> List[float]:
        counts: Dict[str, int] = {}
        for token in self._tokenize(text):
            counts[token] = counts.get(token, 0) + 1
        total_tokens = max(sum(counts.values()), 1)
        embedding = [0.0] * 508
        for token, count in counts.items():
            index = self.token_index.get(token)
            if index is not None:
                embedding[index] = float(count) / float(total_tokens)
        return embedding

    def embed_sparse(self, text: str) -> Dict[int, float]:
        dense = self.embed_text(text)
        return {index: value for index, value in enumerate(dense) if value}

    def extract_features(
        self,
        *,
        raw_text: str,
        severity: str = "UNKNOWN",
        source: str = "human",
        cve_id: str = "",
    ) -> List[float]:
        structured = [
            SEVERITY_MAP.get(str(severity).upper(), 0.0),
            1.0 if cve_id else 0.0,
            SOURCE_WEIGHT.get(str(source).lower(), 0.5),
            min(len(str(raw_text).split()) / 512.0, 1.0),
        ]
        return self.embed_text(raw_text) + structured


class IntelligenceLayer:
    def __init__(self):
        self._model_metadata, self._model_state = self._load_model_checkpoint()
        self._optimal_threshold = self._load_optimal_threshold()
        self._feature_extractor = self._load_feature_extractor()
        self._bridge_samples: List[Dict[str, Any]] | None = None
        self._fallback_model_active = bool(self._model_metadata.get("fallback_model"))
        tensor_hash = str(self._model_metadata.get("tensor_hash", "unknown"))[:8]
        epoch = str(self._model_metadata.get("epoch_number", "unknown"))
        self._model_version = (
            str(self._model_metadata.get("model_version", "g38-keyword-fallback-missing-checkpoint"))
            if self._fallback_model_active
            else f"g38-safetensors-epoch{epoch}-{tensor_hash}"
        )

    @staticmethod
    def _load_missing_checkpoint_fallback() -> tuple[Dict[str, Any], Dict[str, _TensorData]]:
        return {
            "fallback_model": True,
            "fallback_reason": "missing_checkpoint",
            "epoch_number": "missing",
            "tensor_hash": "fallback",
            "model_version": "g38-keyword-fallback-missing-checkpoint",
            "checkpoint_path": str(MODEL_CHECKPOINT_PATH),
        }, {}

    def _load_model_checkpoint(self) -> tuple[Dict[str, Any], Dict[str, _TensorData]]:
        _raise_if_execution_guarded("model checkpoint load")
        if not MODEL_CHECKPOINT_PATH.exists():
            return self._load_missing_checkpoint_fallback()
        try:
            from training.safetensors_io import load_safetensors

            raw_tensors = load_safetensors(str(MODEL_CHECKPOINT_PATH), device="cpu")
            metadata = self._read_safetensors_metadata(MODEL_CHECKPOINT_PATH)
            return metadata, {
                name: self._coerce_loaded_tensor(tensor)
                for name, tensor in raw_tensors.items()
            }
        except FileNotFoundError:
            return self._load_missing_checkpoint_fallback()
        except Exception:
            try:
                return self._load_safetensors_fallback(MODEL_CHECKPOINT_PATH)
            except FileNotFoundError:
                return self._load_missing_checkpoint_fallback()

    def _load_optimal_threshold(self) -> float:
        _raise_if_execution_guarded("threshold load")
        payload = json.loads(THRESHOLD_PATH.read_text(encoding="utf-8"))
        return float(payload.get("optimal_threshold", 0.5))

    def _load_feature_extractor(self) -> _FeatureExtractorCompat:
        _raise_if_execution_guarded("feature extractor load")
        try:
            module = importlib.import_module("backend.training.feature_extractor")
            vocabulary = module.load_vocabulary()
        except Exception:
            vocabulary = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
        return _FeatureExtractorCompat(vocabulary)

    @staticmethod
    def _read_safetensors_metadata(path: Path) -> Dict[str, Any]:
        with path.open("rb") as handle:
            header_len = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_len).decode("utf-8"))
        metadata = header.get("__metadata__", {})
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _coerce_loaded_tensor(tensor: Any) -> _TensorData:
        shape = tuple(int(dim) for dim in getattr(tensor, "shape", ()))
        if hasattr(tensor, "detach"):
            tensor = tensor.detach()
        if hasattr(tensor, "cpu"):
            tensor = tensor.cpu()
        if hasattr(tensor, "tolist"):
            nested = tensor.tolist()
            values = array("f")
            if shape and len(shape) == 2:
                for row in nested:
                    values.extend(float(value) for value in row)
            else:
                values.extend(float(value) for value in nested)
            return _TensorData(shape=shape, values=values)
        raise RuntimeError("Unsupported tensor type returned by checkpoint loader")

    @staticmethod
    def _load_safetensors_fallback(path: Path) -> tuple[Dict[str, Any], Dict[str, _TensorData]]:
        with path.open("rb") as handle:
            header_len = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_len).decode("utf-8"))
            data = handle.read()

        metadata = header.get("__metadata__", {})
        tensors: Dict[str, _TensorData] = {}
        for name, entry in header.items():
            if name == "__metadata__":
                continue
            if entry.get("dtype") != "F32":
                raise RuntimeError(f"Unsupported tensor dtype for {name}: {entry.get('dtype')}")
            start, end = entry["data_offsets"]
            values = array("f")
            values.frombytes(data[start:end])
            tensors[name] = _TensorData(
                shape=tuple(int(dim) for dim in entry.get("shape", [])),
                values=values,
            )
        return dict(metadata) if isinstance(metadata, dict) else {}, tensors

    @staticmethod
    def _combine_description(description: str, technology_stack: Sequence[str], scope: str) -> str:
        parts = [str(description or "").strip()]
        stack = ", ".join(str(item).strip() for item in technology_stack if str(item).strip())
        if stack:
            parts.append(f"Technology stack: {stack}")
        if scope:
            parts.append(f"Scope: {scope}")
        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _gelu(value: float) -> float:
        return 0.5 * value * (1.0 + math.erf(value / math.sqrt(2.0)))

    @staticmethod
    def _softmax(values: Sequence[float]) -> List[float]:
        max_value = max(values)
        exps = [math.exp(value - max_value) for value in values]
        total = sum(exps) or 1.0
        return [value / total for value in exps]

    @staticmethod
    def _layer_norm(values: Sequence[float], weight: _TensorData, bias: _TensorData) -> List[float]:
        mean = sum(values) / max(len(values), 1)
        variance = sum((value - mean) ** 2 for value in values) / max(len(values), 1)
        denom = math.sqrt(variance + LAYER_NORM_EPSILON)
        return [
            ((value - mean) / denom) * weight.values[index] + bias.values[index]
            for index, value in enumerate(values)
        ]

    @staticmethod
    def _linear(values: Sequence[float], weight: _TensorData, bias: _TensorData) -> List[float]:
        rows, cols = weight.shape
        output: List[float] = []
        flat = weight.values
        for row in range(rows):
            total = float(bias.values[row])
            row_offset = row * cols
            for col in range(cols):
                total += flat[row_offset + col] * values[col]
            output.append(total)
        return output

    def _residual_block(self, values: Sequence[float], prefix: str) -> List[float]:
        linear = self._linear(
            values,
            self._model_state[f"{prefix}.linear.weight"],
            self._model_state[f"{prefix}.linear.bias"],
        )
        normalized = self._layer_norm(
            linear,
            self._model_state[f"{prefix}.norm.weight"],
            self._model_state[f"{prefix}.norm.bias"],
        )
        activated = [self._gelu(value) for value in normalized]
        return [base + residual for base, residual in zip(values, activated)]

    def _down_block(self, values: Sequence[float], prefix: str) -> List[float]:
        projected = self._linear(
            values,
            self._model_state[f"{prefix}.0.weight"],
            self._model_state[f"{prefix}.0.bias"],
        )
        normalized = self._layer_norm(
            projected,
            self._model_state[f"{prefix}.1.weight"],
            self._model_state[f"{prefix}.1.bias"],
        )
        return [self._gelu(value) for value in normalized]

    def _run_model(self, features: Sequence[float]) -> float:
        x = self._linear(
            features,
            self._model_state["input_proj.weight"],
            self._model_state["input_proj.bias"],
        )
        x = self._layer_norm(
            x,
            self._model_state["input_norm.weight"],
            self._model_state["input_norm.bias"],
        )
        x = [self._gelu(value) for value in x]
        x = self._residual_block(x, "block_1024")
        x = self._down_block(x, "down_1024_512")
        x = self._residual_block(x, "block_512")
        x = self._down_block(x, "down_512_256")
        x = self._residual_block(x, "block_256")
        x = self._down_block(x, "down_256_128")
        logits = self._linear(
            x,
            self._model_state["head.weight"],
            self._model_state["head.bias"],
        )
        return self._softmax(logits)[1]

    @staticmethod
    def _sample_text(payload: Mapping[str, Any]) -> str:
        fields = (
            str(payload.get("endpoint", "")).strip(),
            str(payload.get("parameters", "")).strip(),
            str(payload.get("exploit_vector", "")).strip(),
            str(payload.get("impact", "")).strip(),
            str(payload.get("source_tag", "")).strip(),
        )
        return " ".join(field for field in fields if field)

    def _similar_training_samples(
        self,
        description: str,
        technology_stack: Sequence[str],
        *,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        query_sparse = self._feature_extractor.embed_sparse(description)
        stack_tokens = {token.lower() for token in technology_stack if token}
        best: List[Dict[str, Any]] = []
        for payload in self._load_bridge_samples():
            sample_text = str(payload.get("sample_text", ""))
            sample_sparse = payload.get("sample_sparse", {})
            similarity = sum(
                value * sample_sparse.get(index, 0.0)
                for index, value in query_sparse.items()
            )
            lowered = sample_text.lower()
            tech_bonus = 0.02 * sum(1 for token in stack_tokens if token and token in lowered)
            reliability = float(payload.get("reliability", 0.0))
            score = similarity + tech_bonus + (reliability * 0.001)
            if score <= 0.0:
                continue
            candidate = {
                "score": score,
                "endpoint": str(payload.get("endpoint", "")),
                "description": str(payload.get("description", "")),
                "sample_text": sample_text,
            }
            best.append(candidate)
            best.sort(key=lambda item: item["score"], reverse=True)
            if len(best) > limit:
                best = best[:limit]
        return best

    def _load_bridge_samples(self) -> List[Dict[str, Any]]:
        if self._bridge_samples is not None:
            return self._bridge_samples
        if not BRIDGE_SAMPLE_PATH.exists():
            self._bridge_samples = []
            return self._bridge_samples
        cached: List[Dict[str, Any]] = []
        with gzip.open(BRIDGE_SAMPLE_PATH, "rt", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                sample_text = self._sample_text(payload)
                cached.append(
                    {
                        "endpoint": str(payload.get("endpoint", "")),
                        "description": str(payload.get("exploit_vector", "")).strip() or sample_text,
                        "sample_text": sample_text,
                        "sample_sparse": self._feature_extractor.embed_sparse(sample_text),
                        "reliability": float(payload.get("reliability", 0.0)),
                    }
                )
        self._bridge_samples = cached
        return self._bridge_samples

    @staticmethod
    def _derive_focus_areas(
        description: str,
        technology_stack: Sequence[str],
        matches: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        corpus = " ".join(
            [description, *technology_stack, *(str(match.get("sample_text", "")) for match in matches)]
        ).lower()
        ranked: List[tuple[int, str]] = []
        for token, label in FOCUS_KEYWORDS.items():
            score = corpus.count(token)
            if score:
                ranked.append((score, label))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        focus_areas: List[str] = []
        for _, label in ranked:
            if label not in focus_areas:
                focus_areas.append(label)
            if len(focus_areas) >= 4:
                break
        if focus_areas:
            return focus_areas
        return ["Human review of historically similar patterns for the provided scope"]

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def _run_keyword_fallback_model(
        self,
        description: str,
        technology_stack: Sequence[str],
    ) -> float:
        corpus = " ".join([description, *technology_stack]).lower()
        keyword_hits = sum(1 for token in FOCUS_KEYWORDS if token in corpus)
        repeated_hits = sum(corpus.count(token) for token in FOCUS_KEYWORDS)
        stack_hits = len({token.strip().lower() for token in technology_stack if str(token).strip()})
        base_score = 0.22
        keyword_score = min(keyword_hits * 0.08, 0.40)
        repetition_score = min(max(repeated_hits - keyword_hits, 0) * 0.02, 0.10)
        stack_score = min(stack_hits * 0.04, 0.12)
        length_score = min(len(corpus.split()) / 80.0, 0.12)
        auth_bonus = 0.10 if any(token in corpus for token in ("login", "auth", "password", "session")) else 0.0
        return self._clamp(base_score + keyword_score + repetition_score + stack_score + length_score + auth_bonus)

    def analyze_target_description(
        self,
        description: str,
        technology_stack: List[str],
        scope: str,
    ) -> AnalysisResult:
        """
        This function performs NO network requests.
        It performs NO scanning of any target.
        It returns patterns learned from historical public data only.
        All findings require human verification before any action.
        Human remains the sole authority on all decisions.
        """
        _verify_guard("can_ai_execute", can_ai_execute)
        _verify_guard("can_ai_verify_bug", can_ai_verify_bug)

        combined_description = self._combine_description(description, technology_stack, scope)
        feature_vector = self._feature_extractor.extract_features(raw_text=combined_description)
        probability = (
            self._run_keyword_fallback_model(combined_description, technology_stack)
            if self._fallback_model_active
            else self._run_model(feature_vector)
        )
        confidence = self._clamp(
            probability
            if probability >= self._optimal_threshold
            else probability * self._optimal_threshold
        )

        similar_samples = self._similar_training_samples(combined_description, technology_stack)
        pattern_matches = [
            f"{sample['endpoint']}: {sample['description']}".strip(": ")
            for sample in similar_samples
        ]
        suggested_focus_areas = self._derive_focus_areas(
            combined_description,
            technology_stack,
            similar_samples,
        )

        return AnalysisResult(
            confidence=confidence,
            pattern_matches=pattern_matches,
            suggested_focus_areas=suggested_focus_areas,
            requires_human_verification=True,
            model_version=self._model_version,
            analysis_timestamp=datetime.now(UTC),
        )
