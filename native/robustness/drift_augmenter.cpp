/**
 * Drift Augmentation & Distribution Shifting for robustness.
 *
 * Compile: cl /O2 /EHsc /std:c++17 drift_augmenter.cpp
 */
#include <algorithm>
#include <cstdint>
#include <random>


namespace g38 {
namespace robustness {

/**
 * Apply domain randomization: ±scale% feature scaling.
 */
void apply_domain_randomization(float *features, int batch_size, int dim,
                                float scale_pct, uint64_t seed) {
  std::mt19937_64 rng(seed);
  std::uniform_real_distribution<float> scale(1.0f - scale_pct,
                                              1.0f + scale_pct);

  for (int d = 0; d < dim; ++d) {
    float s = scale(rng);
    for (int b = 0; b < batch_size; ++b) {
      features[b * dim + d] =
          std::max(0.0f, std::min(1.0f, features[b * dim + d] * s));
    }
  }
}

/**
 * Apply random feature missingness.
 */
void apply_random_missingness(float *features, int batch_size, int dim,
                              float miss_rate, uint64_t seed) {
  std::mt19937_64 rng(seed);
  std::uniform_real_distribution<float> uniform(0.0f, 1.0f);

  for (int b = 0; b < batch_size; ++b) {
    for (int d = 0; d < dim; ++d) {
      if (uniform(rng) < miss_rate) {
        features[b * dim + d] = 0.5f; // Replace with neutral value
      }
    }
  }
}

/**
 * Inject novel structural patterns into fraction of batch.
 * Preserves label integrity by only modifying non-dominant dims.
 */
void inject_novel_patterns(float *features, int batch_size, int dim,
                           float inject_rate, uint64_t seed) {
  std::mt19937_64 rng(seed);
  std::uniform_real_distribution<float> uniform(0.0f, 1.0f);
  std::normal_distribution<float> novel(0.5f, 0.15f);

  int n_inject = static_cast<int>(batch_size * inject_rate);

  for (int b = 0; b < n_inject; ++b) {
    // Modify noise dims (192-255) with novel patterns
    for (int d = 192; d < std::min(dim, 256); ++d) {
      features[b * dim + d] = std::max(0.0f, std::min(1.0f, novel(rng)));
    }
    // Add small perturbation to interaction dims
    for (int d = 128; d < std::min(dim, 192); ++d) {
      features[b * dim + d] += (uniform(rng) - 0.5f) * 0.1f;
      features[b * dim + d] =
          std::max(0.0f, std::min(1.0f, features[b * dim + d]));
    }
  }
}

/**
 * Apply correlated noise injection.
 */
void apply_correlated_noise(float *features, int batch_size, int dim,
                            float sigma, uint64_t seed) {
  std::mt19937_64 rng(seed);
  std::normal_distribution<float> noise(0.0f, sigma);

  for (int b = 0; b < batch_size; ++b) {
    float base_noise = noise(rng);
    for (int d = 0; d < dim; ++d) {
      float n = base_noise + noise(rng) * 0.5f;
      features[b * dim + d] =
          std::max(0.0f, std::min(1.0f, features[b * dim + d] + n));
    }
  }
}

} // namespace robustness
} // namespace g38
