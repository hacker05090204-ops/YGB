/**
 * Feature Diversification Engine — Implementation.
 *
 * Deterministic, seed-controlled transformations.
 * All operations use epoch+batch for reproducible RNG state.
 */
#include "feature_diversifier.h"
#include <algorithm>
#include <cmath>

namespace g38 {

FeatureDiversifier::FeatureDiversifier(const FeatureConfig &config)
    : config_(config), rng_(config.seed) {}

void FeatureDiversifier::apply_interaction_dropout(float *features,
                                                   int batch_size, int dim,
                                                   uint64_t epoch,
                                                   uint64_t batch) {

  if (!config_.training)
    return;

  std::mt19937_64 local_rng(config_.seed ^ (epoch * 10000 + batch));
  std::uniform_real_distribution<float> uniform(0.0f, 1.0f);
  std::normal_distribution<float> noise(0.0f, 0.02f);

  int n_interaction = config_.interaction_end - config_.interaction_start;

  for (int b = 0; b < batch_size; ++b) {
    float *row = features + b * dim;

    // Compute mean of interaction dims for this sample
    float mean = 0.0f;
    for (int d = config_.interaction_start; d < config_.interaction_end; ++d) {
      mean += row[d];
    }
    mean /= static_cast<float>(n_interaction);

    // Dropout
    for (int d = config_.interaction_start; d < config_.interaction_end; ++d) {
      if (uniform(local_rng) < config_.interaction_dropout_p) {
        row[d] = mean + noise(local_rng); // Replace with mean + small noise
      }
    }
  }
}

void FeatureDiversifier::apply_adversarial_scramble(float *features,
                                                    int batch_size, int dim,
                                                    uint64_t epoch,
                                                    uint64_t batch) {

  if (!config_.training)
    return;

  std::mt19937_64 local_rng(config_.seed ^ (epoch * 99999 + batch * 7));
  std::uniform_real_distribution<float> uniform(0.0f, 1.0f);

  // Only 10% of batches get scrambled
  if (uniform(local_rng) > 0.10f)
    return;

  int n_interaction = config_.interaction_end - config_.interaction_start;

  for (int b = 0; b < batch_size; ++b) {
    float *row = features + b * dim;

    // Small permutation: swap ~20% of interaction dim pairs
    int n_swaps = n_interaction / 5;
    for (int s = 0; s < n_swaps; ++s) {
      int i = config_.interaction_start + (local_rng() % n_interaction);
      int j = config_.interaction_start + (local_rng() % n_interaction);
      std::swap(row[i], row[j]);
    }
  }
}

void FeatureDiversifier::expand_independent_channels(const float *input,
                                                     float *output,
                                                     int batch_size,
                                                     int input_dim) {

  int output_dim = input_dim + 4;

  for (int b = 0; b < batch_size; ++b) {
    const float *in_row = input + b * input_dim;
    float *out_row = output + b * output_dim;

    // Copy original dims
    std::copy(in_row, in_row + input_dim, out_row);

    // Channel 1: Signal L2 norm (normalized)
    float sig_norm = 0.0f;
    for (int d = config_.signal_start; d < config_.signal_end; ++d) {
      sig_norm += in_row[d] * in_row[d];
    }
    out_row[input_dim] = std::sqrt(sig_norm) / std::sqrt(64.0f);

    // Channel 2: Signal entropy approximation
    float sig_ent = 0.0f;
    for (int d = config_.signal_start; d < config_.signal_end; ++d) {
      float v = std::max(in_row[d], 1e-6f);
      sig_ent -= v * std::log(v);
    }
    out_row[input_dim + 1] = sig_ent / 10.0f; // Normalize

    // Channel 3: Response L2 norm (normalized)
    float res_norm = 0.0f;
    for (int d = config_.response_start; d < config_.response_end; ++d) {
      res_norm += in_row[d] * in_row[d];
    }
    out_row[input_dim + 2] = std::sqrt(res_norm) / std::sqrt(64.0f);

    // Channel 4: Response variance
    float res_mean = 0.0f, res_var = 0.0f;
    for (int d = config_.response_start; d < config_.response_end; ++d) {
      res_mean += in_row[d];
    }
    res_mean /= 64.0f;
    for (int d = config_.response_start; d < config_.response_end; ++d) {
      float diff = in_row[d] - res_mean;
      res_var += diff * diff;
    }
    out_row[input_dim + 3] = res_var / 64.0f;
  }
}

void FeatureDiversifier::apply_mixup(float *features, float *labels,
                                     int batch_size, int dim, uint64_t epoch,
                                     uint64_t batch) {

  if (!config_.training || batch_size < 2)
    return;

  std::mt19937_64 local_rng(config_.seed ^ (epoch * 77777 + batch * 13));

  // Beta(alpha, alpha) approximation via gamma
  std::gamma_distribution<float> gamma(config_.mixup_alpha, 1.0f);

  for (int b = 0; b < batch_size / 2; ++b) {
    float g1 = gamma(local_rng);
    float g2 = gamma(local_rng);
    float lam = g1 / (g1 + g2 + 1e-10f);
    lam = std::max(lam, 1.0f - lam); // Ensure lam >= 0.5

    int i = b;
    int j = batch_size - 1 - b;

    for (int d = 0; d < dim; ++d) {
      float mixed =
          lam * features[i * dim + d] + (1.0f - lam) * features[j * dim + d];
      features[i * dim + d] = mixed;
    }
    // Soft labels
    float mixed_label = lam * labels[i] + (1.0f - lam) * labels[j];
    labels[i] = mixed_label;
  }
}

void FeatureDiversifier::apply_noise_augmentation(float *features,
                                                  int batch_size, int dim,
                                                  uint64_t epoch,
                                                  uint64_t batch) {

  if (!config_.training)
    return;

  std::mt19937_64 local_rng(config_.seed ^ (epoch * 55555 + batch * 3));
  std::normal_distribution<float> noise(0.0f, config_.noise_sigma);

  for (int b = 0; b < batch_size; ++b) {
    float *row = features + b * dim;

    // Apply noise to signal and response dims only (NOT interaction — break
    // dependency)
    for (int d = config_.signal_start; d < config_.signal_end; ++d) {
      row[d] = std::max(0.0f, std::min(1.0f, row[d] + noise(local_rng)));
    }
    for (int d = config_.response_start; d < config_.response_end; ++d) {
      row[d] = std::max(0.0f, std::min(1.0f, row[d] + noise(local_rng)));
    }
  }
}

float FeatureDiversifier::compute_interaction_contribution(
    const float *features, int batch_size, int dim) {

  // Compute variance of each dim, sum interaction vs total
  std::vector<float> means(dim, 0.0f);
  for (int b = 0; b < batch_size; ++b) {
    for (int d = 0; d < dim; ++d) {
      means[d] += features[b * dim + d];
    }
  }
  for (int d = 0; d < dim; ++d)
    means[d] /= batch_size;

  float interaction_var = 0.0f, total_var = 0.0f;
  for (int d = 0; d < dim; ++d) {
    float var = 0.0f;
    for (int b = 0; b < batch_size; ++b) {
      float diff = features[b * dim + d] - means[d];
      var += diff * diff;
    }
    var /= batch_size;
    total_var += var;
    if (d >= config_.interaction_start && d < config_.interaction_end) {
      interaction_var += var;
    }
  }

  return (total_var > 1e-10f) ? (interaction_var / total_var) : 0.0f;
}

float FeatureDiversifier::compute_balance_penalty(const float *features,
                                                  int batch_size, int dim) {

  float ratio = compute_interaction_contribution(features, batch_size, dim);
  if (ratio > config_.interaction_penalty_threshold) {
    return (ratio - config_.interaction_penalty_threshold) * 2.0f; // Penalty
  }
  return 0.0f;
}

} // namespace g38
