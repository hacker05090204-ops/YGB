/**
 * Feature Diversification Engine for G38 MODE-B Gate Fix.
 * 
 * Breaks interaction shortcut dominance WITHOUT removing features.
 * Implements:
 *   - Independent channel expansion
 *   - Interaction regularization (stochastic dropout p=0.3)
 *   - Feature mixing (Mixup, Beta(0.4))
 *   - Noise augmentation (sigma <= 0.05)
 * 
 * Deterministic: all operations seeded.
 * Compile: cl /O2 /EHsc /std:c++17 feature_diversifier.cpp -o feature_diversifier.dll
 */
#ifndef FEATURE_DIVERSIFIER_H
#define FEATURE_DIVERSIFIER_H

#include <vector>
#include <cstdint>
#include <random>

namespace g38 {

struct FeatureConfig {
    int input_dim = 256;
    int signal_start = 0, signal_end = 64;
    int response_start = 64, response_end = 128;
    int interaction_start = 128, interaction_end = 192;
    int noise_start = 192, noise_end = 256;
    
    float interaction_dropout_p = 0.3f;
    float noise_sigma = 0.05f;
    float mixup_alpha = 0.4f;
    float interaction_penalty_threshold = 0.50f;
    
    bool training = true;
    uint64_t seed = 42;
};

class FeatureDiversifier {
public:
    explicit FeatureDiversifier(const FeatureConfig& config);
    
    /**
     * Apply interaction dropout during training.
     * Randomly zero p=0.3 of dims [128, 192) with deterministic seed.
     * Replace with group mean or noise.
     */
    void apply_interaction_dropout(float* features, int batch_size, int dim,
                                    uint64_t epoch, uint64_t batch);
    
    /**
     * Apply adversarial scrambling to 10% of batches.
     * Small permutation within interaction dims.
     */
    void apply_adversarial_scramble(float* features, int batch_size, int dim,
                                     uint64_t epoch, uint64_t batch);
    
    /**
     * Expand features with independent channels.
     * Adds 2 signal-only + 2 response-only channels (normalized separately).
     * Output dim = input_dim + 4.
     */
    void expand_independent_channels(const float* input, float* output,
                                      int batch_size, int input_dim);
    
    /**
     * Mixup augmentation with deterministic lambda ~ Beta(alpha, alpha).
     */
    void apply_mixup(float* features, float* labels, int batch_size, int dim,
                     uint64_t epoch, uint64_t batch);
    
    /**
     * Controlled Gaussian noise on non-dominant dims only.
     */
    void apply_noise_augmentation(float* features, int batch_size, int dim,
                                   uint64_t epoch, uint64_t batch);
    
    /**
     * Compute interaction contribution ratio.
     * Returns fraction [0, 1] of total variance from interaction dims.
     */
    float compute_interaction_contribution(const float* features, int batch_size, int dim);
    
    /**
     * Feature balance penalty value.
     * Returns penalty > 0 if interaction contribution > threshold.
     */
    float compute_balance_penalty(const float* features, int batch_size, int dim);

private:
    FeatureConfig config_;
    std::mt19937_64 rng_;
};

} // namespace g38

#endif // FEATURE_DIVERSIFIER_H
