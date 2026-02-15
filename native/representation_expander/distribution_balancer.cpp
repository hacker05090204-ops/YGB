/**
 * Distribution Balancer for MODE-A Representation Expansion.
 *
 * Balances feature group distributions to prevent shortcut reliance.
 * Implements Phase 4 algorithms in the same file.
 *
 * GOVERNANCE: NO decision labels, deterministic, noise sigma <= 0.03.
 *
 * Compile: cl /O2 /EHsc /std:c++17 distribution_balancer.cpp
 */
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <random>
#include <vector>


namespace g38 {
namespace repr {

struct BalancerConfig {
  int input_dim = 256;
  int signal_start = 0, signal_end = 64;
  int response_start = 64, response_end = 128;
  int interaction_start = 128, interaction_end = 192;
  int noise_start = 192, noise_end = 256;
  float max_interaction_ratio = 0.30f;
  float noise_sigma = 0.03f;
  float entropy_floor = 0.5f;
  uint64_t seed = 42;
};

class DistributionBalancer {
public:
  explicit DistributionBalancer(const BalancerConfig &cfg)
      : cfg_(cfg), rng_(cfg.seed) {}

  /**
   * Equalize feature group weight contribution.
   * Scales each group so total variance contribution is ~25% each.
   */
  void equalize_group_weights(float *features, int batch_size, int dim) {
    struct Group {
      int s, e;
    };
    Group groups[4] = {{cfg_.signal_start, cfg_.signal_end},
                       {cfg_.response_start, cfg_.response_end},
                       {cfg_.interaction_start, cfg_.interaction_end},
                       {cfg_.noise_start, cfg_.noise_end}};

    // Compute per-group variance
    float group_var[4] = {0};
    float total_var = 0;
    for (int g = 0; g < 4; ++g) {
      for (int d = groups[g].s; d < groups[g].e; ++d) {
        float mean = 0;
        for (int b = 0; b < batch_size; ++b)
          mean += features[b * dim + d];
        mean /= batch_size;
        float var = 0;
        for (int b = 0; b < batch_size; ++b) {
          float diff = features[b * dim + d] - mean;
          var += diff * diff;
        }
        var /= batch_size;
        group_var[g] += var;
      }
      total_var += group_var[g];
    }

    if (total_var < 1e-10f)
      return;

    // Scale each group to target 25% of total variance
    float target = total_var / 4.0f;
    for (int g = 0; g < 4; ++g) {
      if (group_var[g] < 1e-10f)
        continue;
      float scale = std::sqrt(target / group_var[g]);
      // Clamp scale to avoid extreme distortion
      scale = std::max(0.5f, std::min(2.0f, scale));

      for (int b = 0; b < batch_size; ++b) {
        for (int d = groups[g].s; d < groups[g].e; ++d) {
          features[b * dim + d] *= scale;
          features[b * dim + d] =
              std::max(0.0f, std::min(1.0f, features[b * dim + d]));
        }
      }
    }
  }

  /**
   * Cap interaction features at max_interaction_ratio of total variance.
   * Adaptively scales interaction dims down if dominant.
   */
  void cap_interaction_variance(float *features, int batch_size, int dim) {
    float interaction_var = 0, total_var = 0;

    for (int d = 0; d < dim; ++d) {
      float mean = 0;
      for (int b = 0; b < batch_size; ++b)
        mean += features[b * dim + d];
      mean /= batch_size;
      float var = 0;
      for (int b = 0; b < batch_size; ++b) {
        float diff = features[b * dim + d] - mean;
        var += diff * diff;
      }
      var /= batch_size;
      total_var += var;
      if (d >= cfg_.interaction_start && d < cfg_.interaction_end)
        interaction_var += var;
    }

    if (total_var < 1e-10f)
      return;
    float ratio = interaction_var / total_var;

    if (ratio > cfg_.max_interaction_ratio) {
      float target_var = cfg_.max_interaction_ratio * total_var;
      float scale = std::sqrt(target_var / interaction_var);

      for (int b = 0; b < batch_size; ++b) {
        for (int d = cfg_.interaction_start; d < cfg_.interaction_end; ++d) {
          features[b * dim + d] *= scale;
          features[b * dim + d] =
              std::max(0.0f, std::min(1.0f, features[b * dim + d]));
        }
      }
    }
  }

  /**
   * Add independent channel augmentation.
   * Per-group normalization producing 4 derived channels.
   * Output dim = input_dim + 4.
   */
  void add_independent_channels(const float *input, float *output,
                                int batch_size, int input_dim) {
    int out_dim = input_dim + 4;
    struct Group {
      int s, e;
    };
    Group groups[4] = {{cfg_.signal_start, cfg_.signal_end},
                       {cfg_.response_start, cfg_.response_end},
                       {cfg_.interaction_start, cfg_.interaction_end},
                       {cfg_.noise_start, cfg_.noise_end}};

    for (int b = 0; b < batch_size; ++b) {
      const float *in_row = input + b * input_dim;
      float *out_row = output + b * out_dim;
      std::copy(in_row, in_row + input_dim, out_row);

      for (int g = 0; g < 4; ++g) {
        float sum = 0, sum_sq = 0;
        int n = groups[g].e - groups[g].s;
        for (int d = groups[g].s; d < groups[g].e; ++d) {
          sum += in_row[d];
          sum_sq += in_row[d] * in_row[d];
        }
        float mean = sum / n;
        float var = sum_sq / n - mean * mean;
        // Normalized group energy
        out_row[input_dim + g] = std::sqrt(std::max(0.0f, var));
      }
    }
  }

  /**
   * Apply controlled Gaussian noise (sigma <= 0.03).
   */
  void apply_noise(float *features, int batch_size, int dim) {
    std::normal_distribution<float> noise(0.0f, cfg_.noise_sigma);

    for (int b = 0; b < batch_size; ++b) {
      for (int d = cfg_.signal_start; d < cfg_.signal_end; ++d) {
        float &v = features[b * dim + d];
        v = std::max(0.0f, std::min(1.0f, v + noise(rng_)));
      }
      for (int d = cfg_.response_start; d < cfg_.response_end; ++d) {
        float &v = features[b * dim + d];
        v = std::max(0.0f, std::min(1.0f, v + noise(rng_)));
      }
    }
  }

  /**
   * Enforce entropy floor per group.
   * If group entropy is below threshold, inject diversity.
   */
  void enforce_entropy_floor(float *features, int batch_size, int dim) {
    struct Group {
      int s, e;
    };
    Group groups[4] = {{cfg_.signal_start, cfg_.signal_end},
                       {cfg_.response_start, cfg_.response_end},
                       {cfg_.interaction_start, cfg_.interaction_end},
                       {cfg_.noise_start, cfg_.noise_end}};

    std::uniform_real_distribution<float> u(0.0f, 1.0f);

    for (int g = 0; g < 4; ++g) {
      int n_dims = groups[g].e - groups[g].s;

      // Estimate entropy via variance
      float mean_var = 0;
      for (int d = groups[g].s; d < groups[g].e; ++d) {
        float mean = 0;
        for (int b = 0; b < batch_size; ++b)
          mean += features[b * dim + d];
        mean /= batch_size;
        float var = 0;
        for (int b = 0; b < batch_size; ++b) {
          float diff = features[b * dim + d] - mean;
          var += diff * diff;
        }
        mean_var += var / batch_size;
      }
      mean_var /= n_dims;

      // If variance too low, inject controlled diversity
      if (mean_var < cfg_.entropy_floor * 0.01f) {
        std::normal_distribution<float> inject(0.0f, 0.05f);
        for (int b = 0; b < batch_size; ++b) {
          for (int d = groups[g].s; d < groups[g].e; ++d) {
            float &v = features[b * dim + d];
            v = std::max(0.0f, std::min(1.0f, v + inject(rng_)));
          }
        }
      }
    }
  }

  /**
   * Compute current interaction ratio.
   */
  float get_interaction_ratio(const float *features, int batch_size, int dim) {
    float i_var = 0, t_var = 0;
    for (int d = 0; d < dim; ++d) {
      float mean = 0;
      for (int b = 0; b < batch_size; ++b)
        mean += features[b * dim + d];
      mean /= batch_size;
      float var = 0;
      for (int b = 0; b < batch_size; ++b) {
        float diff = features[b * dim + d] - mean;
        var += diff * diff;
      }
      var /= batch_size;
      t_var += var;
      if (d >= cfg_.interaction_start && d < cfg_.interaction_end)
        i_var += var;
    }
    return (t_var > 1e-10f) ? (i_var / t_var) : 0.0f;
  }

private:
  BalancerConfig cfg_;
  std::mt19937_64 rng_;
};

} // namespace repr
} // namespace g38
