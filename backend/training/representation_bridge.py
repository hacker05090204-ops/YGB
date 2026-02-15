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
import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass


FIXED_SEED = 42


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

    def __init__(self, config: ExpansionConfig = None, seed: int = FIXED_SEED):
        self.config = config or ExpansionConfig()
        self.rng = np.random.RandomState(seed)

    def generate_http_features(self, n: int) -> np.ndarray:
        """Generate HTTP protocol representation features (32 dims)."""
        feats = np.zeros((n, 32), dtype=np.float32)
        feats[:, 0] = self.rng.randint(0, 15, n) / 14.0  # method
        feats[:, 1] = self.rng.choice([0.2, 0.4, 0.6, 0.8, 1.0], n)  # status family
        feats[:, 2] = self.rng.randint(0, 20, n) / 19.0  # status specific
        feats[:, 3] = self.rng.randint(0, 12, n) / 11.0  # content-type
        feats[:, 4] = self.rng.randint(0, 8, n) / 7.0    # auth scheme
        feats[:, 5] = self.rng.randint(0, 6, n) / 5.0    # encoding
        feats[:, 6] = self.rng.uniform(0, 1, n)           # has_body
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
        feats = np.zeros((n, 32), dtype=np.float32)
        feats[:, 0] = self.rng.randint(1, 21, n) / 20.0  # tree_depth
        feats[:, 1] = np.minimum(1, np.log2(1 + self.rng.uniform(0, 500, n)) / 9)
        feats[:, 2] = np.minimum(1, (1 + self.rng.uniform(0, 8, n)) / 10)
        feats[:, 3] = 0.3 + self.rng.uniform(0, 0.5, n)
        feats[:, 4] = self.rng.randint(0, 6, n) / 5.0    # form_count
        feats[:, 5] = self.rng.randint(0, 16, n) / 15.0   # input_count
        for d in range(6, 32):
            feats[:, d] = self.rng.uniform(0, 1, n).astype(np.float32)
        return feats

    def generate_api_features(self, n: int) -> np.ndarray:
        """Generate API schema representation features (32 dims)."""
        feats = np.zeros((n, 32), dtype=np.float32)
        feats[:, 0] = self.rng.randint(1, 9, n) / 8.0    # path_depth
        feats[:, 6] = self.rng.randint(1, 11, n) / 10.0   # response_nesting
        feats[:, 16] = (self.rng.uniform(0, 1, n) > 0.75).astype(np.float32)  # is_graphql
        for d in [1,2,3,4,5,7,8,9,10,11,12,13,14,15,17,18,19,20,21,22,23,24,25,26,27,28,29,30]:
            feats[:, d] = self.rng.uniform(0, 1, n).astype(np.float32)
        # complexity score
        feats[:, 31] = np.minimum(1,
            feats[:, 0]*0.2 + feats[:, 6]*0.25 + feats[:, 8]*0.15 +
            feats[:, 13]*0.1 + feats[:, 17]*0.15 + feats[:, 26]*0.15)
        return feats

    def generate_auth_features(self, n: int) -> np.ndarray:
        """Generate auth flow state graph features (32 dims)."""
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
        feats[:, 31] = np.minimum(1,
            feats[:, 1]*0.2 + feats[:, 2]*0.15 + feats[:, 3]*0.15 +
            feats[:, 12]*0.1 + feats[:, 22]*0.1 + feats[:, 30]*0.15 +
            feats[:, 20]*0.15)
        return feats

    def generate_interaction_features(self, signal: np.ndarray,
                                       response: np.ndarray) -> np.ndarray:
        """Generate interaction features from signal+response (64 dims)."""
        n = signal.shape[0]
        feats = np.zeros((n, 64), dtype=np.float32)
        for d in range(64):
            s_idx = d % 32
            r_idx = (d * 7 + 13) % 32
            # Nonlinear interaction with noise
            feats[:, d] = np.clip(
                signal[:, s_idx] * response[:, r_idx] +
                self.rng.normal(0, 0.05, n).astype(np.float32),
                0, 1)
        return feats

    def generate_noise_features(self, n: int) -> np.ndarray:
        """Generate noise/regularization features (64 dims)."""
        return self.rng.uniform(0, 1, (n, 64)).astype(np.float32)

    def generate_expanded_dataset(
        self, n: int = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate full expanded representation dataset.

        Returns:
            Tuple of (features [N, 256], labels [N])
        """
        n = n or self.config.total_samples

        # Generate per-group features
        http = self.generate_http_features(n)
        dom = self.generate_dom_features(n)
        api = self.generate_api_features(n)
        auth = self.generate_auth_features(n)

        signal = np.concatenate([http, dom], axis=1)     # 64 dims
        response = np.concatenate([api, auth], axis=1)   # 64 dims
        interaction = self.generate_interaction_features(signal, response)
        noise = self.generate_noise_features(n)

        features = np.concatenate(
            [signal, response, interaction, noise], axis=1)

        # Labels based on signal + response pattern (representation only)
        signal_strength = np.mean(signal[:, :32], axis=1)
        response_strength = np.mean(response[:, :32], axis=1)
        combined = 0.6 * signal_strength + 0.4 * response_strength
        labels = (combined > 0.5).astype(np.float32)

        # Add edge cases: 10% with noisy labels near boundary
        n_edge = int(n * 0.10)
        edge_mask = np.argsort(np.abs(combined - 0.5))[:n_edge]
        labels[edge_mask] = (combined[edge_mask] +
            self.rng.normal(0, 0.1, n_edge) > 0.5).astype(np.float32)

        return features, labels
