/**
 * Rolling Drift Engine — Temporal Distribution Shift Simulator.
 *
 * Simulates 7-day rolling distribution shift on 256-dim feature vectors.
 * Applies gradual Gaussian drift (sigma grows linearly per day) to each
 * feature group independently.
 *
 * Metrics per step:
 *   - KL divergence vs original (threshold < 0.5)
 *   - Per-group mean shift
 *   - Per-group variance change ratio
 *
 * GOVERNANCE: No decision labels. Deterministic seeded.
 * Compile: cl /O2 /EHsc /std:c++17 rolling_drift_engine.cpp
 */
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <random>
#include <vector>


namespace g38 {
namespace temporal {

// Feature group layout
struct FeatureGroup {
  int start;
  int end;
  const char *name;
};

static const std::array<FeatureGroup, 4> GROUPS = {{{0, 64, "signal"},
                                                    {64, 128, "response"},
                                                    {128, 192, "interaction"},
                                                    {192, 256, "noise"}}};

// Per-step drift result
struct DriftStepResult {
  int day;
  double kl_divergence;     // KL(drifted || original)
  double mean_shift[4];     // Per-group mean shift
  double variance_ratio[4]; // Per-group var(drifted)/var(original)
  double entropy_retention; // Entropy ratio vs original
  bool kl_pass;             // KL < 0.5
};

// ============================================================================
// KL Divergence (binned, with epsilon smoothing)
// ============================================================================

inline double compute_kl(const float *orig, const float *drifted, int n,
                         int n_bins = 50, double eps = 1e-10) {
  if (n == 0)
    return 0.0;
  float mn = orig[0], mx = orig[0];
  for (int i = 1; i < n; ++i) {
    mn = std::min(mn, std::min(orig[i], drifted[i]));
    mx = std::max(mx, std::max(orig[i], drifted[i]));
  }
  if (mx - mn < 1e-8f)
    return 0.0;

  std::vector<double> p(n_bins, 0), q(n_bins, 0);
  double bin_w = (mx - mn) / n_bins;

  for (int i = 0; i < n; ++i) {
    int bo = std::min(n_bins - 1, int((orig[i] - mn) / bin_w));
    int bd = std::min(n_bins - 1, int((drifted[i] - mn) / bin_w));
    p[bo] += 1.0;
    q[bd] += 1.0;
  }
  // Normalize + smooth
  for (int b = 0; b < n_bins; ++b) {
    p[b] = (p[b] + eps) / (n + eps * n_bins);
    q[b] = (q[b] + eps) / (n + eps * n_bins);
  }
  double kl = 0.0;
  for (int b = 0; b < n_bins; ++b)
    kl += p[b] * std::log(p[b] / q[b]);
  return kl;
}

// ============================================================================
// Rolling Drift Engine
// ============================================================================

class RollingDriftEngine {
public:
  explicit RollingDriftEngine(uint64_t seed = 42, int n_days = 7)
      : rng_(seed), seed_(seed), n_days_(n_days) {}

  /**
   * Apply one day's drift to a feature matrix.
   *
   * @param features  [N x dim] feature matrix (modified in-place)
   * @param N         number of samples
   * @param dim       feature dimension (256)
   * @param day       day index (0-6), controls drift magnitude
   * @param base_sigma base drift sigma (grows as base_sigma * (day+1)/n_days)
   */
  void apply_drift(float *features, int N, int dim, int day,
                   float base_sigma = 0.05f) {
    float sigma = base_sigma * static_cast<float>(day + 1) / n_days_;
    std::normal_distribution<float> noise(0.0f, sigma);

    // Apply drift to each group with different group-specific scaling
    for (int g = 0; g < 4; ++g) {
      int gs = GROUPS[g].start;
      int ge = GROUPS[g].end;
      // Interaction group gets 50% more drift (stress test)
      float group_scale = (g == 2) ? 1.5f : 1.0f;

      for (int i = 0; i < N; ++i) {
        for (int d = gs; d < ge; ++d) {
          float drift = noise(rng_) * group_scale;
          features[i * dim + d] =
              std::max(0.0f, std::min(1.0f, features[i * dim + d] + drift));
        }
      }
    }
  }

  /**
   * Compute drift metrics comparing original vs drifted features.
   */
  DriftStepResult compute_metrics(const float *original, const float *drifted,
                                  int N, int dim, int day) {
    DriftStepResult r;
    r.day = day;

    // Per-group metrics
    double total_kl = 0.0;
    for (int g = 0; g < 4; ++g) {
      int gs = GROUPS[g].start;
      int ge = GROUPS[g].end;
      int gdim = ge - gs;

      // Flatten group features for KL
      std::vector<float> orig_flat(N * gdim);
      std::vector<float> drift_flat(N * gdim);
      double orig_sum = 0, drift_sum = 0;
      double orig_sq = 0, drift_sq = 0;

      for (int i = 0; i < N; ++i) {
        for (int d = 0; d < gdim; ++d) {
          float ov = original[i * dim + gs + d];
          float dv = drifted[i * dim + gs + d];
          orig_flat[i * gdim + d] = ov;
          drift_flat[i * gdim + d] = dv;
          orig_sum += ov;
          drift_sum += dv;
          orig_sq += ov * ov;
          drift_sq += dv * dv;
        }
      }
      int total = N * gdim;
      double orig_mean = orig_sum / total;
      double drift_mean = drift_sum / total;
      double orig_var = orig_sq / total - orig_mean * orig_mean;
      double drift_var = drift_sq / total - drift_mean * drift_mean;

      r.mean_shift[g] = std::abs(drift_mean - orig_mean);
      r.variance_ratio[g] = (orig_var > 1e-10) ? drift_var / orig_var : 1.0;

      double gkl = compute_kl(orig_flat.data(), drift_flat.data(), total);
      total_kl += gkl;
    }

    r.kl_divergence = total_kl / 4.0; // Average across groups
    r.kl_pass = r.kl_divergence < 0.5;

    // Entropy retention (variance-based proxy)
    double orig_total_var = 0, drift_total_var = 0;
    for (int d = 0; d < dim; ++d) {
      double om = 0, dm = 0;
      for (int i = 0; i < N; ++i) {
        om += original[i * dim + d];
        dm += drifted[i * dim + d];
      }
      om /= N;
      dm /= N;
      double ov = 0, dv = 0;
      for (int i = 0; i < N; ++i) {
        double od = original[i * dim + d] - om;
        double dd = drifted[i * dim + d] - dm;
        ov += od * od;
        dv += dd * dd;
      }
      orig_total_var += ov / N;
      drift_total_var += dv / N;
    }
    r.entropy_retention =
        (orig_total_var > 1e-10) ? drift_total_var / orig_total_var : 1.0;

    return r;
  }

  /**
   * Run full 7-day simulation.
   * Returns per-day results.
   */
  std::vector<DriftStepResult> run_simulation(const float *original, int N,
                                              int dim,
                                              float base_sigma = 0.05f) {
    std::vector<float> current(original, original + N * dim);
    std::vector<DriftStepResult> results;

    for (int day = 0; day < n_days_; ++day) {
      apply_drift(current.data(), N, dim, day, base_sigma);
      auto r = compute_metrics(original, current.data(), N, dim, day);
      results.push_back(r);
    }
    return results;
  }

private:
  std::mt19937_64 rng_;
  uint64_t seed_;
  int n_days_;
};

} // namespace temporal
} // namespace g38
