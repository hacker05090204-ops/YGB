/**
 * Rolling Drift Detector — Sliding Window Distribution Monitor
 *
 * 10k-sample sliding window. Compares current feature distribution
 * to gate-pass baseline. Alerts if mean shift > 2σ on any feature group.
 *
 * Prevents undetected input distribution drift in long-running shadow mode.
 */

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <deque>
#include <vector>


struct DriftStats {
  double max_mean_shift_sigma;       // Maximum shift across all dims (in σ)
  double mean_mean_shift_sigma;      // Average shift across all dims
  std::vector<double> per_dim_shift; // Per-dimension shift in σ units
  int window_size;
  int feature_dim;
  bool alert;    // True if max shift > threshold
  int alert_dim; // Which dimension triggered alert
};

class DriftDetector {
private:
  int dim_;
  int window_size_;
  double sigma_threshold_;

  // Baseline
  std::vector<double> baseline_mean_;
  std::vector<double> baseline_std_;
  bool has_baseline_;

  // Sliding window (stores feature vectors as flat array)
  std::deque<std::vector<double>> window_;

  // Running stats for window
  std::vector<double> window_sum_;
  std::vector<double> window_sum_sq_;

  void add_to_running(const double *features) {
    for (int d = 0; d < dim_; d++) {
      window_sum_[d] += features[d];
      window_sum_sq_[d] += features[d] * features[d];
    }
  }

  void remove_from_running(const double *features) {
    for (int d = 0; d < dim_; d++) {
      window_sum_[d] -= features[d];
      window_sum_sq_[d] -= features[d] * features[d];
    }
  }

public:
  DriftDetector()
      : dim_(0), window_size_(10000), sigma_threshold_(2.0),
        has_baseline_(false) {}

  void initialize(int dim, int window_size = 10000,
                  double sigma_threshold = 2.0) {
    dim_ = dim;
    window_size_ = window_size;
    sigma_threshold_ = sigma_threshold;
    window_sum_.assign(dim, 0.0);
    window_sum_sq_.assign(dim, 0.0);
    has_baseline_ = false;
  }

  void set_baseline(const double *mean, const double *std_dev, int dim) {
    baseline_mean_.assign(mean, mean + dim);
    baseline_std_.assign(std_dev, std_dev + dim);
    has_baseline_ = true;
  }

  void add_sample(const double *features) {
    std::vector<double> sample(features, features + dim_);

    add_to_running(features);
    window_.push_back(sample);

    // Evict oldest if window full
    if (static_cast<int>(window_.size()) > window_size_) {
      remove_from_running(window_.front().data());
      window_.pop_front();
    }
  }

  void add_batch(const double *features, int n_samples) {
    for (int i = 0; i < n_samples; i++) {
      add_sample(features + i * dim_);
    }
  }

  DriftStats get_stats() const {
    DriftStats stats;
    stats.feature_dim = dim_;
    stats.window_size = static_cast<int>(window_.size());
    stats.alert = false;
    stats.alert_dim = -1;
    stats.max_mean_shift_sigma = 0.0;
    stats.mean_mean_shift_sigma = 0.0;

    if (!has_baseline_ || window_.empty())
      return stats;

    int n = stats.window_size;
    stats.per_dim_shift.resize(dim_);

    double total_shift = 0.0;
    for (int d = 0; d < dim_; d++) {
      double window_mean = window_sum_[d] / n;
      double baseline_sigma = std::max(baseline_std_[d], 1e-10);
      double shift = std::abs(window_mean - baseline_mean_[d]) / baseline_sigma;
      stats.per_dim_shift[d] = shift;
      total_shift += shift;

      if (shift > stats.max_mean_shift_sigma) {
        stats.max_mean_shift_sigma = shift;
        stats.alert_dim = d;
      }
    }

    stats.mean_mean_shift_sigma = total_shift / dim_;
    stats.alert = (stats.max_mean_shift_sigma > sigma_threshold_);

    return stats;
  }

  void reset() {
    window_.clear();
    window_sum_.assign(dim_, 0.0);
    window_sum_sq_.assign(dim_, 0.0);
  }

  bool is_alert() const { return get_stats().alert; }
  int current_window_size() const { return static_cast<int>(window_.size()); }
};
