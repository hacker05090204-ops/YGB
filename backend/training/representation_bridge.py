"""
Representation Bridge — Python interface to C++ diversity engines.

Generates expanded feature vectors using the same patterns as the
C++ native engines (http_variance, dom_topology, api_schema, state_graph)
directly in Python/NumPy for PyTorch DataLoader integration.

This is a pure-Python mirror of the C++ logic for training integration.
The C++ engines provide the reference implementation; this bridge
provides the DataLoader-compatible interface.

GOVERNANCE: MODE-A only. No decision labels. No exploit content.
"""

from pathlib import Path
import numpy as np
from typing import Optional, Sequence, Tuple
from dataclasses import dataclass


FIXED_SEED = 42
_BLOCKED_SYNTHETIC_REPRESENTATION_MESSAGE = (
    "blocked: DISABLED: Synthetic representation generation is forbidden in production"
)


class SyntheticDataBlockedError(RuntimeError):
    pass


class DataShapeError(ValueError):
    """Raised when a feature tensor has an unexpected shape."""


class DataValueError(ValueError):
    """Raised when a feature tensor contains invalid values."""


def _abort_synthetic_generation(component: str) -> None:
    raise SyntheticDataBlockedError(
        f"{_BLOCKED_SYNTHETIC_REPRESENTATION_MESSAGE} ({component})"
    )


@dataclass
class ExpansionConfig:
    """Configuration for representation expansion."""

    total_samples: int = 8000
    feature_dim: int = 256
    seed: int = FIXED_SEED
    # Diversity targets
    protocol_diversity_boost: float = 0.30
    dom_variance_boost: float = 0.25
    api_nesting_boost: float = 0.20
    auth_flow_templates: int = 10


@dataclass(frozen=True)
class RepresentationValidationResult:
    """Result of validating one representation vector against stored state."""

    valid: bool
    reason: str
    cosine_similarity: Optional[float] = None
    matched_index: Optional[int] = None
    stored_count: int = 0


class InvalidRepresentationError(ValueError):
    """Raised when a representation is rejected on the bridge path."""

    def __init__(self, result: RepresentationValidationResult):
        self.result = result
        super().__init__(result.reason)


class RepresentationValidator:
    """Validate representation tensors before they are admitted to the bridge path."""

    def __init__(self, duplicate_threshold: float = 0.99):
        self.duplicate_threshold = float(duplicate_threshold)

    @staticmethod
    def _coerce_vector(representation: np.ndarray) -> np.ndarray:
        vector = np.asarray(representation, dtype=np.float32)
        if vector.ndim != 1:
            raise ValueError("representation tensor must be 1-dimensional")
        if vector.size == 0:
            raise ValueError("representation tensor is empty")
        if not np.isfinite(vector).all():
            raise ValueError("representation tensor contains NaN/Inf values")

        norm = float(np.linalg.norm(vector))
        if norm <= 0.0:
            raise ValueError("representation tensor norm must be greater than zero")
        return vector

    @staticmethod
    def _iter_stored_representations(
        stored_representations: Optional[Sequence[np.ndarray]],
    ):
        if stored_representations is None:
            return ()

        if isinstance(stored_representations, np.ndarray):
            if stored_representations.ndim == 1:
                return (stored_representations,)
            if stored_representations.ndim == 2:
                return tuple(stored_representations[idx] for idx in range(stored_representations.shape[0]))
            raise ValueError("stored representations must be a 1D or 2D tensor")

        return tuple(stored_representations)

    def validate(
        self,
        representation: np.ndarray,
        stored_representations: Optional[Sequence[np.ndarray]] = None,
    ) -> RepresentationValidationResult:
        """Return a structured validation result for a representation tensor."""
        try:
            vector = self._coerce_vector(representation)
        except ValueError as exc:
            return RepresentationValidationResult(valid=False, reason=str(exc))

        vector_norm = float(np.linalg.norm(vector))
        stored = self._iter_stored_representations(stored_representations)

        for idx, candidate in enumerate(stored):
            try:
                candidate_vector = self._coerce_vector(candidate)
            except ValueError as exc:
                return RepresentationValidationResult(
                    valid=False,
                    reason=f"stored representation {idx} invalid: {exc}",
                    matched_index=idx,
                    stored_count=len(stored),
                )

            if candidate_vector.shape != vector.shape:
                return RepresentationValidationResult(
                    valid=False,
                    reason=(
                        f"stored representation {idx} dimensionality mismatch: "
                        f"expected {vector.shape[0]}, got {candidate_vector.shape[0]}"
                    ),
                    matched_index=idx,
                    stored_count=len(stored),
                )

            cosine_similarity = float(
                np.dot(vector, candidate_vector)
                / (vector_norm * float(np.linalg.norm(candidate_vector)))
            )
            if cosine_similarity > self.duplicate_threshold:
                return RepresentationValidationResult(
                    valid=False,
                    reason=(
                        "representation rejected as near-duplicate: "
                        f"cosine_similarity={cosine_similarity:.6f} "
                        f"> {self.duplicate_threshold:.2f}"
                    ),
                    cosine_similarity=cosine_similarity,
                    matched_index=idx,
                    stored_count=len(stored),
                )

        return RepresentationValidationResult(
            valid=True,
            reason="representation_valid",
            stored_count=len(stored),
        )

    def validate_or_raise(
        self,
        representation: np.ndarray,
        stored_representations: Optional[Sequence[np.ndarray]] = None,
    ) -> RepresentationValidationResult:
        """Bridge-path validation that raises for invalid representations."""
        result = self.validate(representation, stored_representations)
        if not result.valid:
            raise InvalidRepresentationError(result)
        return result


def validate_representation_for_bridge(
    representation: np.ndarray,
    stored_representations: Optional[Sequence[np.ndarray]] = None,
    validator: Optional[RepresentationValidator] = None,
) -> RepresentationValidationResult:
    """Bridge-facing validation entrypoint that raises on invalid tensors."""
    active_validator = validator or RepresentationValidator()
    return active_validator.validate_or_raise(representation, stored_representations)


class RepresentationExpander:
    """
    Generates expanded representation data matching C++ engine patterns.

    Feature layout (256 dims):
      [0-31]   HTTP protocol features
      [32-63]  DOM topology features
      [64-95]  API schema features
      [96-127] Auth flow state graph features
      [128-191] Interaction features (cross-group)
      [192-255] Noise/regularization features
    """

    _SYNTHETIC_GENERATION_BLOCKED = True

    def __init__(self, config: Optional[ExpansionConfig] = None, seed: int = FIXED_SEED):
        effective_seed = seed if config is None else config.seed
        self.config = config or ExpansionConfig(seed=effective_seed)
        self.rng = np.random.RandomState(effective_seed)

    def _raise_if_synthetic_generation_blocked(self) -> None:
        if self._SYNTHETIC_GENERATION_BLOCKED:
            raise SyntheticDataBlockedError(_BLOCKED_SYNTHETIC_REPRESENTATION_MESSAGE)

    @staticmethod
    def _coerce_feature_matrix(name: str, matrix: np.ndarray) -> np.ndarray:
        array = np.asarray(matrix, dtype=np.float32)
        if array.ndim != 2:
            raise DataShapeError(f"{name} must be a 2D array, got shape {array.shape}")
        if not np.isfinite(array).all():
            raise DataValueError(f"{name} contains NaN/Inf values")
        return array

    def combine(self, *feature_groups: np.ndarray) -> np.ndarray:
        """Combine real feature groups into one [N, 256] matrix."""
        if not feature_groups:
            raise DataShapeError("at least one feature group is required")

        matrices = [
            self._coerce_feature_matrix(f"feature_groups[{idx}]", group)
            for idx, group in enumerate(feature_groups)
        ]
        row_count = matrices[0].shape[0]
        for idx, matrix in enumerate(matrices[1:], start=1):
            if matrix.shape[0] != row_count:
                raise DataShapeError(
                    "row count mismatch between feature groups: "
                    f"feature_groups[0]={row_count}, feature_groups[{idx}]={matrix.shape[0]}"
                )

        combined = np.concatenate(matrices, axis=1).astype(np.float32, copy=False)
        if combined.shape[1] != self.config.feature_dim:
            raise DataShapeError(
                f"combined features must have {self.config.feature_dim} columns, got {combined.shape[1]}"
            )
        return combined

    def expand(self, *feature_groups: np.ndarray) -> np.ndarray:
        """Pass through or combine real feature tensors without synthetic generation."""
        return self.combine(*feature_groups)

    def generate_http_features(self, n: int) -> np.ndarray:
        """Generate HTTP protocol representation features (32 dims)."""
        self._raise_if_synthetic_generation_blocked()
        feats = np.zeros((n, 32), dtype=np.float32)
        feats[:, 0] = self.rng.randint(0, 15, n) / 14.0  # method
        feats[:, 1] = self.rng.choice([0.2, 0.4, 0.6, 0.8, 1.0], n)  # status family
        feats[:, 2] = self.rng.randint(0, 20, n) / 19.0  # status specific
        feats[:, 3] = self.rng.randint(0, 12, n) / 11.0  # content-type
        feats[:, 4] = self.rng.randint(0, 8, n) / 7.0  # auth scheme
        feats[:, 5] = self.rng.randint(0, 6, n) / 5.0  # encoding
        feats[:, 6] = self.rng.uniform(0, 1, n)  # has_body
        feats[:, 7] = np.minimum(1, np.log2(1 + self.rng.uniform(0, 10000, n)) / 14)
        feats[:, 8] = np.minimum(1, (3 + self.rng.uniform(0, 20, n)) / 25)
        feats[:, 9] = np.minimum(1, self.rng.uniform(0, 5, n) / 5)
        feats[:, 10] = np.minimum(1, self.rng.uniform(0, 8, n) / 10)
        feats[:, 11] = np.minimum(1, (1 + self.rng.uniform(0, 7, n)) / 8)
        feats[:, 12] = (self.rng.uniform(0, 1, n) > 0.3).astype(np.float32)
        feats[:, 13] = (self.rng.uniform(0, 1, n) > 0.6).astype(np.float32)
        feats[:, 14] = (self.rng.uniform(0, 1, n) > 0.5).astype(np.float32)
        feats[:, 15] = (self.rng.uniform(0, 1, n) > 0.95).astype(np.float32)
        for d in range(16, 32):
            feats[:, d] = self.rng.uniform(0, 1, n).astype(np.float32)
        return feats

    def generate_dom_features(self, n: int) -> np.ndarray:
        """Generate DOM topology representation features (32 dims)."""
        self._raise_if_synthetic_generation_blocked()
        feats = np.zeros((n, 32), dtype=np.float32)
        feats[:, 0] = self.rng.randint(1, 21, n) / 20.0  # tree_depth
        feats[:, 1] = np.minimum(1, np.log2(1 + self.rng.uniform(0, 500, n)) / 9)
        feats[:, 2] = np.minimum(1, (1 + self.rng.uniform(0, 8, n)) / 10)
        feats[:, 3] = 0.3 + self.rng.uniform(0, 0.5, n)
        feats[:, 4] = self.rng.randint(0, 6, n) / 5.0  # form_count
        feats[:, 5] = self.rng.randint(0, 16, n) / 15.0  # input_count
        for d in range(6, 32):
            feats[:, d] = self.rng.uniform(0, 1, n).astype(np.float32)
        return feats

    def generate_api_features(self, n: int) -> np.ndarray:
        """Generate API schema representation features (32 dims)."""
        self._raise_if_synthetic_generation_blocked()
        feats = np.zeros((n, 32), dtype=np.float32)
        feats[:, 0] = self.rng.randint(1, 9, n) / 8.0  # path_depth
        feats[:, 6] = self.rng.randint(1, 11, n) / 10.0  # response_nesting
        feats[:, 16] = (self.rng.uniform(0, 1, n) > 0.75).astype(
            np.float32
        )  # is_graphql
        for d in [
            1,
            2,
            3,
            4,
            5,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
        ]:
            feats[:, d] = self.rng.uniform(0, 1, n).astype(np.float32)
        # complexity score
        feats[:, 31] = np.minimum(
            1,
            feats[:, 0] * 0.2
            + feats[:, 6] * 0.25
            + feats[:, 8] * 0.15
            + feats[:, 13] * 0.1
            + feats[:, 17] * 0.15
            + feats[:, 26] * 0.15,
        )
        return feats

    def generate_auth_features(self, n: int) -> np.ndarray:
        """Generate auth flow state graph features (32 dims)."""
        self._raise_if_synthetic_generation_blocked()
        flow_states = [6, 4, 3, 5, 5, 4, 5, 4, 3, 4]
        flow_trans = [8, 5, 4, 7, 7, 5, 7, 5, 4, 6]

        feats = np.zeros((n, 32), dtype=np.float32)
        flows = self.rng.randint(0, 10, n)
        feats[:, 0] = flows / 9.0

        for i in range(n):
            f = flows[i]
            s = flow_states[f] + self.rng.randint(0, 5)
            t = flow_trans[f] + self.rng.randint(0, 4)
            feats[i, 1] = min(1, s / 12.0)
            feats[i, 2] = min(1, t / 15.0)
            feats[i, 3] = min(1, t / max(1, s))

        for d in range(4, 31):
            feats[:, d] = self.rng.uniform(0, 1, n).astype(np.float32)
        # complexity
        feats[:, 31] = np.minimum(
            1,
            feats[:, 1] * 0.2
            + feats[:, 2] * 0.15
            + feats[:, 3] * 0.15
            + feats[:, 12] * 0.1
            + feats[:, 22] * 0.1
            + feats[:, 30] * 0.15
            + feats[:, 20] * 0.15,
        )
        return feats

    def generate_interaction_features(
        self, signal: np.ndarray, response: np.ndarray
    ) -> np.ndarray:
        """Generate interaction features from signal+response (64 dims)."""
        self._raise_if_synthetic_generation_blocked()
        n = signal.shape[0]
        feats = np.zeros((n, 64), dtype=np.float32)
        for d in range(64):
            s_idx = d % 32
            r_idx = (d * 7 + 13) % 32
            # Nonlinear interaction with noise
            feats[:, d] = np.clip(
                signal[:, s_idx] * response[:, r_idx]
                + self.rng.normal(0, 0.05, n).astype(np.float32),
                0,
                1,
            )
        return feats

    def generate_noise_features(self, n: int) -> np.ndarray:
        """Generate noise/regularization features (64 dims)."""
        self._raise_if_synthetic_generation_blocked()
        return self.rng.uniform(0, 1, (n, 64)).astype(np.float32)

    def generate_expanded_dataset(self, n: int = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate full expanded representation dataset.

        Returns:
            Tuple of (features [N, 256], labels [N])
        """
        self._raise_if_synthetic_generation_blocked()
        n = n or self.config.total_samples

        # Generate per-group features
        http = self.generate_http_features(n)
        dom = self.generate_dom_features(n)
        api = self.generate_api_features(n)
        auth = self.generate_auth_features(n)

        signal = np.concatenate([http, dom], axis=1)  # 64 dims
        response = np.concatenate([api, auth], axis=1)  # 64 dims
        interaction = self.generate_interaction_features(signal, response)
        noise = self.generate_noise_features(n)

        features = self.combine(signal, response, interaction, noise)

        # Labels based on signal + response pattern (representation only)
        signal_strength = np.mean(signal[:, :32], axis=1)
        response_strength = np.mean(response[:, :32], axis=1)
        combined = 0.6 * signal_strength + 0.4 * response_strength
        labels = (combined > 0.5).astype(np.float32)

        # Add edge cases: 10% with noisy labels near boundary
        n_edge = int(n * 0.10)
        edge_mask = np.argsort(np.abs(combined - 0.5))[:n_edge]
        labels[edge_mask] = (
            combined[edge_mask] + self.rng.normal(0, 0.1, n_edge) > 0.5
        ).astype(np.float32)

        return features, labels


class RealFeatureLoader:
    """Load validated real feature matrices from on-disk artifacts."""

    @staticmethod
    def _load_safetensors(path: Path) -> np.ndarray:
        try:
            from safetensors.numpy import load_file as load_safetensors_file
        except Exception as exc:  # pragma: no cover - depends on optional package state
            raise DataValueError(f"{path}: safetensors support unavailable: {exc}") from exc

        tensors = load_safetensors_file(str(path))
        if "features" in tensors:
            return np.asarray(tensors["features"])
        if len(tensors) == 1:
            return np.asarray(next(iter(tensors.values())))
        raise DataShapeError(
            f"{path}: expected exactly one tensor or a 'features' tensor, found {sorted(tensors.keys())}"
        )

    @staticmethod
    def _validate(path: Path, array: np.ndarray) -> np.ndarray:
        features = np.asarray(array)
        if features.ndim != 2 or features.shape[0] < 1 or features.shape[1] != 256:
            raise DataShapeError(
                f"{path}: expected shape (N, 256) with N >= 1, got {features.shape}"
            )
        if features.dtype != np.float32:
            raise DataShapeError(f"{path}: expected dtype float32, got {features.dtype}")
        invalid_locations = np.argwhere(~np.isfinite(features))
        if invalid_locations.size:
            row, column = invalid_locations[0]
            raise DataValueError(
                f"{path}: non-finite value at index ({int(row)}, {int(column)}): {features[row, column]!r}"
            )
        zero_rows = np.argwhere(np.all(features == 0.0, axis=1))
        if zero_rows.size:
            raise DataValueError(
                f"{path}: all-zero row at index {int(zero_rows[0, 0])}"
            )
        zero_variance_rows = np.argwhere(np.var(features, axis=1) <= 0.0)
        if zero_variance_rows.size:
            raise DataValueError(
                f"{path}: zero-variance row at index {int(zero_variance_rows[0, 0])}"
            )
        return features

    @staticmethod
    def load(path: Path) -> np.ndarray:
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix == ".npy":
            features = np.load(target, allow_pickle=False)
        elif suffix == ".safetensors":
            features = RealFeatureLoader._load_safetensors(target)
        else:
            raise DataShapeError(f"{target}: unsupported feature file suffix '{target.suffix}'")
        return RealFeatureLoader._validate(target, features)
