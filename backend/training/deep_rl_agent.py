"""
Deep RL layer that makes the model learn from real outcomes.
Uses GRPO (Group Relative Policy Optimization) style rewards.
sklearn provides feature engineering and anomaly detection.
Real rewards only — no simulated outcomes.
"""

import logging
import json
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import Counter
import numpy as np

logger = logging.getLogger("ygb.deep_rl")


@dataclass
class RLEpisode:
    """Single RL episode recording a prediction and its outcome."""
    episode_id: str
    cve_id: str
    predicted_severity: str
    true_severity: str
    reward: float
    reward_source: str   # "cisa_kev"|"nvd_update"|"vendor_confirm"|"label"
    advantage: float     # GRPO advantage
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class GRPORewardNormalizer:
    """
    Group Relative Policy Optimization reward normalization.
    Normalizes rewards within a group to reduce variance.
    """

    def __init__(self, group_size: int = 8):
        self.group_size = group_size
        self._buffer: List[float] = []

    def add(self, reward: float) -> float:
        """Add reward and return normalized advantage."""
        self._buffer.append(reward)
        
        if len(self._buffer) >= self.group_size:
            # Use last group_size rewards for normalization
            group = self._buffer[-self.group_size:]
            mean = np.mean(group)
            std = np.std(group) + 1e-8
            advantage = (reward - mean) / std
        else:
            # Not enough samples yet, return raw reward
            advantage = reward
        
        return float(advantage)

    def reset(self):
        """Reset the buffer."""
        self._buffer = []

    def get_stats(self) -> Dict[str, float]:
        """Get current buffer statistics."""
        if not self._buffer:
            return {"mean": 0.0, "std": 0.0, "count": 0}
        
        return {
            "mean": float(np.mean(self._buffer)),
            "std": float(np.std(self._buffer)),
            "count": len(self._buffer),
        }


class SklearnFeatureAugmenter:
    """
    sklearn-powered feature engineering for CVE samples.
    Extracts statistical + anomaly features that deep learning misses.
    """

    def __init__(self):
        self._scaler = None
        self._iso_forest = None
        self._pca = None
        self._fitted = False

    def fit(self, features: np.ndarray):
        """Fit on real training data. Never call with synthetic data."""
        try:
            from sklearn.preprocessing import StandardScaler
            from sklearn.ensemble import IsolationForest
            from sklearn.decomposition import PCA
        except ImportError:
            logger.warning("scikit-learn not installed. pip install scikit-learn")
            return

        if features.shape[0] < 10:
            logger.warning("Not enough samples to fit sklearn augmenter (need >= 10)")
            return

        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(features)

        # PCA for dimensionality insight (not reduction — just features)
        n_components = min(32, features.shape[1], features.shape[0] - 1)
        if n_components > 0:
            self._pca = PCA(n_components=n_components)
            self._pca.fit(X_scaled)

        # Anomaly detection — flag unusual CVE patterns
        self._iso_forest = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42
        )
        self._iso_forest.fit(X_scaled)

        self._fitted = True
        logger.info("SklearnAugmenter fitted on %d samples", len(features))

    def augment(self, features: np.ndarray) -> np.ndarray:
        """
        Add sklearn-derived features to base features.
        Returns augmented array with additional columns.
        """
        if not self._fitted:
            logger.debug("SklearnAugmenter not fitted — returning original features")
            return features

        try:
            X_scaled = self._scaler.transform(features)

            augmented_features = []

            # PCA reconstruction error (anomaly signal)
            if self._pca is not None:
                X_pca = self._pca.transform(X_scaled)
                X_reconstructed = self._pca.inverse_transform(X_pca)
                recon_error = np.mean((X_scaled - X_reconstructed) ** 2, axis=1, keepdims=True)
                augmented_features.append(recon_error)

            # Anomaly score from Isolation Forest
            if self._iso_forest is not None:
                anomaly_score = self._iso_forest.score_samples(X_scaled).reshape(-1, 1)
                augmented_features.append(anomaly_score)

            # Combine with original features
            if augmented_features:
                augmented = np.concatenate([features] + augmented_features, axis=1)
                return augmented.astype(np.float32)
            else:
                return features

        except Exception as e:
            logger.warning("Feature augmentation failed: %s", e)
            return features

    def save(self, path: Path):
        """Save fitted augmenter to disk."""
        if not self._fitted:
            logger.warning("Cannot save unfitted augmenter")
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "scaler": self._scaler,
            "pca": self._pca,
            "iso_forest": self._iso_forest,
            "fitted": self._fitted,
        }
        path.write_bytes(pickle.dumps(data))
        logger.info("SklearnAugmenter saved to %s", path)

    def load(self, path: Path):
        """Load fitted augmenter from disk."""
        if not path.exists():
            logger.warning("Augmenter file not found: %s", path)
            return

        try:
            data = pickle.loads(path.read_bytes())
            self._scaler = data.get("scaler")
            self._pca = data.get("pca")
            self._iso_forest = data.get("iso_forest")
            self._fitted = data.get("fitted", False)
            logger.info("SklearnAugmenter loaded from %s", path)
        except Exception as e:
            logger.error("Failed to load augmenter: %s", e)

    @property
    def is_fitted(self) -> bool:
        """Check if augmenter is fitted."""
        return self._fitted

    def get_feature_count(self) -> int:
        """Get number of additional features added."""
        if not self._fitted:
            return 0
        
        count = 0
        if self._pca is not None:
            count += 1  # reconstruction error
        if self._iso_forest is not None:
            count += 1  # anomaly score
        return count


class DeepRLAgent:
    """
    Orchestrates the full Deep RL loop.
    Feeds real outcome signals back into training.
    """

    # Severity order for reward calculation
    SEVERITY_ORDER = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "INFORMATIONAL": 0,
        "INFO": 0,
    }

    # Trust levels for different outcome sources
    SOURCE_TRUST = {
        "cisa_kev": 1.0,        # CISA Known Exploited Vulnerabilities
        "nvd_update": 0.9,      # NVD official updates
        "vendor_confirm": 0.95, # Vendor confirmations
        "exploit_db": 0.85,     # Exploit-DB entries
        "label": 0.7,           # Training labels
        "user_feedback": 0.6,   # User-provided feedback
    }

    def __init__(self, checkpoint_dir: Path = Path("checkpoints")):
        self._normalizer = GRPORewardNormalizer(group_size=8)
        self._sklearn_aug = SklearnFeatureAugmenter()
        self._episodes: List[RLEpisode] = []
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._episodes_path = self._checkpoint_dir / "rl_episodes.jsonl"
        
        # Load existing episodes if available
        self._load_episodes()

    def record_outcome(
        self,
        cve_id: str,
        predicted: str,
        true: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RLEpisode:
        """
        Record a real outcome and compute GRPO reward.
        
        Args:
            cve_id: CVE identifier
            predicted: Predicted severity level
            true: True severity level
            source: Source of ground truth
            metadata: Additional metadata
        """
        import uuid

        # Normalize severity strings
        predicted = predicted.upper()
        true = true.upper()

        # Compute raw reward
        raw_reward = self._compute_reward(predicted, true, source)
        
        # Compute GRPO advantage
        advantage = self._normalizer.add(raw_reward)

        # Create episode
        episode = RLEpisode(
            episode_id=uuid.uuid4().hex[:8],
            cve_id=cve_id,
            predicted_severity=predicted,
            true_severity=true,
            reward=raw_reward,
            reward_source=source,
            advantage=advantage,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        self._episodes.append(episode)

        # Persist to jsonl
        with open(self._episodes_path, "a") as f:
            f.write(json.dumps(self._episode_to_dict(episode)) + "\n")

        logger.debug(
            "Recorded episode: %s | %s→%s | reward=%.2f | advantage=%.2f",
            cve_id, predicted, true, raw_reward, advantage
        )

        return episode

    def _compute_reward(self, predicted: str, true: str, source: str) -> float:
        """
        Real reward function based on severity accuracy and source trust.
        
        Reward structure:
        - Exact match: +1.0 * trust
        - Off by 1 level: -0.2 * trust
        - Off by 2+ levels: -0.4 * trust
        - Missing CRITICAL: -0.8 * trust (extra penalty)
        - False CRITICAL: -0.5 * trust (extra penalty)
        """
        trust = self.SOURCE_TRUST.get(source, 0.5)

        # Exact match
        if predicted == true:
            return 1.0 * trust

        # Get severity values
        pred_v = self.SEVERITY_ORDER.get(predicted, 2)
        true_v = self.SEVERITY_ORDER.get(true, 2)
        distance = abs(pred_v - true_v)

        # Base penalty
        if distance == 1:
            base = -0.2
        else:
            base = -0.4

        # Extra penalty for missing critical vulnerabilities
        if true in ("CRITICAL", "HIGH") and pred_v < 2:
            base -= 0.4

        # Extra penalty for false critical alarms
        if predicted == "CRITICAL" and true in ("LOW", "INFORMATIONAL", "INFO"):
            base -= 0.3

        return max(-1.0, base * trust)

    def get_sample_weights(self, cve_ids: List[str]) -> np.ndarray:
        """
        For each training sample, return weight based on RL history.
        High-reward samples get higher weight.
        
        Args:
            cve_ids: List of CVE IDs
            
        Returns:
            Array of sample weights
        """
        weights = np.ones(len(cve_ids), dtype=np.float32)
        
        # Build episode map
        episode_map = {}
        for ep in self._episodes:
            # Keep most recent episode for each CVE
            if ep.cve_id not in episode_map or ep.timestamp > episode_map[ep.cve_id].timestamp:
                episode_map[ep.cve_id] = ep

        # Assign weights based on advantage
        for i, cve_id in enumerate(cve_ids):
            if cve_id in episode_map:
                ep = episode_map[cve_id]
                # Scale advantage to weight range [0.5, 2.0]
                # Positive advantage → higher weight
                # Negative advantage → lower weight
                weight = 1.0 + (ep.advantage * 0.5)
                weights[i] = max(0.5, min(2.0, weight))

        return weights

    def fit_sklearn(self, features: np.ndarray):
        """Fit sklearn augmenter on real training features."""
        self._sklearn_aug.fit(features)
        augmenter_path = self._checkpoint_dir / "sklearn_augmenter.pkl"
        self._sklearn_aug.save(augmenter_path)

    def augment_features(self, features: np.ndarray) -> np.ndarray:
        """Augment features with sklearn-derived signals."""
        return self._sklearn_aug.augment(features)

    def load_sklearn_augmenter(self):
        """Load sklearn augmenter from checkpoint."""
        augmenter_path = self._checkpoint_dir / "sklearn_augmenter.pkl"
        self._sklearn_aug.load(augmenter_path)

    def get_episode_stats(self) -> Dict[str, Any]:
        """Get statistics about recorded episodes."""
        if not self._episodes:
            return {
                "total": 0,
                "mean_reward": 0.0,
                "positive": 0,
                "negative": 0,
                "by_source": {},
                "by_severity": {},
            }

        rewards = [e.reward for e in self._episodes]
        
        # Count by source
        by_source = Counter(e.reward_source for e in self._episodes)
        
        # Count by predicted severity
        by_severity = Counter(e.predicted_severity for e in self._episodes)

        return {
            "total": len(self._episodes),
            "mean_reward": float(np.mean(rewards)),
            "std_reward": float(np.std(rewards)),
            "positive": sum(1 for r in rewards if r > 0),
            "negative": sum(1 for r in rewards if r < 0),
            "by_source": dict(by_source),
            "by_severity": dict(by_severity),
            "normalizer_stats": self._normalizer.get_stats(),
        }

    def get_recent_episodes(self, n: int = 10) -> List[RLEpisode]:
        """Get n most recent episodes."""
        return self._episodes[-n:] if self._episodes else []

    def _load_episodes(self):
        """Load episodes from disk."""
        if not self._episodes_path.exists():
            return

        try:
            with open(self._episodes_path, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        episode = self._dict_to_episode(data)
                        self._episodes.append(episode)
            
            logger.info("Loaded %d episodes from %s", len(self._episodes), self._episodes_path)
        except Exception as e:
            logger.error("Failed to load episodes: %s", e)

    def _episode_to_dict(self, episode: RLEpisode) -> Dict[str, Any]:
        """Convert episode to dictionary for serialization."""
        return {
            "episode_id": episode.episode_id,
            "cve_id": episode.cve_id,
            "predicted_severity": episode.predicted_severity,
            "true_severity": episode.true_severity,
            "reward": episode.reward,
            "reward_source": episode.reward_source,
            "advantage": episode.advantage,
            "timestamp": episode.timestamp,
            "metadata": episode.metadata,
        }

    def _dict_to_episode(self, data: Dict[str, Any]) -> RLEpisode:
        """Convert dictionary to episode."""
        return RLEpisode(
            episode_id=data["episode_id"],
            cve_id=data["cve_id"],
            predicted_severity=data["predicted_severity"],
            true_severity=data["true_severity"],
            reward=data["reward"],
            reward_source=data["reward_source"],
            advantage=data["advantage"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
        )

    @property
    def sklearn_augmenter(self) -> SklearnFeatureAugmenter:
        """Get sklearn augmenter instance."""
        return self._sklearn_aug


if __name__ == "__main__":
    # Example usage
    print("Deep RL Agent")
    print("=" * 50)
    print("\nUsage:")
    print("  from backend.training.deep_rl_agent import DeepRLAgent")
    print("  agent = DeepRLAgent()")
    print("  episode = agent.record_outcome('CVE-2024-0001', 'CRITICAL', 'CRITICAL', 'cisa_kev')")
    print("  print(f'Reward: {episode.reward}, Advantage: {episode.advantage}')")
