/**
 * Latent Space Monitor — Embedding Drift Detection
 *
 * Tracks embedding mean/std and covariance shift.
 * Alerts if KL divergence exceeds configurable threshold.
 *
 * Prevents silent representation shift in shadow mode.
 */

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <vector>

struct LatentSpaceStats {
  std::vector<double> mean;         // per-dimension mean
  std::vector<double> variance;     // per-dimension variance
  std::vector<double> cov_diagonal; // diagonal of covariance matrix
  double kl_divergence;             // KL(current || baseline)
  double frobenius_shift;           // Frobenius norm of cov shift
  double mean_shift_sigma;          // mean shift in units of baseline σ
  int n_samples;
  bool alert;
};

class LatentSpaceMonitor {
private:
  int dim_;
  double kl_threshold_;

  // Baseline (from gate-pass snapshot)
  std::vector<double> baseline_mean_;
  std::vector<double> baseline_var_;
  bool has_baseline_;

  // Running statistics (Welford's algorithm)
  std::vector<double> running_mean_;
  std::vector<double> running_m2_;
  int running_n_;

  double compute_kl_gaussian(const std::vector<double> &mu0,
                             const std::vector<double> &var0,
                             const std::vector<double> &mu1,
                             const std::vector<double> &var1) const {
    // KL(N(mu1, var1) || N(mu0, var0))
    // = 0.5 * sum_d [ log(var0/var1) + var1/var0 + (mu0-mu1)^2/var0 - 1 ]
    double kl = 0.0;
    for (int d = 0; d < dim_; d++) {
      double v0 = std::max(var0[d], 1e-10);
      double v1 = std::max(var1[d], 1e-10);
      kl += std::log(v0 / v1) + v1 / v0 +
            (mu0[d] - mu1[d]) * (mu0[d] - mu1[d]) / v0 - 1.0;
    }
    return 0.5 * kl;
  }

public:
  LatentSpaceMonitor()
      : dim_(0), kl_threshold_(0.5), has_baseline_(false), running_n_(0) {}

  void initialize(int dim, double kl_threshold = 0.5) {
    dim_ = dim;
    kl_threshold_ = kl_threshold;
    running_mean_.assign(dim, 0.0);
    running_m2_.assign(dim, 0.0);
    running_n_ = 0;
    has_baseline_ = false;
  }

  void set_baseline(const double *mean, const double *variance, int dim) {
    dim_ = dim;
    baseline_mean_.assign(mean, mean + dim);
    baseline_var_.assign(variance, variance + dim);
    has_baseline_ = true;
  }

  void update(const double *embedding, int dim) {
    if (dim != dim_)
      return;
    running_n_++;
    for (int d = 0; d < dim_; d++) {
      double delta = embedding[d] - running_mean_[d];
      running_mean_[d] += delta / running_n_;
      double delta2 = embedding[d] - running_mean_[d];
      running_m2_[d] += delta * delta2;
    }
  }

  void update_batch(const double *embeddings, int n_samples, int dim) {
    for (int i = 0; i < n_samples; i++) {
      update(embeddings + i * dim, dim);
    }
  }

  LatentSpaceStats get_stats() const {
    LatentSpaceStats stats;
    stats.n_samples = running_n_;
    stats.mean = running_mean_;
    stats.kl_divergence = 0.0;
    stats.frobenius_shift = 0.0;
    stats.mean_shift_sigma = 0.0;
    stats.alert = false;

    // Compute variance
    stats.variance.resize(dim_);
    stats.cov_diagonal.resize(dim_);
    for (int d = 0; d < dim_; d++) {
      double var = (running_n_ > 1) ? running_m2_[d] / (running_n_ - 1) : 0.0;
      stats.variance[d] = var;
      stats.cov_diagonal[d] = var;
    }

    if (has_baseline_ && running_n_ > 10) {
      // KL divergence
      stats.kl_divergence = compute_kl_gaussian(baseline_mean_, baseline_var_,
                                                running_mean_, stats.variance);

      // Frobenius shift (diagonal approximation)
      double frob = 0.0;
      for (int d = 0; d < dim_; d++) {
        double diff = stats.cov_diagonal[d] - baseline_var_[d];
        frob += diff * diff;
      }
      stats.frobenius_shift = std::sqrt(frob);

      // Mean shift in sigma units
      double max_shift = 0.0;
      for (int d = 0; d < dim_; d++) {
        double sigma = std::sqrt(std::max(baseline_var_[d], 1e-10));
        double shift = std::abs(running_mean_[d] - baseline_mean_[d]) / sigma;
        max_shift = std::max(max_shift, shift);
      }
      stats.mean_shift_sigma = max_shift;

      stats.alert = (stats.kl_divergence > kl_threshold_);
    }

    return stats;
  }

  void reset() {
    running_mean_.assign(dim_, 0.0);
    running_m2_.assign(dim_, 0.0);
    running_n_ = 0;
  }

  bool is_alert() const { return get_stats().alert; }
};
