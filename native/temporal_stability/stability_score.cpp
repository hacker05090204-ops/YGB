/**
 * Stability Score — Composite Temporal Stability Metric.
 *
 * Aggregates:
 *   - KL stability (30%)     — avg KL < 0.5 across time steps
 *   - Entropy retention (25%) — entropy drop < 10%
 *   - Accuracy retention (25%) — accuracy drop < 5%
 *   - Calibration retention (20%) — ECE delta < 0.02
 *
 * Score range [0, 100]. PASS threshold >= 80.
 * Uses rolling window (deque) for temporal smoothing.
 *
 * GOVERNANCE: No decision labels. Deterministic.
 * Compile: cl /O2 /EHsc /std:c++17 stability_score.cpp
 */
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <deque>
#include <vector>


namespace g38 {
namespace temporal {

static constexpr double PASS_THRESHOLD = 80.0;
static constexpr int WINDOW_SIZE = 10;

// Weights
static constexpr double W_KL = 0.30;
static constexpr double W_ENTROPY = 0.25;
static constexpr double W_ACCURACY = 0.25;
static constexpr double W_CALIBRATION = 0.20;

// Thresholds for full marks
static constexpr double KL_THRESHOLD = 0.5;
static constexpr double ENTROPY_DROP_MAX = 0.10;
static constexpr double ACCURACY_DROP_MAX = 0.05;
static constexpr double CALIBRATION_DELTA_MAX = 0.02;

struct StabilityMeasurement {
  double kl_divergence;
  double entropy_retention;  // ratio vs baseline (1.0 = no change)
  double accuracy_retention; // ratio vs baseline
  double calibration_delta;  // ECE change vs baseline
  double composite_score;
  bool passed;
};

class StabilityScoreEngine {
public:
  StabilityScoreEngine() = default;

  /**
   * Compute sub-score for KL stability.
   * Perfect (100) at KL=0, degrades linearly to 0 at KL=KL_THRESHOLD*2.
   */
  static double kl_score(double kl) {
    if (kl <= 0.0)
      return 100.0;
    if (kl >= KL_THRESHOLD * 2.0)
      return 0.0;
    return 100.0 * (1.0 - kl / (KL_THRESHOLD * 2.0));
  }

  /**
   * Compute sub-score for entropy retention.
   * Perfect at ratio=1.0, degrades as ratio drops below 1.
   */
  static double entropy_score(double retention_ratio) {
    if (retention_ratio >= 1.0)
      return 100.0;
    double drop = 1.0 - retention_ratio;
    if (drop >= ENTROPY_DROP_MAX * 2.0)
      return 0.0;
    return 100.0 * (1.0 - drop / (ENTROPY_DROP_MAX * 2.0));
  }

  /**
   * Compute sub-score for accuracy retention.
   */
  static double accuracy_score(double retention_ratio) {
    if (retention_ratio >= 1.0)
      return 100.0;
    double drop = 1.0 - retention_ratio;
    if (drop >= ACCURACY_DROP_MAX * 2.0)
      return 0.0;
    return 100.0 * (1.0 - drop / (ACCURACY_DROP_MAX * 2.0));
  }

  /**
   * Compute sub-score for calibration stability.
   */
  static double calibration_score(double ece_delta) {
    double abs_delta = std::abs(ece_delta);
    if (abs_delta <= 0.0)
      return 100.0;
    if (abs_delta >= CALIBRATION_DELTA_MAX * 2.0)
      return 0.0;
    return 100.0 * (1.0 - abs_delta / (CALIBRATION_DELTA_MAX * 2.0));
  }

  /**
   * Record a measurement and compute composite score.
   */
  StabilityMeasurement record(double kl, double entropy_retention,
                              double accuracy_retention,
                              double calibration_delta) {
    StabilityMeasurement m;
    m.kl_divergence = kl;
    m.entropy_retention = entropy_retention;
    m.accuracy_retention = accuracy_retention;
    m.calibration_delta = calibration_delta;

    double ks = kl_score(kl);
    double es = entropy_score(entropy_retention);
    double as = accuracy_score(accuracy_retention);
    double cs = calibration_score(calibration_delta);

    m.composite_score =
        W_KL * ks + W_ENTROPY * es + W_ACCURACY * as + W_CALIBRATION * cs;
    m.passed = m.composite_score >= PASS_THRESHOLD;

    // Add to rolling window
    history_.push_back(m);
    if (static_cast<int>(history_.size()) > WINDOW_SIZE) {
      history_.pop_front();
    }

    return m;
  }

  /**
   * Get rolling average composite score.
   */
  double rolling_average() const {
    if (history_.empty())
      return 0.0;
    double sum = 0.0;
    for (const auto &m : history_)
      sum += m.composite_score;
    return sum / history_.size();
  }

  /**
   * Check if system is stable (rolling avg >= threshold).
   */
  bool is_stable() const { return rolling_average() >= PASS_THRESHOLD; }

  /**
   * Get worst score in history.
   */
  double worst_score() const {
    double worst = 100.0;
    for (const auto &m : history_)
      worst = std::min(worst, m.composite_score);
    return worst;
  }

  int history_size() const { return static_cast<int>(history_.size()); }

private:
  std::deque<StabilityMeasurement> history_;
};

} // namespace temporal
} // namespace g38
