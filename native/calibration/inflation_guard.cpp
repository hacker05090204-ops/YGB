/**
 * Confidence Inflation Guard — Rolling ECE & Inflation Tracker
 *
 * Monitors:
 *   1) Rolling 5k-prediction ECE window
 *   2) Rolling confidence inflation (mean_conf − mean_acc)
 *   3) Monotonicity slope of confidence vs accuracy
 *
 * Auto-disable shadow_mode if:
 *   - Inflation > 2%
 *   - Monotonicity slope < 0.9
 *
 * Shadow-only system must prefer abstention over false confidence.
 */

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <deque>
#include <vector>


struct InflationStats {
  double rolling_ece;
  double rolling_inflation; // mean_conf - mean_acc
  double monotonicity_slope;
  int window_size;
  bool inflation_alert;    // inflation > 2%
  bool monotonicity_alert; // slope < 0.9
  bool should_disable;     // ANY alert fires
};

struct PredictionRecord {
  double confidence;
  bool correct;
};

class InflationGuard {
private:
  int window_size_;
  double inflation_threshold_;
  double monotonicity_min_;
  int n_bins_;

  std::deque<PredictionRecord> window_;

public:
  InflationGuard()
      : window_size_(5000), inflation_threshold_(0.02), monotonicity_min_(0.9),
        n_bins_(10) {}

  void initialize(int window_size = 5000, double inflation_threshold = 0.02,
                  double monotonicity_min = 0.9, int n_bins = 10) {
    window_size_ = window_size;
    inflation_threshold_ = inflation_threshold;
    monotonicity_min_ = monotonicity_min;
    n_bins_ = n_bins;
  }

  void record_prediction(double confidence, bool correct) {
    window_.push_back({confidence, correct});
    if (static_cast<int>(window_.size()) > window_size_)
      window_.pop_front();
  }

  void record_batch(const double *confidences, const bool *correct, int n) {
    for (int i = 0; i < n; i++)
      record_prediction(confidences[i], correct[i]);
  }

  InflationStats get_stats() const {
    InflationStats stats;
    stats.window_size = static_cast<int>(window_.size());
    stats.rolling_ece = 0.0;
    stats.rolling_inflation = 0.0;
    stats.monotonicity_slope = 1.0;
    stats.inflation_alert = false;
    stats.monotonicity_alert = false;
    stats.should_disable = false;

    if (window_.size() < 100)
      return stats;

    int n = static_cast<int>(window_.size());

    // Rolling ECE and inflation
    double sum_conf = 0.0, sum_correct = 0.0;
    std::vector<double> bin_conf_sum(n_bins_, 0.0);
    std::vector<double> bin_acc_sum(n_bins_, 0.0);
    std::vector<int> bin_count(n_bins_, 0);

    for (const auto &rec : window_) {
      sum_conf += rec.confidence;
      sum_correct += rec.correct ? 1.0 : 0.0;

      int bin = static_cast<int>(rec.confidence * (n_bins_ - 1));
      bin = std::max(0, std::min(n_bins_ - 1, bin));
      bin_conf_sum[bin] += rec.confidence;
      bin_acc_sum[bin] += rec.correct ? 1.0 : 0.0;
      bin_count[bin]++;
    }

    // ECE
    for (int b = 0; b < n_bins_; b++) {
      if (bin_count[b] > 0) {
        double mean_conf = bin_conf_sum[b] / bin_count[b];
        double mean_acc = bin_acc_sum[b] / bin_count[b];
        stats.rolling_ece += (static_cast<double>(bin_count[b]) / n) *
                             std::abs(mean_conf - mean_acc);
      }
    }

    // Inflation
    stats.rolling_inflation = (sum_conf / n) - (sum_correct / n);
    stats.inflation_alert = (stats.rolling_inflation > inflation_threshold_);

    // Monotonicity slope (linear regression of bin_acc on bin_conf)
    // Higher confidence bins should have higher accuracy
    double sum_x = 0, sum_y = 0, sum_xy = 0, sum_xx = 0;
    int valid_bins = 0;
    for (int b = 0; b < n_bins_; b++) {
      if (bin_count[b] >= 10) {
        double x = bin_conf_sum[b] / bin_count[b];
        double y = bin_acc_sum[b] / bin_count[b];
        sum_x += x;
        sum_y += y;
        sum_xy += x * y;
        sum_xx += x * x;
        valid_bins++;
      }
    }

    if (valid_bins >= 2) {
      double denom = valid_bins * sum_xx - sum_x * sum_x;
      if (std::abs(denom) > 1e-10) {
        stats.monotonicity_slope =
            (valid_bins * sum_xy - sum_x * sum_y) / denom;
      }
    }

    stats.monotonicity_alert = (stats.monotonicity_slope < monotonicity_min_);
    stats.should_disable = stats.inflation_alert || stats.monotonicity_alert;

    return stats;
  }

  bool should_disable() const { return get_stats().should_disable; }

  void reset() { window_.clear(); }
};
