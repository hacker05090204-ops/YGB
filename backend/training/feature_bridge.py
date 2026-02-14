"""
Python Feature Bridge — Numpy implementation of C++ feature engine.

Implements the same algorithms as native/feature_engine/feature_diversifier.cpp,
native/calibration/temperature_scaling.cpp, and native/robustness/drift_augmenter.cpp.

When MSVC is available, compile the C++ and use pybind11. Until then,
this pure numpy implementation provides identical behavior.

All operations are deterministic (seeded RNG).
"""
import numpy as np
from dataclasses import dataclass


@dataclass
class FeatureConfig:
    input_dim: int = 256
    signal_start: int = 0
    signal_end: int = 64
    response_start: int = 64
    response_end: int = 128
    interaction_start: int = 128
    interaction_end: int = 192
    noise_start: int = 192
    noise_end: int = 256
    
    interaction_dropout_p: float = 0.5
    noise_sigma: float = 0.05
    mixup_alpha: float = 0.4
    interaction_penalty_threshold: float = 0.50
    
    training: bool = True
    seed: int = 42


class FeatureDiversifier:
    """
    Breaks interaction shortcut dominance without removing features.
    Deterministic, seed-controlled transformations.
    """
    
    def __init__(self, config: FeatureConfig = None):
        self.config = config or FeatureConfig()
    
    def apply_interaction_dropout(self, features: np.ndarray, 
                                   epoch: int, batch: int) -> np.ndarray:
        """
        Randomly zero p=0.3 of interaction dims [128, 192).
        Replace with group mean + small noise.
        """
        if not self.config.training:
            return features
        
        rng = np.random.RandomState(self.config.seed ^ (epoch * 10000 + batch))
        result = features.copy()
        bs, dim = result.shape
        
        s, e = self.config.interaction_start, self.config.interaction_end
        
        # Compute per-sample mean of interaction dims
        interaction_mean = result[:, s:e].mean(axis=1, keepdims=True)
        
        # Dropout mask
        mask = rng.random((bs, e - s)) < self.config.interaction_dropout_p
        noise = rng.normal(0, 0.02, (bs, e - s))
        
        # Replace masked dims with mean + noise
        result[:, s:e] = np.where(mask, interaction_mean + noise, result[:, s:e])
        
        return result
    
    def apply_adversarial_scramble(self, features: np.ndarray,
                                    epoch: int, batch: int) -> np.ndarray:
        """
        Apply adversarial scrambling to 10% of batches.
        Small permutation within interaction dims.
        """
        if not self.config.training:
            return features
        
        rng = np.random.RandomState(self.config.seed ^ (epoch * 99999 + batch * 7))
        
        # Only 10% of batches
        if rng.random() > 0.10:
            return features
        
        result = features.copy()
        s, e = self.config.interaction_start, self.config.interaction_end
        n_interaction = e - s
        n_swaps = n_interaction // 5
        
        for b in range(result.shape[0]):
            for _ in range(n_swaps):
                i = s + rng.randint(n_interaction)
                j = s + rng.randint(n_interaction)
                result[b, i], result[b, j] = result[b, j], result[b, i]
        
        return result
    
    def apply_mixup(self, features: np.ndarray, labels: np.ndarray,
                    epoch: int, batch: int):
        """Mixup augmentation with lambda ~ Beta(alpha, alpha)."""
        if not self.config.training or features.shape[0] < 2:
            return features, labels
        
        rng = np.random.RandomState(self.config.seed ^ (epoch * 77777 + batch * 13))
        bs = features.shape[0]
        
        result_f = features.copy()
        result_l = labels.copy().astype(np.float32)
        
        for b in range(bs // 2):
            lam = rng.beta(self.config.mixup_alpha, self.config.mixup_alpha)
            lam = max(lam, 1.0 - lam)  # Ensure >= 0.5
            
            i, j = b, bs - 1 - b
            result_f[i] = lam * features[i] + (1 - lam) * features[j]
            result_l[i] = lam * labels[i] + (1 - lam) * labels[j]
        
        return result_f, result_l
    
    def apply_noise_augmentation(self, features: np.ndarray,
                                  epoch: int, batch: int) -> np.ndarray:
        """Controlled Gaussian noise on signal+response dims only."""
        if not self.config.training:
            return features
        
        rng = np.random.RandomState(self.config.seed ^ (epoch * 55555 + batch * 3))
        result = features.copy()
        
        # Signal dims
        s, e = self.config.signal_start, self.config.signal_end
        noise = rng.normal(0, self.config.noise_sigma, result[:, s:e].shape)
        result[:, s:e] = np.clip(result[:, s:e] + noise, 0, 1)
        
        # Response dims
        s, e = self.config.response_start, self.config.response_end
        noise = rng.normal(0, self.config.noise_sigma, result[:, s:e].shape)
        result[:, s:e] = np.clip(result[:, s:e] + noise, 0, 1)
        
        return result
    
    def compute_interaction_contribution(self, features: np.ndarray) -> float:
        """Fraction of total variance from interaction dims."""
        variances = features.var(axis=0)
        total_var = variances.sum()
        if total_var < 1e-10:
            return 0.0
        interaction_var = variances[self.config.interaction_start:self.config.interaction_end].sum()
        return float(interaction_var / total_var)
    
    def compute_balance_penalty(self, features: np.ndarray) -> float:
        """Penalty if interaction contribution > threshold."""
        ratio = self.compute_interaction_contribution(features)
        if ratio > self.config.interaction_penalty_threshold:
            return (ratio - self.config.interaction_penalty_threshold) * 2.0
        return 0.0


class CalibrationEngine:
    """Calibration-aware training utilities."""
    
    @staticmethod
    def compute_calibration_penalty(confidences: np.ndarray, correct: np.ndarray) -> float:
        """Penalty = max(0, mean_confidence - mean_accuracy)."""
        avg_conf = float(confidences.mean())
        avg_acc = float(correct.mean())
        return max(0.0, avg_conf - avg_acc)
    
    @staticmethod
    def compute_monotonicity_penalty(confidences: np.ndarray, correct: np.ndarray,
                                      n_bins: int = 10) -> float:
        """Penalty for non-monotonic accuracy across confidence bins."""
        bins = np.linspace(0, 1, n_bins + 1)
        prev_acc = -1.0
        penalty = 0.0
        
        for i in range(n_bins):
            mask = (confidences >= bins[i]) & (confidences < bins[i + 1])
            if mask.sum() < 5:
                continue
            acc = correct[mask].mean()
            if prev_acc >= 0 and acc < prev_acc:
                penalty += prev_acc - acc
            prev_acc = acc
        
        return float(penalty)


class DriftAugmenter:
    """Drift robustness augmentation for training."""
    
    @staticmethod
    def apply_domain_randomization(features: np.ndarray, scale_pct: float = 0.10,
                                    seed: int = 42) -> np.ndarray:
        """Apply ±scale% feature scaling per dimension."""
        rng = np.random.RandomState(seed)
        scales = rng.uniform(1 - scale_pct, 1 + scale_pct, (1, features.shape[1]))
        return np.clip(features * scales, 0, 1)
    
    @staticmethod
    def apply_random_missingness(features: np.ndarray, miss_rate: float = 0.10,
                                  seed: int = 42) -> np.ndarray:
        """Replace random features with neutral value 0.5."""
        rng = np.random.RandomState(seed)
        mask = rng.random(features.shape) < miss_rate
        result = features.copy()
        result[mask] = 0.5
        return result
    
    @staticmethod
    def inject_novel_patterns(features: np.ndarray, inject_rate: float = 0.05,
                               seed: int = 42) -> np.ndarray:
        """Inject novel structural patterns into fraction of batch."""
        rng = np.random.RandomState(seed)
        result = features.copy()
        n_inject = int(len(result) * inject_rate)
        
        if n_inject == 0:
            return result
        
        # Modify noise dims with novel patterns
        result[:n_inject, 192:256] = np.clip(rng.normal(0.5, 0.15, (n_inject, 64)), 0, 1)
        
        # Small perturbation to interaction dims
        perturbation = (rng.random((n_inject, 64)) - 0.5) * 0.1
        result[:n_inject, 128:192] = np.clip(result[:n_inject, 128:192] + perturbation, 0, 1)
        
        return result
    
    @staticmethod
    def apply_correlated_noise(features: np.ndarray, sigma: float = 0.03,
                                seed: int = 42) -> np.ndarray:
        """Correlated noise across dims."""
        rng = np.random.RandomState(seed)
        result = features.copy()
        base_noise = rng.normal(0, sigma, (features.shape[0], 1))
        dim_noise = rng.normal(0, sigma * 0.5, features.shape)
        return np.clip(result + base_noise + dim_noise, 0, 1)
